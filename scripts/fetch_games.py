#!/usr/bin/env python3
"""
KBO 공식 홈페이지(koreabaseball.com) 첫 화면 전광판이 쓰는 경기 목록(JSON)을 읽어
어제 경기 결과와 오늘 경기(진행 중이면 현재 점수·이닝)를 data/games.json 으로 저장합니다.
경기가 시작됐거나 끝난 경기는 게임센터의 스코어보드(이닝별 점수)와 박스스코어(타자·투수 기록,
결승타·홈런 같은 경기 기록)도 함께 읽어 각 경기의 "box" 칸에 넣어요. 사이트에서 경기를 누르면 보여요.

- 경기 목록 요청은 날짜당 1번(어제+오늘 = 2번). 박스스코어는 경기당 2번이에요.
  끝난 경기는 두 번 확인한 뒤엔 다시 읽지 않고, 진행 중인 경기만 매번 새로 읽어요.
- 매일 새벽 자동 수집(update-data.yml)과, 경기 시간에 10분마다 도는
  라이브 스코어 워크플로(live-score.yml)가 이 스크립트를 실행해요.
- 두 날짜를 모두 못 읽으면 기존 games.json을 그대로 두고 실패(exit 1)해요.
  한쪽만 실패하면 그 날짜는 기존 데이터를 유지해요.
- 박스스코어를 못 읽어도 점수는 그대로 저장돼요(박스스코어는 있으면 좋은 덤이에요).

실행:  python scripts/fetch_games.py
       python scripts/fetch_games.py --dump     (응답의 원래 필드·박스스코어 원본 일부를 로그로 보여줘요)
       python scripts/fetch_games.py --no-box   (박스스코어는 건너뛰고 점수만)
"""
import datetime as dt
import html
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

# 게임센터(경기 상세)가 쓰는 주소: 스코어보드(이닝별 점수)와 박스스코어(타자·투수 기록)
SCOREBOARD_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScoreBoardScroll"
BOXSCORE_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetBoxScoreScroll"
GAMECENTER = "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx"
BOX_TIME_BUDGET = 150     # 한 번 실행에서 박스스코어 읽기에 쓸 수 있는 최대 시간(초)
BOX_MAX_GAMES = 12        # 한 번 실행에서 박스스코어를 새로 읽을 최대 경기 수
BOX_FINAL_CHECKS = 2      # 끝난 경기는 이 횟수만큼 확인한 뒤엔 다시 읽지 않아요(기록 정정 반영용)
BOX_TIMEOUT = 15

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
        # 박스스코어를 요청할 때 필요한 번호(정규시즌 srId=0, 포스트시즌은 3·4·5·7)
        "sr_id": str(first(row, "SR_ID") if first(row, "SR_ID") is not None else "0"),
        "season_id": str(first(row, "SEASON_ID") or d[:4] or ""),
    }
    if state == "final" and away_score is not None and home_score is not None:
        game["winner"] = "home" if home_score > away_score else "away" if away_score > home_score else "draw"
    return game


# ---------------------------------------------------------------------------
# 스코어보드 · 박스스코어
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_box_state = {"scoreboard_type": None, "fails": 0, "dumped": False}


def clean_cell(text):
    """표 칸의 글자에서 HTML 태그·&nbsp; 를 걷어 냅니다."""
    if text is None:
        return ""
    t = _TAG_RE.sub(" ", str(text).replace("<br>", "/").replace("<br/>", "/").replace("<br />", "/"))
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def parse_kbo_table(value):
    """KBO 표(JSON 문자열 또는 dict) → {"headers": [글자...], "rows": [[글자...], ...]}.
    형식: {"headers":[{"row":[{"Text":..}, ..]}], "rows":[{"row":[{"Text":..}, ..]}, ..]}"""
    if not value:
        return {"headers": [], "rows": []}
    data = value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except ValueError:
            return {"headers": [], "rows": []}
    if not isinstance(data, dict):
        return {"headers": [], "rows": []}

    def cells(row):
        raw = row.get("row") if isinstance(row, dict) else row
        if not isinstance(raw, list):
            return []
        return [clean_cell(c.get("Text") if isinstance(c, dict) else c) for c in raw]

    header_rows = data.get("headers") or data.get("header") or []
    headers = cells(header_rows[-1]) if isinstance(header_rows, list) and header_rows else []
    rows = [cells(r) for r in (data.get("rows") or []) if r is not None]
    return {"headers": headers, "rows": [r for r in rows if r]}


def post_json(url, body, referer):
    """KBO 웹서비스에 POST. 성공하면 dict, 아니면 None. (두 번까지 시도)"""
    headers = dict(HEADERS)
    headers["Referer"] = referer
    for attempt in range(2):
        try:
            r = requests.post(url, data=body, headers=headers, timeout=BOX_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("d"), str):  # ASP.NET 래퍼 대비
                data = json.loads(data["d"])
            return data if isinstance(data, dict) else None
        except Exception as e:  # noqa: BLE001
            log(f"    재시도 {attempt + 1}/2: {url.rsplit('/', 1)[-1]} ({e})")
            time.sleep(2)
    return None


