#!/usr/bin/env python3
"""
KBO 공식 홈페이지(koreabaseball.com) 첫 화면 전광판이 쓰는 경기 목록(JSON)을 읽어
어제 경기 결과와 오늘 경기(진행 중이면 현재 점수·이닝)를 data/games.json 으로 저장합니다.

- 요청은 날짜당 1번, 그러니까 한 번 실행에 2번(어제+오늘)이에요.
- 매일 새벽 자동 수집(update-data.yml)과, 경기 시간에 10분마다 도는
  라이브 스코어 워크플로(live-scores.yml)가 이 스크립트를 실행해요.
- 두 날짜를 모두 못 읽으면 기존 games.json을 그대로 두고 실패(exit 1)해요.
  한쪽만 실패하면 그 날짜는 기존 데이터를 유지해요.

실행:  python scripts/fetch_games.py
       python scripts/fetch_games.py --dump   (응답의 원래 필드 이름을 로그로 보여줘요)
"""
import datetime as dt
import json
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "games.json"
KST = dt.timezone(dt.timedelta(hours=9))

URL = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.koreabaseball.com/",
    "User-Agent": "Mozilla/5.0 (baseball-note; personal fan site, a few fetches per day)",
}
DELAY = 1.0

# KBO 사이트의 팀 ID / 팀 약칭 → 이 사이트의 팀 코드
TEAM_BY_ID = {"HT": "KIA", "WO": "KIWOOM", "SS": "SAMSUNG", "LG": "LG", "OB": "DOOSAN",
              "KT": "KT", "SK": "SSG", "LT": "LOTTE", "HH": "HANWHA", "NC": "NC"}
TEAM_BY_NAME = {"KIA": "KIA", "기아": "KIA", "키움": "KIWOOM", "삼성": "SAMSUNG", "LG": "LG",
                "두산": "DOOSAN", "KT": "KT", "SSG": "SSG", "롯데": "LOTTE", "한화": "HANWHA", "NC": "NC"}

# GAME_STATE_SC: 1 경기 전, 2 진행 중, 3 종료, 4·5 취소/노게임 계열
STATE = {"1": "before", "2": "live", "3": "final", "4": "cancelled", "5": "cancelled"}
STATE_TEXT = {"before": "경기 전", "live": "진행 중", "final": "경기 종료", "cancelled": "취소", "unknown": ""}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def first(row, *keys):
    """여러 후보 키 중 값이 있는 첫 번째를 돌려줍니다(사이트 필드명이 바뀌어도 버티기 위해)."""
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def find_key(row, *patterns):
    """정규식으로 키를 찾습니다. 후보 키 이름을 정확히 모를 때 씁니다."""
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for k, v in row.items():
            if rx.fullmatch(k) and v not in (None, ""):
                return v
    return None


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def team_code(row, side):
    """side: 'AWAY' 또는 'HOME'."""
    tid = str(first(row, f"{side}_ID", f"{side}_TEAM_ID") or "").upper()
    name = str(first(row, f"{side}_NM", f"{side}_TEAM_NM", f"{side}_NAME") or "").strip()
    code = TEAM_BY_ID.get(tid) or TEAM_BY_NAME.get(name) or TEAM_BY_NAME.get(name.upper())
    return {"code": code, "name": name or tid or "?"}


