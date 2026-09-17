# 오늘의 야구 노트 ⚾

딸을 위한 야구 사이트예요. 매일 새벽에 기록이 자동으로 새로 채워지고, 경기 시간엔 점수도 따라와요.

- **경기** — 「점수 지금 가져오기」 버튼으로 라이브 스코어 워크플로를 바로 실행할 수 있어요. 어제 경기 결과(점수·승/패/세이브 투수)와 오늘 경기(선발 투수, 진행 중이면 현재 점수·이닝). 오늘/어제 탭으로 넘겨 봐요.
- **우리 팀 전광판** — KIA·키움의 순위, 승패, 게임차, 연승·연패, 남은 경기
- **내 선수 카드** — 김도영·박재현·서건창의 올 시즌 기록과 리그 순위 배지(예: 홈런 1위)
- **KBO 순위표**와 **부문별 순위 TOP 5**(타자 9부문·투수 6부문)
- **선수 상세** — 카드·순위·메이저리거 어디서든 선수를 누르면 프로필(등번호·생일·키·몸무게·투타·경력)과 올 시즌 전체 기록, 리그 순위가 떠요. 기록 칸을 누르면 그 기록이 무슨 뜻인지 바로 알려줘요.
- **코리안 메이저리거** — 메이저리그와 마이너리그의 한국 선수 성적 (버튼 하나로 즉시 새로고침)
- **오늘의 야구 규칙** — 80개 규칙이 하루에 하나씩 돌아가요. **기록 사전** 버튼을 누르면 타율·OPS·ERA·WHIP 같은 지표 설명만 모아 볼 수 있어요 (`data/rules.json`)

무료로 돌아가요: GitHub Pages(호스팅) + GitHub Actions(매일 새벽 2시 자동 수집 + 경기 시간 10분마다 점수 수집).

---

## 1. 5분 만에 올리기

GitHub 계정만 있으면 돼요.