def _ok(data):
    return isinstance(data, dict) and str(data.get("code", "100")) == "100"


def _num(text):
    """'12' → 12, '0.312'·'5 1/3'·'-' 같은 건 글자 그대로."""
    t = (text or "").strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    return t or None


def _col(headers, names, default):
    """헤더에서 이름으로 열 번호를 찾고, 없으면 기본 위치를 씁니다."""
    for i, h in enumerate(headers):
        if h.replace(" ", "") in names:
            return i
    return default


def parse_linescore(data):
    """스코어보드 응답 → (innings, line, rheb, info). 못 읽으면 (None, None, None, info)."""
    info = {}
    for key, src in (("crowd", "CROWD_CN"), ("start", "START_TM"), ("end", "END_TM"), ("duration", "USE_TM"), ("stadium", "S_NM")):
        v = data.get(src)
        if v not in (None, "", 0, "0"):
            info[key] = str(v).strip()
    t2 = parse_kbo_table(data.get("table2"))
    if len(t2["rows"]) < 2:
        return None, None, None, info
    away, home = t2["rows"][0], t2["rows"][1]
    n = max(len(away), len(home))
    away += ["-"] * (n - len(away))
    home += ["-"] * (n - len(home))
    labels = [h for h in t2["headers"] if re.fullmatch(r"\d+", h)]
    if len(labels) != n:
        labels = [str(i + 1) for i in range(n)]
    # 아직 하지 않은 이닝('-')은 뒤에서부터 잘라 내되 9회까지는 남겨요.
    keep = n
    while keep > 9 and away[keep - 1] in ("-", "") and home[keep - 1] in ("-", ""):
        keep -= 1
    line = {"away": [c or "-" for c in away[:keep]], "home": [c or "-" for c in home[:keep]]}
    rheb = None
    t3 = parse_kbo_table(data.get("table3"))
    if len(t3["rows"]) >= 2:
        hdr = [h.upper() for h in t3["headers"]]
        idx = {k: _col(hdr, {k}, i) for i, k in enumerate(("R", "H", "E", "B"))}
        rheb = {}
        for side, row in (("away", t3["rows"][0]), ("home", t3["rows"][1])):
            rheb[side] = {k: _num(row[i]) if i < len(row) else None for k, i in idx.items()}
    return labels[:keep], line, rheb, info


def parse_batters(block):
    """박스스코어의 한 팀 타자 묶음(table1=타순·포지션·이름, table2=이닝별 결과, table3=타수·안타·타점·득점·타율)."""
    if not isinstance(block, dict):
        return []
    t1, t2, t3 = (parse_kbo_table(block.get(k)) for k in ("table1", "table2", "table3"))
    labels = [h for h in t2["headers"] if re.fullmatch(r"\d+", h)]
    h3 = t3["headers"]
    i_ab, i_h = _col(h3, {"타수", "AB"}, 0), _col(h3, {"안타", "H"}, 1)
    i_rbi, i_r, i_avg = _col(h3, {"타점", "RBI"}, 2), _col(h3, {"득점", "R"}, 3), _col(h3, {"타율", "AVG"}, 4)
    out, prev_order = [], None
    for i, row in enumerate(t1["rows"]):
        if len(row) == 2:            # 교체 선수 줄이 타순 칸 없이 [포지션, 이름]만 오는 경우 대비
            row = [""] + row
        name = row[2] if len(row) > 2 else (row[-1] if row else "")
        if not name or name in ("합계", "TOTAL", "계"):
            continue
        stat = t3["rows"][i] if i < len(t3["rows"]) else []
        events = t2["rows"][i] if i < len(t2["rows"]) else []
        pa = []
        for j, ev in enumerate(events):
            ev = ev.strip(" /")
            if ev and ev not in ("-", "0"):
                pa.append([labels[j] if j < len(labels) and len(labels) == len(events) else str(j + 1), ev])
        order = _num(row[0]) if row else None
        if not isinstance(order, int):
            order = None
        is_sub = prev_order is not None and (order is None or order == prev_order)
        if order is None:
            order = prev_order
        get = lambda k: _num(stat[k]) if k < len(stat) else None  # noqa: E731
        out.append({"o": order, "sub": bool(is_sub), "p": row[1] if len(row) > 1 else "",
                    "n": name, "ab": get(i_ab), "h": get(i_h), "rbi": get(i_rbi), "r": get(i_r), "avg": get(i_avg), "pa": pa})
        if order is not None:
            prev_order = order
    return out


