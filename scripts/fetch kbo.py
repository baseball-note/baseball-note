#!/usr/bin/env python3
"""
KBO 공식 영문 홈페이지(eng.koreabaseball.com)의 순위표와 부문별 리더보드(20위까지)를 읽어
data/kbo.json 으로 저장합니다. 선수 프로필(등번호·생년월일·신장/체중·투타·경력)은
KBO 한글 홈페이지의 선수 페이지에서 읽어 data/profiles.json 에 모아 두고, 한 번 읽은 선수는
PROFILE_DAYS 일 동안 다시 읽지 않습니다.

- 개인 학습·비상업 용도입니다. 데이터의 권리는 KBO에 있습니다.
- 하루 1~2회만 실행하세요. 요청 사이에 DELAY 초를 쉽니다.
- 표를 하나도 못 읽으면 기존 kbo.json을 덮어쓰지 않고 실패(exit 1)합니다.
- 리더보드는 정렬이 실제로 그 부문 순서인지 확인하고, 아니면 버립니다(잘못된 순위 방지).

실행:  python scripts/fetch_kbo.py
"""
import datetime as dt
import json
import pathlib
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text("utf-8"))
NAMES = {k: v for k, v in json.loads((ROOT / "data" / "names_ko.json").read_text("utf-8")).items()
         if not k.startswith("_")}
OUT = ROOT / "data" / "kbo.json"
PROFILES = ROOT / "data" / "profiles.json"

BASE = "https://eng.koreabaseball.com"
KO_BASE = "https://www.koreabaseball.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (kbo-note; personal fan site, 1 fetch/day)"}
DELAY = 1.5
SEASON = int(CONFIG.get("season") or dt.date.today().year)
PHOTO = "https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/person/middle/{season}/{pcode}.jpg"
BOARD_SIZE = 20          # 부문별 순위를 몇 위까지 저장할지
PROFILE_LIMIT = 80       # 한 번 실행에 새로 읽을 프로필 수(첫 실행 뒤엔 거의 0)
SUMMARY_LIMIT = 40       # TOP5에만 있는 선수 기록을 한 번에 몇 명까지 읽을지
PROFILE_DAYS = 180       # 프로필을 다시 읽는 주기(일)

# 정렬 파라미터는 사이트의 MORE+ 링크에서 확인한 값입니다. 페이지는 여러 개를 적으면 차례로 시도해요.
# (카테고리, 페이지 목록, sort, 예비) - 어느 부문이든 표가 그 부문 순서로 정렬된 것을 확인하지 못하면 버립니다.
BATTING_BOARDS = [
    ("AVG", ["/Stats/BattingLeaders.aspx"], None, False),
    ("HR", ["/Stats/BattingLeaders.aspx"], "HR_CN", False),
    ("RBI", ["/Stats/BattingLeaders.aspx"], "RBI_CN", False),
    ("R", ["/Stats/BattingLeaders.aspx"], "RUN_CN", True),
    ("H", ["/Stats/BattingLeaders.aspx"], "HIT_CN", True),
    ("SB", ["/Stats/BattingLeaders.aspx"], "SB_CN", False),
    ("OBP", ["/Stats/BattingLeaders02.aspx"], "OBP_RT", False),
    ("SLG", ["/Stats/BattingLeaders02.aspx"], "SLG_RT", True),
    ("OPS", ["/Stats/BattingLeaders02.aspx"], "OPS_RT", True),
]
PITCHING_BOARDS = [
    ("ERA", ["/Stats/PitchingLeaders.aspx"], None, False),
    ("W", ["/Stats/PitchingLeaders.aspx"], "W_CN", False),
    ("SV", ["/Stats/PitchingLeaders.aspx"], "SV_CN", False),
    ("HLD", ["/Stats/PitchingLeaders.aspx"], "HOLD_CN", False),
    ("SO", ["/Stats/PitchingLeaders02.aspx", "/Stats/PitchingLeaders.aspx"], "KK_CN", False),
    ("WHIP", ["/Stats/PitchingLeaders02.aspx", "/Stats/PitchingLeaders.aspx"], "WHIP_RT", True),
]
# 표에서 그 부문 값을 찾을 때 쓰는 열 이름 후보
BOARD_COLUMNS = {"SO": ["SO", "K", "KK"], "HLD": ["HLD", "HOLD", "HD"], "SV": ["SV", "S"], "WPCT": ["WPCT", "PCT"]}
LOWER_IS_BETTER = {"ERA", "WHIP"}
TOP5_CATEGORIES = {
    "AVERAGE": "AVG", "HOME RUNS": "HR", "RBI": "RBI", "RUNS": "R", "HITS": "H",
    "ON-BASE PERCENTAGE": "OBP", "ERA": "ERA", "WINS": "W", "SAVES": "SV",
    "HOLDS": "HLD", "WINNING PERCENTAGE": "WPCT", "STRIKEOUTS": "SO",
}
TEAM_CODES = {"KIA", "KIWOOM", "SAMSUNG", "LG", "DOOSAN", "KT", "SSG", "LOTTE", "HANWHA", "NC"}