def normalize(row):
    d = str(first(row, "G_DT", "GAME_DATE") or "")
    date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else None
    state_code = str(first(row, "GAME_STATE_SC", "GAME_STATE") or "")
    state = STATE.get(state_code, "unknown")
    cancel = str(first(row, "CANCEL_SC_NM", "CANCEL_NM") or "").strip()
    if cancel and cancel not in ("정상경기", "정상"):
        state = "cancelled"
    away_score = to_int(first(row, "T_SCORE_CN", "AWAY_SCORE_CN", "AWAY_SCORE") or find_key(row, r"T_?SCORE.*", r"AWAY.*SCORE.*"))
    home_score = to_int(first(row, "B_SCORE_CN", "HOME_SCORE_CN", "HOME_SCORE") or find_key(row, r"B_?SCORE.*", r"HOME.*SCORE.*"))
    if state == "before":
        away_score = home_score = None
    inning = to_int(first(row, "GAME_INN_NO", "INN_NO") or find_key(row, r".*INN_NO"))
    half = str(first(row, "GAME_TB_SC", "TB_SC") or "").upper()[:1]
    inning_text = None
    if state == "live" and inning:
        inning_text = f"{inning}회" + ("초" if half == "T" else "말" if half == "B" else "")
    header_no = to_int(first(row, "HEADER_NO")) or 0

    game = {
        "id": str(first(row, "G_ID", "GAME_ID") or ""),
        "date": date,
        "time": str(first(row, "G_TM", "GAME_TM") or "").strip() or None,
        "stadium": str(first(row, "S_NM", "STADIUM_NM") or "").strip() or None,
        "away": team_code(row, "AWAY"),
        "home": team_code(row, "HOME"),
        "away_score": away_score,
        "home_score": home_score,
        "state": state,
        "state_text": cancel if state == "cancelled" and cancel else STATE_TEXT[state],
        "inning": inning if state == "live" else None,
        "half": half if state == "live" and half in ("T", "B") else None,
        "inning_text": inning_text,
        "series": str(first(row, "GAME_SC_NM", "SR_NM") or "").strip() or None,
        "header_no": header_no,
        "away_starter": (first(row, "T_PIT_P_NM", "AWAY_PIT_NM") or "").strip() or None,
        "home_starter": (first(row, "B_PIT_P_NM", "HOME_PIT_NM") or "").strip() or None,
        "win_pitcher": (first(row, "W_PIT_P_NM", "WIN_PIT_NM") or "").strip() or None,
        "lose_pitcher": (first(row, "L_PIT_P_NM", "LOSE_PIT_NM") or "").strip() or None,
        "save_pitcher": (first(row, "SV_PIT_P_NM", "SAVE_PIT_NM") or "").strip() or None,
        "tv": (first(row, "TV_IF") or "").strip() or None,
    }
    if state == "final" and away_score is not None and home_score is not None:
        game["winner"] = "home" if home_score > away_score else "away" if away_score > home_score else "draw"
    return game


def fetch_day(date, dump=False):
    """하루치 경기 목록. 실패하면 None, 경기가 없는 날이면 []."""
    body = {"leId": "1", "srId": "0,1,3,4,5,6,7,8,9", "date": date.strftime("%Y%m%d")}
    for attempt in range(3):
        try:
            r = requests.post(URL, data=body, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("d"), str):  # ASP.NET 래퍼 대비
                data = json.loads(data["d"])
            rows = data.get("game") if isinstance(data, dict) else None
            if rows is None and isinstance(data, dict):
                rows = next((v for v in data.values() if isinstance(v, list)), None)
            if not isinstance(rows, list):
                log(f"  예상과 다른 응답 형식: {str(data)[:200]}")
                return None
            if dump and rows:
                log("  첫 경기의 원래 필드:", json.dumps(rows[0], ensure_ascii=False))
            elif rows:
                log("  응답 필드 이름:", ", ".join(sorted(rows[0].keys())))
            time.sleep(DELAY)
            return [normalize(row) for row in rows if str(row.get("LE_ID", "1")) == "1"]
        except Exception as e:  # noqa: BLE001
            log(f"  재시도 {attempt + 1}/3: {date} ({e})")
            time.sleep(3)
    return None


def main():
    dump = "--dump" in sys.argv
    now = dt.datetime.now(KST)
    today = now.date()
    yesterday = today - dt.timedelta(days=1)

    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            old = {}

    result = {}
    ok = 0
    for key, date in (("yesterday", yesterday), ("today", today)):
        log(f"{key} ({date}) 경기 읽는 중…")
        games = fetch_day(date, dump)
        if games is None:
            prev = old.get(key) or {}
            if prev.get("date") == date.isoformat():
                log(f"  읽지 못해 기존 {key} 데이터를 유지합니다.")
                result[key] = prev
            else:
                result[key] = {"date": date.isoformat(), "games": [], "error": True}
            continue
        ok += 1
        games.sort(key=lambda g: (g["time"] or "99:99", g["header_no"], g["stadium"] or ""))
        result[key] = {"date": date.isoformat(), "games": games}
        log(f"  {len(games)}경기")

    if ok == 0:
        log("어제·오늘 경기를 모두 읽지 못했습니다. 기존 파일을 유지합니다.")
        sys.exit(1)

    data = {
        "fetched_at": now.isoformat(timespec="minutes"),
        "source": "https://www.koreabaseball.com",
        "seed": False,
        "live": any(g["state"] == "live" for g in result["today"].get("games", [])),
        "today": result["today"],
        "yesterday": result["yesterday"],
    }
    # 진행 중인 경기가 없고 내용도 그대로면 시각만 바꿔 저장하지 않아요(불필요한 커밋 방지).
    same = old.get("today") == data["today"] and old.get("yesterday") == data["yesterday"] and not old.get("seed")
    if same and not data["live"] and old.get("fetched_at"):
        log("경기 내용이 그대로라 파일을 바꾸지 않습니다.")
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    log(f"저장 완료: {OUT}  (어제 {len(result['yesterday'].get('games', []))}경기, 오늘 {len(result['today'].get('games', []))}경기, 진행 중 {'있음' if data['live'] else '없음'})")


if __name__ == "__main__":
    main()