1. [github.com](https://github.com) → 오른쪽 위 **+** → **New repository** → 이름 예: `baseball-note` → **Public** → **Create repository**
2. 만들어진 페이지에서 **uploading an existing file** 링크 → 이 폴더 안의 파일을 **폴더 구조 그대로** 끌어다 놓기 → **Commit changes**
   - `.github`, `data`, `scripts` 폴더가 꼭 같이 올라가야 해요. `.github`는 숨김 폴더라 탐색기에서 안 보일 수 있으니 "숨김 파일 보기"를 켜 주세요.
   - 드래그가 번거로우면 [GitHub Desktop](https://desktop.github.com) 앱으로 폴더째 올려도 돼요.
3. 저장소의 **Settings → Pages** → Build and deployment에서 **Source: Deploy from a branch**, **Branch: main / (root)** → **Save**
   - 1~2분 뒤 `https://<깃허브아이디>.github.io/baseball-note/` 에서 사이트가 열려요.
4. **Actions** 탭 → 왼쪽 **야구 데이터 매일 업데이트** → 오른쪽 **Run workflow** → **Run workflow**
   - 초록색 체크가 뜨면 `data/` 폴더에 오늘 기록이 커밋되고, 사이트도 곧 바뀌어요.
   - 빨간 X가 뜨면 그 실행을 눌러 로그를 확인하세요. 처음엔 KBO 홈페이지 구조 때문에 표를 못 읽는 경우가 있을 수 있어요 (아래 "문제가 생기면" 참고).
5. 이제 매일 **한국시간 새벽 2시**에 자동으로 돌아가고, 경기 시간(14시~자정)엔 **라이브 스코어 업데이트**가 10분마다 점수를 가져와요. 딸에게 주소를 알려 주세요.

> 커밋이 거부되면: **Settings → Actions → General → Workflow permissions**에서 **Read and write permissions**를 선택하고 저장한 뒤 다시 실행하세요.

## 2. 이미 올린 사이트를 고친 파일로 바꾸기

사이트를 이미 올려 두었다면, 새 파일을 **같은 경로에 다시 올리기만** 하면 덮어써져요. 저장소를 지우거나 새로 만들 필요는 없어요.

**방법 A. 웹에서 드래그** (파일 몇 개일 때)

1. 저장소 첫 화면 → 오른쪽 위 **Add file** → **Upload files**
2. 바뀐 파일을 **폴더 구조 그대로** 끌어다 놓아요. 예를 들어 `index.html`은 최상위에, `fetch_kbo.py`는 `scripts` 폴더째 끌어 놓으면 `scripts/fetch_kbo.py` 자리에 들어가요. (폴더째 끌어 놓으면 경로가 자동으로 맞춰져요.)
   - `.github/workflows/` 안의 파일은 숨김 폴더라 잘 안 보여요. 탐색기에서 "숨김 파일 보기"를 켜고 `.github` 폴더째 끌어 놓거나, GitHub에서 그 파일을 열어 연필(✏️) 아이콘으로 내용을 붙여 넣어도 돼요.
3. 아래 **Commit changes** 클릭. 같은 이름의 파일은 새 내용으로 바뀌어요.

**방법 B. GitHub Desktop** (파일이 많을 때 편해요)

1. GitHub Desktop → **File → Clone repository** → 내 `baseball-note` 선택 → 컴퓨터에 받아요.
2. 받은 폴더 안에 새 파일들을 **덮어써서** 복사해요.
3. GitHub Desktop 왼쪽에 바뀐 파일 목록이 뜨면 아래 Summary에 `기능 추가` 같은 메모를 쓰고 **Commit to main** → 위쪽 **Push origin**

**올린 다음에 꼭 할 것**

1. **Actions** 탭 → **야구 데이터 매일 업데이트** → **Run workflow** 한 번 실행 (TOP 20, 선수 프로필, 경기 기록이 이때 처음 채워져요)
2. **Actions** 탭 → **라이브 스코어 업데이트** → **Run workflow** 한 번 실행 (경기 목록이 제대로 읽히는지 확인)
3. 1~2분 뒤 사이트를 새로고침. 옛날 화면이 보이면 브라우저 캐시 때문이니 한 번 더 새로고침하거나 시크릿 창으로 열어 보세요.

## 3. 내 취향으로 바꾸기

모두 `config.json` 한 파일에서 바꿔요.

```json
{
  "site_title": "오늘의 야구 노트",
  "season": 2026,
  "favorite_teams": ["KIA", "KIWOOM"],
  "favorite_players": [
    {"pcode": "52605", "name": "김도영", "team": "KIA", "type": "hitter", "position": "3루수"}
  ]
}
```

- **팀 코드**: `KIA` `KIWOOM` `SAMSUNG` `LG` `DOOSAN` `KT` `SSG` `LOTTE` `HANWHA` `NC`
- **선수 코드(pcode) 찾기**: [eng.koreabaseball.com](https://eng.koreabaseball.com) → TEAMS → Player Search → 선수 클릭 → 주소창의 `pcode=` 뒤 숫자예요. 투수는 `"type": "pitcher"`.
- **매년 시즌 시작 전** `season` 숫자를 올려 주세요 (선수 사진 주소에 쓰여요).

한글 이름이 안 나오는 선수는 Actions 실행 로그 맨 아래에 목록으로 나와요. `data/names_ko.json`(KBO), `data/mlb_names_ko.json`(MLB)에 한 줄씩 추가하면 다음 실행부터 한글로 보여요. (KBO 선수는 프로필을 읽을 때 한글 이름을 자동으로 채우니, 첫 실행 뒤엔 대부분 저절로 한글이 돼요.)

규칙을 고치거나 더 넣고 싶으면 `data/rules.json`을 편집하세요. 규칙은 `id` 순서로 하루에 하나씩 돌아가고, 마지막 규칙 다음엔 다시 1번으로 돌아와요. 규칙에 `"stats": ["AVG"]`(타자 기록 코드)나 `"pstats": ["ERA"]`(투수 기록 코드)를 적어 두면 선수 상세 화면의 **?** 버튼이 그 규칙으로 이어져요.

**라이브 스코어 주기 바꾸기**: `.github/workflows/live-scores.yml`의 `cron: "*/10 5-14 * * *"`에서 `*/10`이 "10분마다", `5-14`가 "UTC 5~14시(한국 14시~자정)"예요. 예를 들어 `*/20 8-14 * * *`로 바꾸면 한국시간 17시부터 20분마다 돌아요. 5분보다 짧게는 GitHub가 허용하지 않아요.

## 4. 알아 둘 점

- 처음 들어 있는 KBO 기록은 **2026년 9월 15일 기준**이고 부문별 순위는 타율만 20위까지 있어요. 나머지 부문의 20위, 선수 프로필, 경기 기록, 코리안 메이저리거 성적은 **첫 자동 실행 뒤에** 채워져요. 선수 프로필은 한 번에 80명씩 읽으니 1~2번 실행하면 다 채워지고, 그 뒤엔 새 선수만 읽어요.
- **라이브 스코어는 진짜 실시간이 아니에요.** 브라우저가 KBO 홈페이지를 직접 부를 수 없어서, GitHub Actions가 10분마다 점수를 읽어 저장하고 페이지가 그 파일을 2분마다 다시 읽어요. GitHub 예약 실행이 밀리면 10~20분 늦을 수 있어요. 아이에게는 "조금 늦게 따라오는 점수"라고 알려 주세요.
- 경기 시간에 10분마다 커밋이 생기니 저장소 히스토리에 `games:` 커밋이 많이 쌓여요. 정상이에요. 점수가 안 바뀌면 커밋하지 않아요.
- 저장소에 **60일 동안 새 커밋이 없으면** GitHub가 예약 실행을 자동으로 꺼요. 시즌 중엔 매일 커밋이 생겨 괜찮지만, 비시즌이 지나 시즌이 시작되면 Actions 탭에서 두 워크플로 모두 "Enable workflow"를 한 번 눌러 주세요.
- 컴퓨터에서 미리 보려면 프로젝트 폴더에서 `python -m http.server`를 실행하고 `http://localhost:8000`을 여세요. (파일을 더블클릭해서 열면 데이터가 안 읽혀요.)
- 코리안 메이저리거의 **지금 새로고침** 버튼은 브라우저가 MLB API를 직접 불러요. 매일 새벽 자동 수집과 별개로 경기 직후에도 눌러 볼 수 있어요.

## 5. 문제가 생기면

- KBO 홈페이지 디자인이 바뀌면 `scripts/fetch_kbo.py`가 표를 못 찾을 수 있어요. 스크립트는 표를 못 읽으면 **기존 데이터를 지우지 않고** 그대로 둬요. 부문별 순위는 표가 정말 그 부문 순서로 정렬됐는지 확인하고, 아니면 그 부문은 저장하지 않아요(그 부문은 사이트에 TOP 5로 대신 나와요). 로그에 `저장하지 않습니다`가 뜨면 그 부문의 `sort` 값을 확인해야 해요.
- 경기 화면이 비어 있거나 점수가 이상하면 Actions의 **라이브 스코어 업데이트** 로그를 보세요. `응답 필드 이름:` 줄에 KBO가 보내 준 항목 이름이 그대로 찍혀요. 점수·이닝 항목 이름이 예상과 다르면 `scripts/fetch_games.py`의 `normalize()`에 그 이름을 추가하면 돼요.
- 고칠 때는 Claude Code(또는 claude.ai)에 이 폴더를 열고 이렇게 부탁하면 돼요:
  "`scripts/fetch_kbo.py`가 KBO 순위표를 못 읽어요. Actions 로그는 이렇고, 지금 페이지 구조는 이래요."
- 로컬에서 직접 돌려 보려면: `pip install -r scripts/requirements.txt` → `python scripts/fetch_kbo.py` → `python scripts/fetch_games.py` → `python scripts/fetch_mlb.py`

## 파일 구성

```
index.html                     사이트 (HTML+CSS+JS 한 파일)
config.json                    응원팀·선수·시즌 설정
data/kbo.json                  KBO 순위·부문별 TOP 20·선수 기록 (자동 생성)
data/games.json                어제 결과·오늘 경기 점수 (자동 생성, 경기 시간엔 10분마다)
data/profiles.json             선수 프로필 캐시 (자동 생성, 지우면 다시 채워져요)
data/mlb_korean.json           코리안 메이저리거 성적 (자동 생성)
data/rules.json                야구 규칙 80개 (기록 사전 포함)
data/names_ko.json             KBO 선수 코드 → 한글 이름
data/mlb_names_ko.json         MLB 선수 영문 이름 → 한글 이름
scripts/fetch_kbo.py           KBO 홈페이지에서 순위·리더보드·선수 프로필 읽기
scripts/fetch_games.py         KBO 홈페이지 경기 목록(점수·이닝·투수) 읽기
scripts/fetch_mlb.py           MLB Stats API에서 한국 선수 자동 수집
.github/workflows/update-data.yml   매일 새벽 2시 자동 실행
.github/workflows/live-scores.yml   경기 시간 10분마다 점수 갱신
```

## 데이터 출처

KBO 기록과 경기 정보는 KBO 공식 홈페이지(운영: 스포츠투아이), 메이저리그 기록은 MLB Stats API에서 가져와요. 데이터와 사진의 권리는 KBO·MLB에 있고, 이 사이트는 개인 학습용이에요. 하루 한 번(경기 시간엔 10분에 한 번) 접속하도록 만들어져 있으니 실행 주기를 너무 짧게 바꾸지 말아 주세요.
