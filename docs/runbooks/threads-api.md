# Threads 수집 (크롤링 + 공식 API 신청)

## 1. 현재 구조

- **크롤링 (지금 동작):** 로그아웃 상태의 Threads 검색·프로필 페이지에 들어 있는 JSON에서 글과 반응 수를 읽습니다 (`collect/threads.py`, `access_method: crawler`, `config.mode: threads`).
  - 로그인·쿠키를 쓰지 않고, 우리 수집기 이름을 User-Agent로 그대로 씁니다. 브라우저도 실행하지 않습니다.
  - 요청에는 페이지 이동용 표준 헤더(`Sec-Fetch-Mode: navigate` 등)만 붙입니다.
- **robots.txt와 운영자 결정:** threads.com의 robots.txt는 모든 봇에 `Disallow: /`를 걸고, 허가 없는 자동 수집을 금지한다고 공지합니다. 운영자가 이를 알고도 2026-11-19에 개인 뉴스 파악 용도로 소량 크롤링을 결정했습니다.
  - 이 결정은 소스마다 `config.robots_note`에 기록되어 있습니다.
  - 이 예외는 Threads에만 해당합니다. 다른 크롤러는 계속 robots.txt를 따릅니다.
- **공식 API (신청 중):** 앱 심사를 통과하면 키워드 검색을 공식 API로 옮기고, 크롤링 소스는 retire합니다.

## 2. 크롤링 운영

| 대상 | 개수 | 수집 간격 (`min_interval_minutes`) | 하루 요청 |
|---|---|---|---|
| 핵심 키워드 검색 (`threads-search-*`) | 30 | 60분 | 720 |
| 나머지 키워드 검색 | 70 | 240분 | 420 |
| 프로필 (`threads-profile-*`) | 8 | 180분 | 64 |

- **공용 한도:** `scheduling/providers.py`의 `www.threads.com` 항목이 수집과 검증을 합쳐 하루 1,440회(평균 분당 1회), 연속 2회까지 허용합니다.
- **자동 멈춤:**
  - 429 응답이 오거나 글 데이터가 없는 페이지(로그인 화면, 차단, 구조 변경)가 오면 Threads 소스 전체가 1시간 쉽니다.
  - 같은 실패가 재시도 끝까지 이어지면 해당 소스가 일시정지됩니다.
- **수집 범위:** 최근 14일 안의 글만 저장합니다(`max_age_days: 14`). 답글과 글 없는 이미지·영상은 건너뜁니다. 본문은 앞 500자만 저장합니다.
- **반응 지표:** 좋아요, 답글, 리포스트, 인용, 공유 수를 저장합니다. 같은 글이 다시 보이면 `item_metric_snapshots`에 쌓이므로 반응 속도를 계산할 수 있습니다.

전부 끄기 (live 작업 폴더에서):

```bash
cd ~/WorkSpace/NEWS_INSIGHT-live
docker compose exec -T postgres psql -U news -d news_insight -Atc \
  "select key from sources where key like 'threads-%' and status <> 'paused'" |
  while read -r key; do docker compose exec -T api news-insight sources pause "$key" --reason "threads off"; done
```

다시 켤 때는 `sources resume <key>`를 씁니다.

## 3. 공식 API 신청 (사용자 작업)

준비물은 Meta 개발자 계정(Facebook 로그인)과 Threads 계정 하나(테스터용, 본인 계정 가능)입니다.

### 3-1. 앱 만들기
1. https://developers.facebook.com/apps 에서 **앱 만들기**를 누릅니다.
2. 사용 사례로 **"Threads API 액세스"**를 고르고, 앱 이름(예: `Daily IT Intelligence`)과 연락처 이메일을 넣습니다.
3. 비즈니스 포트폴리오는 "지금은 연결하지 않음"을 골라도 됩니다.

### 3-2. 권한 추가
**사용 사례 → Threads API 액세스 → 사용자 지정**에서 다음 3개 권한을 추가합니다.
- `threads_basic` (기본, 필수)
- `threads_keyword_search` (키워드 검색)
- `threads_profile_discovery` (다른 공개 계정 글 조회)

### 3-3. 설정 입력
**사용 사례 → 설정** 화면에서 다음을 입력합니다.
- 리디렉션 콜백 URL: `https://localhost/`
- 제거 콜백 URL과 삭제 콜백 URL: `https://<PUBLIC_HOST>:8700/privacy#data-deletion`

**앱 설정 → 기본 설정** 화면에서 다음을 입력합니다.
- 개인정보처리방침 URL: `https://<PUBLIC_HOST>:8700/privacy`
- 데이터 삭제 안내 URL: 위와 같은 `/privacy#data-deletion`

