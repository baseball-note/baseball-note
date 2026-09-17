#!/usr/bin/env python3
"""
MLB 공식 Stats API(statsapi.mlb.com, 무료·인증 없음)에서
메이저리그와 마이너리그(트리플A~루키)의 한국 출생 선수를 자동으로 찾아
올 시즌 성적을 data/mlb_korean.json 으로 저장합니다.

- 선수 명단을 손으로 관리할 필요가 없어요. birthCountry 가 South Korea 인 선수를 모읍니다.
- 한국 태생이 아닌 한국계 선수를 넣고 싶으면 config.json 의 mlb_extra_ids 에 MLBAM id 를,
  빼고 싶은 선수는 mlb_exclude_ids 에 적으세요.

실행:  python scripts/fetch_mlb.py
"""
import datetime as dt
import json
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text("utf-8"))
NAMES = {k: v for k, v in json.loads((ROOT / "data" / "mlb_names_ko.json").read_text("utf-8")).items()
         if not k.startswith("_")}
OUT = ROOT / "data" / "mlb_korean.json"

API = "https://statsapi.mlb.com/api/v1"
HEADERS = {"User-Agent": "kbo-note personal fan site"}
SEASON = int(CONFIG.get("season") or dt.date.today().year)
EXTRA_IDS = {int(x) for x in CONFIG.get("mlb_extra_ids", [])}
EXCLUDE_IDS = {int(x) for x in CONFIG.get("mlb_exclude_ids", [])}

LEVELS = [1, 11, 12, 13, 14, 16]  # MLB, AAA, AA, High-A, A, Rookie
LEVEL_KO = {1: "메이저리그", 11: "트리플A", 12: "더블A", 13: "하이A", 14: "싱글A", 16: "루키"}
LEVEL_ORDER = {1: 0, 11: 1, 12: 2, 13: 3, 14: 4, 16: 5}

MLB_TEAMS_KO = {
    "Arizona Diamondbacks": "애리조나 다이아몬드백스", "Athletics": "애슬레틱스", "Oakland Athletics": "오클랜드 애슬레틱스",
    "Atlanta Braves": "애틀랜타 브레이브스", "Baltimore Orioles": "볼티모어 오리올스", "Boston Red Sox": "보스턴 레드삭스",
    "Chicago Cubs": "시카고 컵스", "Chicago White Sox": "시카고 화이트삭스", "Cincinnati Reds": "신시내티 레즈",
    "Cleveland Guardians": "클리블랜드 가디언스", "Colorado Rockies": "콜로라도 로키스", "Detroit Tigers": "디트로이트 타이거스",
    "Houston Astros": "휴스턴 애스트로스", "Kansas City Royals": "캔자스시티 로열스", "Los Angeles Angels": "LA 에인절스",
    "Los Angeles Dodgers": "LA 다저스", "Miami Marlins": "마이애미 말린스", "Milwaukee Brewers": "밀워키 브루어스",
    "Minnesota Twins": "미네소타 트윈스", "New York Mets": "뉴욕 메츠", "New York Yankees": "뉴욕 양키스",
    "Philadelphia Phillies": "필라델피아 필리스", "Pittsburgh Pirates": "피츠버그 파이리츠", "San Diego Padres": "샌디에이고 파드리스",
    "San Francisco Giants": "샌프란시스코 자이언츠", "Seattle Mariners": "시애틀 매리너스", "St. Louis Cardinals": "세인트루이스 카디널스",
    "Tampa Bay Rays": "탬파베이 레이스", "Texas Rangers": "텍사스 레인저스", "Toronto Blue Jays": "토론토 블루제이스",
    "Washington Nationals": "워싱턴 내셔널스",
}
HITTING_KEYS = ["gamesPlayed", "plateAppearances", "atBats", "runs", "hits", "doubles", "triples", "homeRuns", "rbi",
                "stolenBases", "baseOnBalls", "strikeOuts", "avg", "obp", "slg", "ops"]
PITCHING_KEYS = ["gamesPlayed", "gamesStarted", "wins", "losses", "saves", "holds", "era", "inningsPitched",
                 "hits", "baseOnBalls", "strikeOuts", "homeRuns", "whip"]