session = requests.Session()
session.headers.update(HEADERS)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(path, params=None):
    return fetch_url(BASE + path, params)


def fetch_url(url, params=None):
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=30)
            r.raise_for_status()
            time.sleep(DELAY)
            return r.text
        except Exception as e:  # noqa: BLE001
            log(f"  재시도 {attempt + 1}/3: {url} ({e})")
            time.sleep(3)
    return None


def clean_header(text):
    t = re.sub(r"[^A-Za-z0-9 %/.\-]", " ", text).upper()
    return re.sub(r"\s+", " ", t).strip()


def to_number(s):
    s = (s or "").strip()
    if s in ("", "-"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d*\.\d+", s):
        return float(s)
    return s


def parse_tables(html):
    """페이지의 모든 <table>을 [(헤더 목록, [(셀 목록, pcode)]), ...] 로 돌려줍니다."""
    soup = BeautifulSoup(html, "html.parser")
    tables = []
    for table in soup.find_all("table"):
        headers = [clean_header(th.get_text(" ", strip=True)) for th in table.find_all("th")]
        trs = table.find_all("tr")
        if not headers and trs:
            # 헤더 행이 <td>로 되어 있는 경우: 첫 행이 숫자가 아니면 헤더로 씁니다.
            first = [clean_header(td.get_text(" ", strip=True)) for td in trs[0].find_all("td")]
            if first and not any(re.fullmatch(r"[\d.\-]+", c) for c in first if c):
                headers, trs = first, trs[1:]
        if not headers:
            continue
        rows = []
        for tr in trs:
            tds = tr.find_all("td")
            if not tds:
                continue
            cells = [td.get_text(" ", strip=True) for td in tds]
            link = tr.find("a", href=re.compile(r"pcode=\d+"))
            pcode = re.search(r"pcode=(\d+)", link["href"]).group(1) if link else None
            rows.append((cells, pcode))
        tables.append((headers, rows))
    return tables


def find_table(tables, must_have):
    for headers, rows in tables:
        if all(h in headers for h in must_have):
            return headers, rows
    return None, []


def rows_to_dicts(headers, rows):
    out = []
    for cells, pcode in rows:
        if len(cells) != len(headers):
            # 헤더 수와 안 맞으면 앞에서부터 맞춰 봅니다.
            cells = cells[:len(headers)]
            if len(cells) != len(headers):
                continue
        d = {}
        for h, c in zip(headers, cells):
            if h == "PLAYER":
                d["name"] = c
            elif h == "TEAM":
                d["team"] = c.upper()
            elif h == "RK":
                d["rank"] = to_number(c)
            else:
                d[h] = to_number(c)
        if pcode:
            d["pcode"] = pcode
            d["name_ko"] = NAMES.get(pcode)
        out.append(d)
    return out


def parse_standings(html):
    tables = parse_tables(html)
    headers, rows = find_table(tables, ("TEAM", "GB", "PCT"))
    standings = rows_to_dicts(headers, rows) if headers else []
    standings = [s for s in standings if s.get("team") in TEAM_CODES]
    h2, r2 = find_table(tables, ("TEAM", "ERA", "RUNS ALLOWED"))
    team_stats = rows_to_dicts(h2, r2) if h2 else []
    return standings, team_stats


def parse_board(html, kind):
    tables = parse_tables(html)
    key = ("PLAYER", "TEAM", "AVG") if kind == "batting" else ("PLAYER", "TEAM", "ERA")
    headers, rows = find_table(tables, key)
    if not headers:
        # 02 페이지는 AVG/ERA 열이 없을 수 있어 PLAYER/TEAM만으로 찾습니다.
        headers, rows = find_table(tables, ("PLAYER", "TEAM"))
    return rows_to_dicts(headers, rows) if headers else []


def parse_top5(html):
    soup = BeautifulSoup(html, "html.parser")
    boards = {}
    for el in soup.find_all(["h2", "h3", "h4", "h5", "h6", "strong", "p", "span", "a", "div"]):
        text = el.get_text(" ", strip=True)
        m = re.fullmatch(r"TOP\s*5\s+([A-Z\- ]+)", text, re.I)
        if not m:
            continue
        cat = TOP5_CATEGORIES.get(m.group(1).strip().upper())
        if not cat or cat in boards:
            continue
        lst = el.find_next(["ol", "ul"])
        if not lst:
            continue
        items = []
        for li in lst.find_all("li"):
            t = li.get_text(" ", strip=True)
            mm = re.match(r"(\d+)\.?\s*(.+?)\s*\(([^)]+)\)\s*([\d.]+)", t)
            if not mm:
                continue
            link = li.find("a", href=re.compile(r"pcode=\d+"))
            pcode = re.search(r"pcode=(\d+)", link["href"]).group(1) if link else None
            items.append({
                "rank": int(mm.group(1)), "name": mm.group(2).strip(),
                "team": mm.group(3).strip().upper(), "pcode": pcode,
                "name_ko": NAMES.get(pcode), "value": to_number(mm.group(4)),
            })
        if items:
            boards[cat] = items
    return boards


PROFILE_LABELS = {  # 선수 페이지의 라벨(한글/영문) → 저장할 키
    "name_ko": ["선수명", "이름", "Name"],
    "number": ["등번호", "배번", "Number", "No", "No."],
    "birth": ["생년월일", "생일", "Birthdate", "Birth Date", "Date of Birth", "Born"],
    "position": ["포지션", "Position"],
    "height_weight": ["신장/체중", "신장 / 체중", "신장·체중", "키/몸무게", "Height/Weight", "Height / Weight"],
    "height": ["신장", "키", "Height"],
    "weight": ["체중", "몸무게", "Weight"],
    "bats_throws": ["투타", "Bats/Throws", "Bats / Throws"],
    "career": ["경력", "출신교", "학교", "Career", "School"],
    "draft": ["지명순위", "지명", "Draft"],
    "debut_year": ["입단년도", "입단 년도", "데뷔", "Debut"],
}
_LABEL_TO_KEY = {}
for _k, _labels in PROFILE_LABELS.items():
    for _l in _labels:
        _LABEL_TO_KEY[_l.lower()] = _k
_LABEL_RE = re.compile(
    r"^\s*(" + "|".join(sorted((re.escape(l) for l in _LABEL_TO_KEY), key=len, reverse=True)) + r")\s*[:：]\s*(.+?)\s*$",
    re.I | re.S)
_INNER_LABEL_RE = re.compile(
    r"(?:^|\s)(" + "|".join(sorted((re.escape(l) for l in _LABEL_TO_KEY), key=len, reverse=True)) + r")\s*[:：]", re.I)


def _clean_profile(raw):
    """라벨→값 사전을 사이트에서 쓰기 좋은 형태로 정리합니다."""
    out = {}
    if raw.get("name_ko") and re.search(r"[가-힣]", raw["name_ko"]):  # 한글 이름일 때만
        out["name_ko"] = re.sub(r"\s*\(.*?\)\s*$", "", raw["name_ko"]).strip()
    if raw.get("number"):
        m = re.search(r"\d+", raw["number"])
        if m:
            out["number"] = int(m.group())
    if raw.get("birth"):
        m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", raw["birth"])
        if m:
            out["birth"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if raw.get("position"):
        pos = raw["position"].strip()
        m = re.match(r"(.+?)\s*\((.+?)\)\s*$", pos)
        if m:
            pos, bt = m.group(1).strip(), m.group(2).strip()
            if re.search(r"[좌우양]투[좌우양]타", bt):
                out["bats_throws"] = bt
            else:
                pos = f"{pos}({bt})"
        out["position"] = pos
    if raw.get("bats_throws"):
        out["bats_throws"] = raw["bats_throws"].strip()
    hw = raw.get("height_weight") or ""
    m = re.search(r"(\d{3})\s*cm", hw) or re.search(r"(\d{3})\s*cm", raw.get("height") or "")
    if m:
        out["height"] = int(m.group(1))
    m = re.search(r"(\d{2,3})\s*kg", hw) or re.search(r"(\d{2,3})\s*kg", raw.get("weight") or "")
    if m:
        out["weight"] = int(m.group(1))
    for k in ("career", "draft"):
        if raw.get(k):
            out[k] = re.sub(r"\s+", " ", raw[k]).strip()
    if raw.get("debut_year"):
        m = re.search(r"\d{4}", raw["debut_year"])
        if m:
            out["debut_year"] = int(m.group())
    return out


def parse_profile(html):
    """선수 페이지에서 '라벨 : 값' 형태의 프로필을 찾습니다. 못 찾으면 {}."""
    soup = BeautifulSoup(html, "html.parser")
    raw = {}

    def put(label, value):
        key = _LABEL_TO_KEY.get(label.strip().lower())
        if key and value and key not in raw:
            raw[key] = value.strip()

    # 1) "생년월일 : 2003.10.02" 처럼 한 요소 안에 라벨과 값이 같이 있는 경우(짧은 요소부터)
    found = []
    for el in soup.find_all(["li", "dd", "td", "p", "span", "div", "strong", "em", "b", "th", "dt"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 80:
            continue
        m = _LABEL_RE.match(text)
        if m and not _INNER_LABEL_RE.search(m.group(2)):  # 값 안에 다른 라벨이 섞여 있으면 상위 요소이므로 건너뜀
            found.append((len(text), m.group(1), m.group(2)))
    for _, label, value in sorted(found, key=lambda x: x[0]):
        put(label, value)
    # 2) <dt>라벨</dt><dd>값</dd>, <th>라벨</th><td>값</td> 처럼 나뉜 경우
    for tag, nxt in (("dt", "dd"), ("th", "td")):
        for el in soup.find_all(tag):
            label = el.get_text(" ", strip=True).rstrip(":： ")
            if label.lower() in _LABEL_TO_KEY:
                sib = el.find_next_sibling(nxt)
                if sib:
                    put(label, sib.get_text(" ", strip=True))
    return _clean_profile(raw)


def fetch_profile(pcode, kind):
    """KBO 한글 선수 페이지 → 안 되면 영문 페이지. 결과에 항상 fetched 날짜를 넣습니다."""
    pages = []
    ko_page = "/Record/Player/HitterDetail/Basic.aspx" if kind == "hitter" else "/Record/Player/PitcherDetail/Basic.aspx"
    ko_alt = "/Record/Player/PitcherDetail/Basic.aspx" if kind == "hitter" else "/Record/Player/HitterDetail/Basic.aspx"
    en_page = "/Teams/PlayerInfoHitter/Summary.aspx" if kind == "hitter" else "/Teams/PlayerInfoPitcher/Summary.aspx"
    pages = [(KO_BASE + ko_page, {"playerId": pcode}), (KO_BASE + ko_alt, {"playerId": pcode}), (BASE + en_page, {"pcode": pcode})]
    for url, params in pages:
        html = fetch_url(url, params)
        if not html:
            continue
        prof = parse_profile(html)
        if prof.get("birth") or prof.get("height") or prof.get("position"):
            prof["fetched"] = dt.date.today().isoformat()
            return prof
    return {"fetched": dt.date.today().isoformat(), "empty": True}


def load_profiles():
    if PROFILES.exists():
        try:
            return {k: v for k, v in json.loads(PROFILES.read_text("utf-8")).items() if not k.startswith("_")}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def profile_is_fresh(prof):
    if not prof or not prof.get("fetched"):
        return False
    try:
        age = (dt.date.today() - dt.date.fromisoformat(prof["fetched"])).days
    except ValueError:
        return False
    return age < (PROFILE_DAYS if not prof.get("empty") else 14)  # 비어 있으면 2주 뒤 다시 시도


def board_value(row, cat):
    for col in BOARD_COLUMNS.get(cat, [cat]):
        if row.get(col) is not None:
            return row[col]
    return None


def check_board(rows, cat, must_verify):
    """리더보드가 정말 그 부문 순서로 정렬되어 있는지 확인하고, 순위를 다시 매깁니다.
    돌려주는 값: (정리된 rows) 또는 None(버려야 함)."""
    vals = [board_value(r, cat) for r in rows]
    nums = [v for v in vals if isinstance(v, (int, float))]
    if len(nums) < max(3, len(rows) // 2):
        # 값 열이 없으면 순서를 확인할 수 없으니 저장하지 않습니다(엉뚱한 순위를 보여주는 것보다 TOP5로 대신하는 편이 안전).
        log(f"  {cat}: 표에서 {cat} 값을 찾지 못해 이 부문은 저장하지 않습니다(사이트는 TOP5로 대신 보여줘요).")
        return None
    ordered = [v for v in vals if isinstance(v, (int, float))]
    asc = cat in LOWER_IS_BETTER
    sorted_ok = all((a <= b) if asc else (a >= b) for a, b in zip(ordered, ordered[1:]))
    if not sorted_ok:
        log(f"  {cat}: 표가 {cat} 순서로 정렬되어 있지 않아 이 부문은 저장하지 않습니다(sort 파라미터 확인 필요).")
        return None
    out = []
    for r in rows:
        v = board_value(r, cat)
        if not isinstance(v, (int, float)):
            continue
        better = sum(1 for o in ordered if (o < v if asc else o > v))
        r = dict(r)
        r["rank"] = better + 1
        r["value"] = v
        out.append(r)
    return out[:BOARD_SIZE]


def parse_player_summary(html, kind):
    """리더보드에 없는 선수는 선수 페이지의 올해 기록 표에서 읽습니다(구조가 바뀌면 None)."""
    tables = parse_tables(html)
    key = ("AVG", "HR") if kind == "hitter" else ("ERA", "IP")
    for headers, rows in tables:
        if not all(k in headers for k in key):
            continue
        dicts = rows_to_dicts(headers, rows)
        if not dicts:
            continue
        for d in dicts:  # 연도 열이 있으면 올해 행을 고릅니다.
            if str(SEASON) in [str(v) for v in d.values()]:
                return d
        return dicts[-1]
    return None


def main():
    log("KBO 순위표 읽는 중…")
    html = fetch("/Standings/TeamStandings.aspx")
    standings, team_stats = parse_standings(html) if html else ([], [])
    if len(standings) < 10:
        log(f"순위표를 읽지 못했습니다(팀 {len(standings)}개). 기존 데이터를 유지합니다.")
        sys.exit(1)

    players = {}  # pcode -> 합쳐진 기록
    profiles = load_profiles()

    def absorb(rows, kind):
        for r in rows:
            p = r.get("pcode")
            if not p:
                continue
            merged = players.setdefault(p, {"kind": kind})
            for k, v in r.items():
                if k in ("rank", "value"):
                    continue
                if v is not None:
                    merged[k] = v

    def boards(spec, kind):
        result = {}
        for cat, paths, sort, must_verify in spec:
            log(f"{kind} {cat} 읽는 중…")
            rows = []
            for path in paths:
                html = fetch(path, {"sort": sort} if sort else None)
                rows = parse_board(html, kind) if html else []
                if rows and board_value(rows[0], cat) is not None:
                    break
            if not rows:
                log(f"  {cat} 표를 찾지 못했습니다.")
                continue
            rows = check_board(rows, cat, must_verify)
            if rows:
                result[cat] = rows
                absorb(rows, "hitter" if kind == "batting" else "pitcher")
        return result

    batting_boards = boards(BATTING_BOARDS, "batting")
    pitching_boards = boards(PITCHING_BOARDS, "pitching")

    log("TOP5 읽는 중…")
    html = fetch("/Stats/BattingTop5.aspx")
    batting_top5 = parse_top5(html) if html else {}
    html = fetch("/Stats/PitchingTop5.aspx")
    pitching_top5 = parse_top5(html) if html else {}

    # TOP5에만 있고 리더보드엔 없는 선수(주로 투수)는 선수 페이지에서 올해 기록 전체를 읽어요.
    # 그래야 사이트에서 이 선수를 눌렀을 때 타자처럼 모든 기록이 한 번에 보여요.
    for kind, top5 in (("hitter", batting_top5), ("pitcher", pitching_top5)):
        base = {}
        for rows in top5.values():
            for r in rows:
                p = r.get("pcode")
                if p and p not in players and p not in base:
                    base[p] = r
        if not base:
            continue
        log(f"TOP5에만 있는 {'타자' if kind == 'hitter' else '투수'} {len(base)}명 기록 읽는 중…")
        page = "/Teams/PlayerInfoHitter/Summary.aspx" if kind == "hitter" else "/Teams/PlayerInfoPitcher/Summary.aspx"
        for p, r in list(base.items())[:SUMMARY_LIMIT]:
            rec = {"kind": kind, "pcode": p, "name": r.get("name"), "team": r.get("team"), "name_ko": r.get("name_ko")}
            try:
                html = fetch(page, {"pcode": p})
                stats = parse_player_summary(html, kind) if html else None
            except Exception as e:  # noqa: BLE001
                log(f"  {r.get('name')}: 선수 페이지를 읽지 못했어요 ({e})")
                stats = None
            for k, v in (stats or {}).items():
                if k not in ("rank", "name", "team", "pcode", "name_ko") and v is not None:
                    rec[k] = v
            players[p] = rec

    # 좋아하는 선수 정리
    favorites = []
    for fav in CONFIG.get("favorite_players", []):
        pcode = str(fav["pcode"])
        kind = fav.get("type", "hitter")
        stats = players.get(pcode)
        source = "board"
        if not stats:
            page = "/Teams/PlayerInfoHitter/Summary.aspx" if kind == "hitter" else "/Teams/PlayerInfoPitcher/Summary.aspx"
            log(f"{fav['name']} 선수는 리더보드에 없어 선수 페이지에서 읽습니다…")
            html = fetch(page, {"pcode": pcode})
            stats = parse_player_summary(html, kind) if html else None
            source = "summary" if stats else None
        ranks = {}
        for cat, rows in (batting_boards if kind == "hitter" else pitching_boards).items():
            for r in rows:
                if r.get("pcode") == pcode and r.get("rank"):
                    ranks[cat] = r["rank"]
        for cat, rows in (batting_top5 if kind == "hitter" else pitching_top5).items():
            for r in rows:
                if r.get("pcode") == pcode:
                    ranks.setdefault(cat, r["rank"])
        favorites.append({
            "pcode": pcode, "name": fav["name"], "team": fav.get("team"),
            "position": fav.get("position"), "type": kind,
            "photo": PHOTO.format(season=SEASON, pcode=pcode),
            "stats": stats, "ranks": ranks, "source": source,
        })
        if not stats:
            log(f"  {fav['name']} 선수 기록을 찾지 못했습니다. config.json의 pcode를 확인하세요.")
        players.setdefault(pcode, {"kind": kind, "pcode": pcode, "name": fav["name"], "team": fav.get("team"), "name_ko": fav["name"]})

    # 선수 프로필: 아직 없거나 오래된 선수만 새로 읽어요(한 번에 PROFILE_LIMIT 명까지).
    fav_codes = [str(f["pcode"]) for f in CONFIG.get("favorite_players", [])]
    need = sorted((p for p in players if not profile_is_fresh(profiles.get(p))),
                  key=lambda p: (p not in fav_codes, p))  # 내 선수 먼저
    if need:
        log(f"선수 프로필 읽는 중… ({min(len(need), PROFILE_LIMIT)}명 / 남은 {len(need)}명)")
    for p in need[:PROFILE_LIMIT]:
        profiles[p] = fetch_profile(p, players[p].get("kind", "hitter"))
        if not profiles[p].get("empty"):
            log(f"  {profiles[p].get('name_ko') or players[p].get('name')}: 프로필 저장")
    PROFILES.write_text(json.dumps({"_설명": "KBO 선수 페이지에서 읽은 프로필(자동 생성). 지우면 다음 실행 때 다시 채워져요.", **profiles},
                                   ensure_ascii=False, indent=1), "utf-8")

    for p, rec in players.items():
        rec["photo"] = PHOTO.format(season=SEASON, pcode=p)
        prof = {k: v for k, v in (profiles.get(p) or {}).items() if k not in ("fetched", "empty", "name_ko")}
        if prof:
            rec["profile"] = prof
        if not rec.get("name_ko") and (profiles.get(p) or {}).get("name_ko"):
            rec["name_ko"] = profiles[p]["name_ko"]
    # 리더보드 행에도 프로필에서 찾은 한글 이름을 넣어요.
    for board in (batting_boards, pitching_boards, batting_top5, pitching_top5):
        for rows in board.values():
            for r in rows:
                if not r.get("name_ko") and r.get("pcode") in players:
                    r["name_ko"] = players[r["pcode"]].get("name_ko")
    for f in favorites:
        prof = (players.get(f["pcode"]) or {}).get("profile")
        if prof:
            f["profile"] = prof

    unmapped = sorted(
        {(r["pcode"], r.get("name"), r.get("team")) for r in players.values()
         if r.get("pcode") and not r.get("name_ko")},
        key=lambda x: x[2] or "")

    data = {
        "season": SEASON,
        "fetched_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes"),
        "source": BASE,
        "seed": False,
        "board_size": BOARD_SIZE,
        "standings": standings,
        "team_stats": team_stats,
        "batting_top5": batting_top5,
        "pitching_top5": pitching_top5,
        "batting_boards": batting_boards,
        "pitching_boards": pitching_boards,
        "players": players,
        "favorites": favorites,
        "unmapped": [{"pcode": p, "name": n, "team": t} for p, n, t in unmapped],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    log(f"저장 완료: {OUT}  (팀 {len(standings)}, 선수 {len(players)}, TOP5 {len(batting_top5) + len(pitching_top5)}개 부문)")
    if unmapped:
        log("\n한글 이름이 없는 선수 (다음 실행 때 프로필에서 자동으로 채워지지만, data/names_ko.json 에 직접 넣어도 돼요):")
        for p, n, t in unmapped:
            log(f'  "{p}": "",   # {n} ({t})')


if __name__ == "__main__":
    main()