`<PUBLIC_HOST>`는 live `.env`의 `PUBLIC_HOST` 값입니다. `/privacy` 페이지는 로그인 없이 열리며, 연락처는 live `.env`의 `PRIVACY_CONTACT_EMAIL`로 정합니다.

### 3-4. 테스터 등록
1. **앱 역할 → 역할 → Threads 테스터 추가**에서 본인 Threads 아이디를 넣습니다.
2. Threads 앱이나 웹에서 **설정 → 계정 → 웹사이트 권한 → 초대**로 들어가 초대를 수락합니다.

### 3-5. 토큰 발급 (터미널)
**앱 설정 → 기본 설정**에 있는 **Threads 앱 ID**와 **Threads 앱 시크릿**을 씁니다. 시크릿은 채팅에 붙여넣지 말고, 아래 스크립트의 가려진 입력란에만 입력합니다.

```bash
cd ~/WorkSpace/NEWS_INSIGHT-live
THREADS_APP_ID=<앱 ID> scripts/threads-token.sh authorize
```

1. 출력된 주소를 브라우저에서 열고 테스터 계정으로 허용을 누릅니다.
2. `https://localhost/?code=...` 페이지로 이동합니다. 페이지는 열리지 않지만 정상입니다. 주소창에서 `code=` 뒤의 값을 복사합니다.
3. 복사한 값으로 아래 명령을 실행합니다.

```bash
THREADS_APP_ID=<앱 ID> scripts/threads-token.sh exchange <code>
scripts/threads-token.sh check
```

`exchange`가 60일짜리 토큰을 `.env`의 `SOURCE_SECRET_THREADS_TOKEN`에 저장합니다. `check` 결과에 본인 아이디가 보이면 성공입니다.

- **토큰 갱신:** 60일 안에 `scripts/threads-token.sh refresh`를 실행하면 60일이 연장됩니다. 한 달에 한 번 실행하면 안전합니다.
- **토큰 반영:** 새 토큰은 worker를 다시 시작해야 반영됩니다(live에서 `docker compose up -d worker`).

### 3-6. 앱 심사 (키워드 검색을 공개 글 전체로 넓히기)
심사 전에는 키워드 검색이 테스터 본인의 글만 돌려줍니다. **앱 심사 → 권한 및 기능**에서 `threads_keyword_search`와 `threads_profile_discovery`에 고급 액세스를 요청합니다.

**사용 목적 설명 (영문 그대로 붙여넣기):**

> Daily IT Intelligence is a private technology-trend monitoring tool used by its operator to follow public discussion of technology fields such as AI models, semiconductors, robotics and devices. The app calls keyword_search with about 100 technology keywords (for example "humanoid robot", "AI chip", "on-device AI") a few times a day, and reads recent public posts of a handful of technology publishers through profile discovery. For each public post it stores the permalink, username, timestamp, the first 500 characters of text and public reaction counts, and shows aggregated trend signals ("which technology topics are gaining attention") to the operator. It never posts, replies, messages, follows, or reads private data; it does not publish, sell or share Threads data, and does not use it to train AI models. Data deletion requests are handled through the URL on our privacy policy.

**화면 녹화 (심사 필수, 1~2분):**
1. 위 3-5의 `authorize` 주소로 로그인하고 권한 허용 화면에서 허용을 누르는 장면
2. 터미널에서 키워드 검색 호출과 결과(JSON)가 나오는 장면. 아래 명령을 쓰면 됩니다.

   ```bash
   curl -G https://graph.threads.net/v1.0/keyword_search --data-urlencode q="humanoid robot" --data-urlencode search_type=TOP --data-urlencode fields=id,text,permalink,timestamp,username --data-urlencode access_token="$(grep ^SOURCE_SECRET_THREADS_TOKEN= .env | cut -d= -f2-)"
   ```

3. 리더 사이트에 수집된 Threads 글이 보이는 장면

녹화 화면에 토큰 값이 보이지 않게 하세요. 위 명령은 토큰을 `.env`에서 읽으므로 화면에 나오지 않습니다.

- **추가 확인 요청:** 심사 도중 Meta가 **Access Verification**(개인 또는 사업자 확인)을 요구하면, 앱 대시보드 안내에 따라 신분 확인을 진행합니다.

## 4. 심사 통과 후

1. 토큰으로 `keyword_search` 응답 필드를 확인합니다(반응 수가 오는지 등).
2. 공식 API 수집 프리셋을 추가하고, 같은 키워드 100개를 API 소스로 등록합니다.
3. 크롤링 소스(`threads-search-*`)는 `sources retire`로 내립니다. 프로필은 `threads_profile_discovery`로 옮깁니다.