session = requests.Session()
session.headers.update(HEADERS)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(path, params=None):
    for attempt in range(3):
        try:
            r = session.get(API + path, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            log(f"  재시도 {attempt + 1}/3: {path} ({e})")
            time.sleep(3)
    return {}


def norm_name(name):
    return re.sub(r"[^a-z]", "", (name or "").lower())


def korean_name(p):
    for candidate in (p.get("fullName"), p.get("useName", "") + " " + p.get("lastName", ""),
                      p.get("firstName", "") + " " + p.get("lastName", "")):
        ko = NAMES.get(norm_name(candidate))
        if ko:
            return ko
    return None


def is_korean_born(p):
    bc = (p.get("birthCountry") or "").lower()
    return "korea" in bc and "north" not in bc


def pick(stat, keys):
    return {k: stat.get(k) for k in keys if k in stat}


def main():
    log(f"{SEASON} 시즌 한국 선수 찾는 중…")
    people = {}
    teams = {}
    for sid in LEVELS:
        data = get(f"/sports/{sid}/players", {"season": SEASON})
        found = 0
        for p in data.get("people", []):
            pid = p.get("id")
            if pid in EXCLUDE_IDS:
                continue
            if is_korean_born(p) or pid in EXTRA_IDS:
                rec = people.setdefault(pid, {"person": p, "levels": []})
                rec["levels"].append(sid)
                found += 1
        log(f"  {LEVEL_KO[sid]}: {found}명")
        tdata = get("/teams", {"sportId": sid, "season": SEASON})
        for t in tdata.get("teams", []):
            teams[t["id"]] = t
        time.sleep(0.5)

    # 명단에는 없지만 직접 지정한 선수
    for pid in EXTRA_IDS - set(people):
        data = get(f"/people/{pid}")
        for p in data.get("people", []):
            people[pid] = {"person": p, "levels": []}

    players = []
    for pid, rec in people.items():
        p = rec["person"]
        cur = p.get("currentTeam") or {}
        team = teams.get(cur.get("id"), {})
        if not team and cur.get("id"):
            team = (get(f"/teams/{cur['id']}").get("teams") or [{}])[0]
        level_id = (team.get("sport") or {}).get("id")
        parent = team.get("parentOrgName") or (team.get("name") if level_id == 1 else None)

        log(f"  {p.get('fullName')} 성적 읽는 중…")
        sdata = get(f"/people/{pid}/stats", {"stats": "yearByYear", "group": "hitting,pitching"})
        splits = []
        for block in sdata.get("stats", []):
            group = (block.get("group") or {}).get("displayName")
            for sp in block.get("splits", []):
                if str(sp.get("season")) != str(SEASON):
                    continue
                st = sp.get("stat") or {}
                sport = sp.get("sport") or {}
                t = sp.get("team") or {}
                if group == "hitting" and not st.get("plateAppearances"):
                    continue
                if group == "pitching" and not st.get("inningsPitched"):
                    continue
                splits.append({
                    "group": group,
                    "level_id": sport.get("id"),
                    "level": LEVEL_KO.get(sport.get("id"), sport.get("abbreviation") or sport.get("name")),
                    "team": t.get("name"),
                    "team_ko": MLB_TEAMS_KO.get(t.get("name")),
                    "stat": pick(st, HITTING_KEYS if group == "hitting" else PITCHING_KEYS),
                })
        # yearByYear 에 올해 기록이 없으면 레벨별 시즌 기록으로 다시 시도
        if not splits:
            for sid in sorted(set(rec["levels"]) | {1}):
                sdata = get(f"/people/{pid}/stats",
                            {"stats": "season", "season": SEASON, "group": "hitting,pitching", "sportId": sid})
                for block in sdata.get("stats", []):
                    group = (block.get("group") or {}).get("displayName")
                    for sp in block.get("splits", []):
                        st = sp.get("stat") or {}
                        if group == "hitting" and not st.get("plateAppearances"):
                            continue
                        if group == "pitching" and not st.get("inningsPitched"):
                            continue
                        t = sp.get("team") or {}
                        splits.append({"group": group, "level_id": sid, "level": LEVEL_KO[sid],
                                       "team": t.get("name"), "team_ko": MLB_TEAMS_KO.get(t.get("name")),
                                       "stat": pick(st, HITTING_KEYS if group == "hitting" else PITCHING_KEYS)})
                time.sleep(0.3)
        splits.sort(key=lambda s: (LEVEL_ORDER.get(s["level_id"], 9), s["group"] != "hitting"))

        pos = (p.get("primaryPosition") or {}).get("abbreviation")
        ft_in = re.match(r"(\d+)' ?(\d+)", p.get("height") or "")  # 6' 1" → cm
        profile = {
            "number": p.get("primaryNumber"),
            "birth": p.get("birthDate"),
            "height": round((int(ft_in.group(1)) * 12 + int(ft_in.group(2))) * 2.54) if ft_in else None,
            "weight": round(p["weight"] * 0.4536) if p.get("weight") else None,
            "bats": (p.get("batSide") or {}).get("code"),
            "throws": (p.get("pitchHand") or {}).get("code"),
            "debut": p.get("mlbDebutDate"),
            "position_name": (p.get("primaryPosition") or {}).get("name"),
        }
        players.append({
            "id": pid,
            "name": p.get("fullName"),
            "name_ko": korean_name(p),
            "position": pos,
            "age": p.get("currentAge"),
            "birth_city": p.get("birthCity"),
            "profile": {k: v for k, v in profile.items() if v not in (None, "")},
            "team": team.get("name"),
            "team_ko": MLB_TEAMS_KO.get(team.get("name")),
            "parent_org": parent,
            "parent_org_ko": MLB_TEAMS_KO.get(parent),
            "level_id": level_id,
            "level": LEVEL_KO.get(level_id, (team.get("sport") or {}).get("abbreviation")),
            "splits": splits,
            "headshot": f"https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/{pid}/headshot/67/current",
        })
        time.sleep(0.3)

    players.sort(key=lambda x: (LEVEL_ORDER.get(x["level_id"], 9), x["name_ko"] or x["name"] or ""))
    if not players:
        log("한국 선수를 한 명도 찾지 못했습니다. 기존 데이터를 유지합니다.")
        sys.exit(1)

    data = {
        "season": SEASON,
        "fetched_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes"),
        "source": API,
        "seed": False,
        "players": players,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    log(f"저장 완료: {OUT}  ({len(players)}명)")
    missing = [p for p in players if not p["name_ko"]]
    if missing:
        log("\n한글 이름이 없는 선수 (data/mlb_names_ko.json 에 추가하세요):")
        for p in missing:
            log(f'  "{norm_name(p["name"])}": "",   # {p["name"]} ({p["team"]})')


if __name__ == "__main__":
    main()