_PITCHER_COLS = [("n", {"선수명", "투수"}), ("in", {"등판"}), ("res", {"결과"}), ("w", {"승"}), ("l", {"패"}), ("sv", {"세"}),
                 ("ip", {"이닝"}), ("bf", {"타자"}), ("np", {"투구수"}), ("ab", {"타수"}), ("h", {"피안타"}), ("hr", {"홈런", "피홈런"}),
                 ("bb", {"4사구", "사사구"}), ("so", {"삼진", "탈삼진"}), ("r", {"실점"}), ("er", {"자책", "자책점"}), ("era", {"평균자책점", "ERA"})]


def parse_pitchers(block):
    if not isinstance(block, dict):
        return []
    t = parse_kbo_table(block.get("table"))
    idx = {key: _col(t["headers"], names, i) for i, (key, names) in enumerate(_PITCHER_COLS)}
    out = []
    for row in t["rows"]:
        name = row[idx["n"]] if idx["n"] < len(row) else ""
        if not name or name in ("합계", "TOTAL", "계"):
            continue
        rec = {}
        for key, i in idx.items():
            v = row[i] if i < len(row) else ""
            rec[key] = v if key in ("n", "in", "res", "ip", "era") else _num(v)
        rec["res"] = rec.get("res") if rec.get("res") not in ("", "-", None) else None
        out.append(rec)
    return out


def parse_notes(value):
    """결승타·홈런·2루타·실책·도루 … [[이름, 내용], ...]"""
    t = parse_kbo_table(value)
    notes = []
    for row in t["rows"]:
        if len(row) >= 2 and row[0] and row[1]:
            notes.append([row[0], row[1]])
    return notes


def fetch_box(game, final, dump=False):
    """한 경기의 스코어보드+박스스코어를 읽어 사이트용으로 정리합니다. 아무것도 못 읽으면 None."""
    gid = game.get("id")
    if not gid:
        return None
    season = game.get("season_id") or gid[:4]
    body = {"leId": "1", "srId": game.get("sr_id") or "0", "seasonId": season, "gameId": gid}
    referer = f"{GAMECENTER}?gameDate={gid[:8]}&gameId={gid}&section=REVIEW"

    box = {}
    # 1) 스코어보드: 이닝별 점수. 사이트 개편으로 type 값이 필요해질 수 있어 한 번은 type=3으로도 시도해요.
    sb = None
    tries = [_box_state["scoreboard_type"]] if _box_state["scoreboard_type"] is not None else ["", "3"]
    for typ in tries:
        data = post_json(SCOREBOARD_URL, {**body, **({"type": typ} if typ else {})}, referer)
        time.sleep(DELAY)
        if _ok(data) and data.get("table2"):
            sb, _box_state["scoreboard_type"] = data, typ
            break
    if sb:
        if dump and not _box_state["dumped"]:
            log("    스코어보드 원본 키:", ", ".join(sorted(sb.keys())))
            log("    table2 앞부분:", str(sb.get("table2"))[:300])
        innings, line, rheb, info = parse_linescore(sb)
        if line:
            box.update({"innings": innings, "line": line})
        if rheb:
            box["rheb"] = rheb
        if info:
            box["info"] = info

    # 2) 박스스코어: 타자·투수 기록과 경기 기록(결승타·홈런 등)
    bs = post_json(BOXSCORE_URL, body, referer)
    time.sleep(DELAY)
    if _ok(bs) and isinstance(bs.get("arrHitter"), list):
        if dump and not _box_state["dumped"]:
            log("    박스스코어 원본 키:", ", ".join(sorted(bs.keys())))
            first_h = bs["arrHitter"][0] if bs["arrHitter"] else {}
            for k in ("table1", "table2", "table3"):
                log(f"    arrHitter[0].{k} 앞부분:", str(first_h.get(k))[:300])
            log("    arrPitcher[0].table 앞부분:", str(((bs.get("arrPitcher") or [{}])[0] or {}).get("table"))[:300])
            log("    tableEtc 앞부분:", str(bs.get("tableEtc"))[:300])
        hit, pit = bs.get("arrHitter") or [], bs.get("arrPitcher") or []
        batters = {"away": parse_batters(hit[0]) if len(hit) > 0 else [], "home": parse_batters(hit[1]) if len(hit) > 1 else []}
        pitchers = {"away": parse_pitchers(pit[0]) if len(pit) > 0 else [], "home": parse_pitchers(pit[1]) if len(pit) > 1 else []}
        if batters["away"] or batters["home"]:
            box["batters"] = batters
        if pitchers["away"] or pitchers["home"]:
            box["pitchers"] = pitchers
        notes = parse_notes(bs.get("tableEtc"))
        if notes:
            box["notes"] = notes
    _box_state["dumped"] = _box_state["dumped"] or bool(sb or bs)

    if not box.get("line") and not box.get("batters"):
        return None
    box["final"] = bool(final)
    return box


def attach_boxes(result, old, dump=False):
    """어제·오늘 경기 중 시작했거나 끝난 경기에 box 를 붙입니다. 끝난 경기는 BOX_FINAL_CHECKS 번 확인한 뒤엔 재사용."""
    old_boxes = {}
    for key in ("today", "yesterday"):
        for g in ((old.get(key) or {}).get("games") or []):
            if g.get("id") and g.get("box"):
                old_boxes[g["id"]] = g["box"]
    started = time.monotonic()
    fetched = succeeded = 0
    for key in ("today", "yesterday"):          # 오늘(진행 중) 경기를 먼저
        for g in result[key].get("games", []):
            if g["state"] not in ("live", "final") or not g.get("id"):
                continue
            prev = old_boxes.get(g["id"])
            final = g["state"] == "final"
            if prev and prev.get("final") and int(prev.get("checks") or 0) >= BOX_FINAL_CHECKS:
                g["box"] = prev                   # 이미 충분히 확인한 끝난 경기
                continue
            over = time.monotonic() - started > BOX_TIME_BUDGET or fetched >= BOX_MAX_GAMES or _box_state["fails"] >= 2
            box = None
            if not over:
                log(f"  박스스코어 읽는 중: {g['id']} ({g['away']['name']} : {g['home']['name']})")
                try:
                    box = fetch_box(g, final, dump)
                except Exception as e:  # noqa: BLE001 - 박스스코어 때문에 점수 저장이 막히면 안 돼요.
                    log(f"    박스스코어를 정리하지 못했어요: {e}")
                    box = None
                fetched += 1
                _box_state["fails"] = 0 if box else _box_state["fails"] + 1
            if box:
                succeeded += 1
                checks = int((prev or {}).get("checks") or 0) if (prev or {}).get("final") else 0
                box["checks"] = checks + 1 if final else 0
                g["box"] = box
            elif prev:
                g["box"] = prev                   # 이번엔 못 읽었으면 지난번 것을 유지
    if _box_state["fails"] >= 2:
        log("  박스스코어 응답을 연달아 읽지 못해 이번 실행에서는 더 시도하지 않았어요(점수는 정상 저장).")
    return succeeded


def dump_json(data):
    """games.json 저장용 문자열. 박스스코어는 한 줄로 눌러 담아 파일이 너무 길어지지 않게 해요."""
    boxes = {}

    def strip(day):
        games = []
        for g in day.get("games", []):
            if g.get("box"):
                token = f"@@BOX{len(boxes)}@@"
                boxes[token] = g["box"]
                g = {**g, "box": token}
            games.append(g)
        return {**day, "games": games}

    slim = {**data, "today": strip(data["today"]), "yesterday": strip(data["yesterday"])}
    text = json.dumps(slim, ensure_ascii=False, indent=1)
    for token, box in boxes.items():
        text = text.replace(json.dumps(token), json.dumps(box, ensure_ascii=False, separators=(",", ":")), 1)
    return text


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
    with_box = "--no-box" not in sys.argv
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

    boxes = 0
    if with_box:
        try:
            boxes = attach_boxes(result, old, dump)
        except Exception as e:  # noqa: BLE001 - 어떤 경우에도 점수 저장은 계속해요.
            log(f"박스스코어 단계에서 문제가 생겼지만 점수는 그대로 저장합니다: {e}")

    data = {
        "fetched_at": now.isoformat(timespec="minutes"),
        "source": "https://www.koreabaseball.com",
        "seed": False,
        "script": "box-1",   # 박스스코어를 읽는 새 스크립트가 만든 파일이라는 표시(사이트가 확인해요)
        "live": any(g["state"] == "live" for g in result["today"].get("games", [])),
        "today": result["today"],
        "yesterday": result["yesterday"],
    }
    # 진행 중인 경기가 없고 내용도 그대로면 시각만 바꿔 저장하지 않아요(불필요한 커밋 방지).
    same = (old.get("today") == data["today"] and old.get("yesterday") == data["yesterday"] and not old.get("seed")
            and old.get("script") == data["script"])
    if same and not data["live"] and old.get("fetched_at"):
        log("경기 내용이 그대로라 파일을 바꾸지 않습니다.")
        return
    OUT.write_text(dump_json(data), "utf-8")
    have = sum(1 for k in ("today", "yesterday") for g in result[k].get("games", []) if g.get("box"))
    log(f"저장 완료: {OUT}  (어제 {len(result['yesterday'].get('games', []))}경기, 오늘 {len(result['today'].get('games', []))}경기, "
        f"진행 중 {'있음' if data['live'] else '없음'}, 박스스코어 {have}경기 · 이번에 새로 읽은 것 {boxes}경기)")


if __name__ == "__main__":
    main()
