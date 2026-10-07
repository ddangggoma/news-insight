# 사이트 로그인 — 아이디/비밀번호, 회원가입 → 관리자 승인

> 요청(2026-10-06): "기본 페이지 로그인을 위한 내용을 개발 계획 세워주세요."
> 변경(2026-10-07): "이메일 토큰 방식이 아니라 id/pw 로그인 방식으로 … 보안을 고려해서 … 가입 신청 후 admin이 승인한 사용자만 접근이 가능하도록."
> 확정(2026-10-07): "ID/PW 방식으로 변경 … 회원가입 페이지를 만들고 이름을 기입받도록 … admin이 승인해준 ID만 로그인 … 승인이 안된 것은 Admin에게 승인요청 하라고." Google 로그인은 운영 도메인이 없어(IP만 있음) 보류.
> 실행 규칙은 [10-execution-progress](2026-10-04-10-execution-progress.md)와 같다(브랜치 → verify → PR → CI → 병합 → `NEWS_INSIGHT-live/scripts/deploy.sh`).
> **상태: 승인 대기.** 사용자 승인 후 PR 1부터 진행한다.

## 0. 목표

- 독자 화면 전체(`/` 탐색, `/briefings`, `/radar`, `/digests`, `/items`)와 콘솔(`/console`)을 **아이디/비밀번호 로그인** 뒤로 옮긴다.
- **회원가입 페이지**(`/signup`)에서 아이디·비밀번호·**이름**을 받는다. 가입하면 `pending`(승인 대기) 상태가 된다.
- **관리자가 승인한 아이디만 로그인된다.** 승인 전 계정이 올바른 비밀번호로 로그인하면 "승인 대기 중입니다. 관리자에게 승인을 요청하세요."를 보여 준다.
- 역할은 둘: `reader`(독자 화면), `admin`(독자 화면 + 콘솔 + 사용자 승인).
- 이메일 매직링크 로그인(P8, D21)은 없앤다. SMTP는 운영 알림 메일(`mailer.send_email`)에만 남는다.

### 완료 기준

1. 세션 없이 어떤 화면을 열어도 `/login?next=…`로 간다. 서버가 세션을 매번 검증한다(쿠키만 보고 통과시키지 않음).
2. 가입 → 로그인 시도 시 승인 요청 안내 → 관리자가 `/console/users`에서 승인 → 로그인 성공. 거절·정지 계정도 로그인되지 않는다.
3. 비밀번호는 Argon2id 해시로만 저장한다. 평문은 DB·로그 어디에도 없다.
4. 무차별 대입이 막히고, 로그인 실패 응답으로 아이디 존재 여부를 알 수 없다.
5. 비밀번호 변경·초기화, 정지, 역할 변경 시 그 사용자의 기존 세션이 모두 끊긴다.
6. 가입·로그인·승인 등 인증 이벤트가 감사 로그에 남는다.
7. 기존 E2E가 로그인 상태로 통과하고, 가입 → 승인 요청 안내 → 승인 → 로그인 E2E가 추가된다.

## 1. 현재 상태 (출발점)

- **API** `apps/api/src/news_insight/auth/`: `admin_email` 한 주소만 매직링크를 받는다. 토큰은 `admin_tokens`에 SHA-256 해시로 저장(`login` 15분 1회용, `session` 14일).
- **경계**: `/api/admin/*`, `/api/public/*`은 Caddy가 외부에서 404로 막고, 웹 서버만 내부망에서 `X-Console-Key` / `X-Public-Key`로 부른다. **인증 API도 이 경계 안에 둔다.**
- **웹** (Next 16.3): `proxy.ts`가 `ni_admin` 쿠키가 없으면 `/console*`을 `/login`으로 보내고, `lib/session.ts`의 `requireAdmin()`이 API로 세션을 검증한다(콘솔 18곳).
- **독자 화면**: 로그인 없음. 데이터는 `PUBLIC_API_KEY`로 받아 Next 데이터 캐시(`tags: ["reader"]`)에 둔다.
- **접속 주소**: 도메인 없이 IP로 접속한다. HTTPS(8700)는 Caddy 자체 인증서(브라우저 경고), HTTP(8701)도 같은 사이트를 서빙한다(2026-10-06).
- **IP 기준 제한의 한계**: Docker Desktop(Mac)에서는 모든 접속이 같은 게이트웨이 IP로 보인다(`docs/runbooks/operations.md`). IP 기준 제한은 사실상 전체 공용 한도가 된다.

## 2. 보안 설계

### 2-1. 전송 구간 — 로그인은 HTTPS에서만

평문 HTTP로 로그인하면 비밀번호가 그대로 네트워크를 지난다. **HTTP 포트(8701)를 HTTPS(8700)로 리다이렉트**한다(2026-10-06 이전 동작으로 복귀). 세션 쿠키는 `Secure`로만 발급한다. → §6-1 확인 필요.

- 도메인이 없어 HTTPS는 Caddy 자체 인증서다. 첫 접속 때 브라우저 경고는 남는다(암호화는 된다). 도메인을 붙이면 경고가 사라진다(후속 작업).
- IP 주소에는 HSTS가 적용되지 않으므로 켜지 않는다.

### 2-2. 비밀번호 저장

- **Argon2id** (`argon2-cffi`, 새 의존성 1개). 시작값은 OWASP 권장 하한(memory 19 MiB, time 2, parallelism 1)이다. 운영 서버에서 검증 1회가 0.2~0.5초가 되도록 맞춘다. 로그인 성공 시 `check_needs_rehash`로 파라미터를 자동 갱신한다.
- 해시 계산은 동기 라우트(스레드풀)에서 한다. 기존 auth 라우트와 같은 형태다.

### 2-3. 비밀번호 정책 (NIST SP 800-63B 기준)

- 길이 10~128자. 대문자·특수문자 강제나 주기적 변경 강제는 두지 않는다.
- 다음은 거부한다: 흔한 비밀번호(상위 1만 개 목록 파일을 저장소에 포함, 외부 호출 없음), 아이디가 들어간 비밀번호.
- 입력 칸은 붙여넣기·비밀번호 관리자를 허용한다(`autocomplete="new-password"` / `"current-password"`).

### 2-4. 무차별 대입·열거 방지

| 장치 | 규칙 |
|---|---|
| 계정 잠금 | 연속 실패 5회 → 15분 잠금. 이후 실패마다 2배(최대 24시간). 성공하면 초기화. 잠금 중에도 응답은 일반 실패와 같다. 관리자 잠금은 CLI `users unlock`으로 푼다 |
| 요청 제한 | API가 Redis로 로그인 분당 30회, 가입 시간당 20회를 센다. 클라이언트 IP 기준이며, 웹이 Caddy의 `X-Forwarded-For`를 `X-Client-IP`로 넘긴다. Docker Desktop에서는 전체 공용 한도가 되므로(§1) 넉넉하게 잡고, 주된 방어는 계정 잠금이다 |
| Caddy | `/login`, `/signup`에 별도 `rate_limit` zone(분당 30) |
| 열거 방지 | 실패 메시지는 하나: "아이디 또는 비밀번호가 올바르지 않습니다". 없는 아이디에도 더미 해시로 Argon2 검증을 돌려 응답 시간을 맞춘다 |
| 상태 안내 | 승인 대기·거절·정지는 **비밀번호가 맞을 때만** 알려 준다. 비밀번호가 틀리면 일반 실패와 같다 |

### 2-5. 세션

- 로그인 성공 시 새 토큰(`secrets.token_urlsafe(32)`)을 발급하고 SHA-256 해시만 저장한다. 로그인 전 쿠키는 재사용하지 않는다(세션 고정 방지).
- 쿠키 `__Host-ni_session`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`. 절대 만료 14일, 유휴 만료 3일.
- 비밀번호 변경·초기화, 정지, 역할 변경 시 그 사용자의 세션을 **전부 폐기**한다. 본인 비밀번호 변경 시에는 현재 세션만 새로 발급한다.
- `/account`에서 "다른 기기 모두 로그아웃"을 할 수 있다.

### 2-6. CSRF·리다이렉트

- 로그인·가입·로그아웃·승인 등 모든 변경은 **Server Actions**(POST)로 한다. Next가 `Origin`과 `Host`를 비교해 다른 출처 요청을 거부한다. GET으로 상태를 바꾸는 경로는 없다.
- `next`는 `/`로 시작하고 `//`·`/\`로 시작하지 않는 같은 출처 경로만 허용한다(오픈 리다이렉트 방지).

### 2-7. 가입 남용 방지

- 가입 폼에 허니팟 필드를 둔다. 승인 대기 계정은 최대 50개이고, 넘으면 "지금은 가입 신청을 받을 수 없습니다"를 보여 준다.
- 거절된 계정은 30일 뒤, 90일 넘게 승인되지 않은 계정은 자동 삭제한다(기존 정리 작업에 추가).

### 2-8. 개인정보

- 받는 항목은 **아이디, 비밀번호, 이름**뿐이다.
- 가입 화면에 수집 항목·목적(접근 승인 판단과 사용자 표시)·보관 기간(거절·탈퇴 시 삭제)을 적고 동의 체크를 받는다.
- 로그·감사 로그에는 비밀번호·세션 토큰·요청 본문을 남기지 않는다.

### 2-9. 감사 로그

`auth_events` 테이블은 `at`, `event`, `user_id`, `actor_id`(관리자 조치일 때), `ip`, `user_agent`(200자)를 기록하고 180일 보관한다. `event`는 다음 중 하나다: signup, login_ok, login_fail, login_pending, locked, logout, approve, reject, suspend, reactivate, role_change, password_change, password_reset. 콘솔에서 사용자별로 본다.

## 3. 구현

### 3-1. 데이터 모델 (마이그레이션 `0028_users`)

`users`

| 필드 | 뜻 |
|---|---|
| `id` | PK |
| `username` | 4~32자, `[a-z0-9._-]`, 소문자로 정규화, unique |
| `password_hash` | Argon2id 문자열 |
| `name` | 이름(1~50자, 필수) |
| `role` | `reader` · `admin` |
| `status` | `pending`(승인 대기) · `active` · `rejected` · `suspended` |
| `must_change_password` | 관리자 초기화 후 첫 로그인 시 변경 강제 |
| `failed_count`, `locked_until` | 계정 잠금(§2-4) |
| `created_at`, `approved_at`, `approved_by`, `last_login_at`, `password_changed_at` | |

`user_sessions`: `id`, `user_id`(FK, cascade), `token_hash`(unique), `created_at`, `expires_at`, `last_seen_at`, `revoked_at`, `ip`, `user_agent`.

`auth_events`: §2-9.

`admin_tokens`는 전환이 끝난 PR 4에서 삭제한다.

### 3-2. API (`apps/api/src/news_insight/auth/`)

- `passwords.py`: 해시·검증·재해시, 정책 검사(목록 `catalog/common-passwords.txt`).
- `service.py`를 사용자 기반으로 다시 쓴다:
  - 사용자 쪽: `register`, `authenticate`(잠금·더미 검증 포함, 결과는 `ok` / `invalid` / `pending` / `rejected` / `suspended`), `issue_session`, `check_session`, `revoke_session(s)`, `change_password`.
  - 관리자 쪽: `approve`, `reject`, `suspend`, `reactivate`, `set_role`, `reset_password`. `reset_password`는 임시 비밀번호를 한 번만 돌려주고 `must_change_password=true`로 둔다.
- 라우트는 지금처럼 `/api/admin/auth/*`(내부망 + `X-Console-Key`) 아래에 둔다:
  - 사용자용: `POST /signup`, `POST /login`, `POST /session`, `POST /logout`, `POST /logout-all`, `POST /password`
  - 관리자용: `GET /users?status=`, `POST /users/{id}/approve|reject|suspend|reactivate|role|reset-password`, `GET /users/{id}/events`. 요청에 담긴 세션 토큰으로 `role == admin`을 **API에서도** 다시 확인한다.
- `POST /login`은 비밀번호가 맞고 상태가 `pending`이면 403과 `{"status": "pending"}`을 돌려준다. 웹은 이 값으로 승인 요청 안내를 띄운다.
- CLI:
  - `news-insight users create-admin <username> --name <이름>`: 비밀번호는 프롬프트로 두 번 받고, 인자나 환경 변수로는 받지 않는다.
  - `users list`, `users approve <username>`, `users reset-password <username>`, `users unlock <username>`
  - 마지막 관리자는 정지·강등할 수 없다.
- 매직링크 코드(`admin link` 명령, `mailer.login_url` / `build_message` / `send_login_link`)는 PR 4에서 삭제한다. `admin_email`은 운영 알림 수신 주소로만 남는다.

### 3-3. 웹: 가드 (`apps/web`)

- `proxy.ts`:
  - matcher를 사이트 전체로 넓힌다. 세션 쿠키가 없으면 `/login?next=…`로 보낸다.
  - 제외 경로: `/login`, `/signup`, `/internal/*`, `/_next/*`, `/icon.svg`, `/favicon.ico`, §6-2에서 공개로 정한 피드.
  - 이 버전의 matcher 문법은 `node_modules/next/dist/docs/`에서 먼저 확인한다(`AGENTS.md`).
- `lib/session.ts`: `currentUser()`(React `cache`), `requireUser(next?)`, `requireAdmin()`을 둔다. `requireAdmin()`은 역할이 admin이 아니면 403 화면을 보여 준다. `must_change_password`면 `/account/password`로 보낸다. 콘솔의 기존 `requireAdmin()` 호출 18곳은 시그니처를 유지한다.
- `app/(reader)/layout.tsx`에서 `requireUser()`를 호출한다. 데이터를 내주는 라우트 핸들러(`radar/[period]/[key]/companies`, `.../topic`)에도 같은 검사를 넣는다(실패 시 401).
- 독자 페이지는 동적 렌더링이 된다. API 응답은 데이터 캐시에 남아 API 부하는 늘지 않고, 요청마다 세션 확인이 1회 는다. 배포 전후 첫 화면 응답 시간을 비교해 기록한다.

### 3-4. 웹: 화면

| 경로 | 내용 |
|---|---|
| `/login` | 아이디·비밀번호, "회원가입" 링크. 승인 대기 계정은 비밀번호가 맞을 때 **"승인 대기 중입니다. 관리자에게 승인을 요청하세요."**, 거절·정지 계정은 "로그인할 수 없는 계정입니다. 관리자에게 문의하세요." |
| `/signup` | 아이디, 비밀번호·비밀번호 확인, **이름**, 개인정보 수집 동의, 허니팟. 입력 오류(아이디 형식·중복, 비밀번호 규칙)는 칸 옆에 표시. 완료 후 "가입 신청이 접수되었습니다. 관리자에게 승인을 요청하세요. 승인 후 로그인할 수 있습니다." |
| `/account` | 아이디·이름, 비밀번호 변경(현재 비밀번호 필요), 다른 기기 모두 로그아웃 |
| `/account/password` | 임시 비밀번호로 들어온 경우 변경을 강제 |
| `/console/users` | 탭 3개: 승인 대기(개수 배지), 사용자, 거절. 승인·거절, 정지·재활성, 역할 변경, 비밀번호 초기화(임시 비밀번호를 한 번만 표시), 잠금 해제, 사용자별 감사 로그. 사이드바에 메뉴를 추가하고 대시보드에 승인 대기 배지를 단다 |
| 헤더 | 독자 헤더 우측 계정 메뉴: 이름 표시, 내 계정, 콘솔(admin만), 로그아웃 |

- 가입 아이디 중복 확인은 아이디 존재 여부를 알려 주지만, 가입에 꼭 필요하므로 요청 제한(§2-4)으로 완화한다.
- 새 가입 신청 알림: 관리자에게 운영 알림 메일 1통(기존 `send_email`, SMTP 미설정이면 생략) + 콘솔 배지. → §6-3.

### 3-5. 피드·오디오

`/feed.xml`, `/podcast.xml`은 구독 앱이 로그인을 못 한다. 기본안은 **공개 유지**이고, 브리핑 제목·요약은 로그인 없이 보인다는 점을 런북에 적는다. 오디오 파일(`/media/briefings/*.m4a`)도 Caddy가 직접 서빙하므로 공개 상태로 남는다. → §6-2.

### 3-6. 배포 전환 순서

1. 마이그레이션 후 `news-insight users create-admin <id> --name <이름>`으로 관리자 계정을 먼저 만든다. 이게 없으면 전환 후 아무도 못 들어간다. `scripts/check-env.sh`에 "활성 관리자 계정 존재" 확인을 추가한다.
2. 웹을 배포한다. 기존 `ni_admin` 쿠키는 무효가 되므로 관리자는 새 아이디로 다시 로그인한다.
3. Caddy 설정(HTTP→HTTPS 리다이렉트, 로그인·가입 rate limit zone)을 반영한다.
4. 운영 사이트에서 직접 확인한다:
   - 세션 없이 접근하면 막힌다.
   - 가입 → 승인 요청 안내 → 승인 → 로그인이 된다.
   - 5회 실패하면 잠긴다.
   - HTTP로 접속하면 HTTPS로 넘어간다.

## 4. 테스트

| 층 | 내용 |
|---|---|
| pytest | 해시가 Argon2id이고 평문이 DB에 없음, 재해시; 정책(길이·흔한 비밀번호·아이디 포함); 가입 시 이름 필수·`pending`; 상태별 로그인 결과(`pending`은 비밀번호가 맞을 때만 403 `pending`); 없는 아이디와 틀린 비밀번호가 같은 응답; 5회 실패 잠금과 해제; 요청 제한; 세션 유휴·절대 만료; 비밀번호 변경·정지·역할 변경 시 세션 전부 폐기; 관리자 라우트가 reader 세션을 거부; 마지막 관리자 보호; 승인 대기 상한·허니팟; 감사 로그 기록 |
| vitest | `next` 경로 검증(`//evil`, `/\evil`, 절대 URL, 빈 값), proxy 제외 목록 |
| Playwright | 세션 없이 → `/login?next=…` → 로그인 후 복귀; 가입(이름 포함) → 로그인 시 "관리자에게 승인을 요청하세요" → 관리자가 승인 → 로그인 성공; reader가 `/console`에 들어가면 거부; 비밀번호 초기화 → 변경 강제; 로그아웃; 레이더 라우트 핸들러 무세션 401 |
| 기존 E2E | `globalSetup`에서 CLI로 admin·reader 계정을 만들고 로그인해 `storageState`를 저장한다. `reader.spec.ts`는 reader, `admin.spec.ts`는 admin 상태로 돌린다. 매직링크 테스트(`loginLink`)는 삭제한다 |
| 보안 점검 | PR 4 전에 `/security-review`로 변경분을 검토하고, `curl`로 쿠키 속성과 HTTP 리다이렉트를 확인한다 |

검증: `scripts/dev.sh verify`, `scripts/dev.sh web-e2e`.

## 5. 작업 순서 (PR 단위)

1. **PR 1 — API 사용자·세션**
   - 범위: §3-1, §3-2. 매직링크와 잠시 병존한다.
   - 확인: pytest, CLI로 관리자 생성 후 로그인 API 호출.
2. **PR 2 — 웹 로그인·회원가입·가드·계정 화면**
   - 범위: §3-3, §3-4 중 `/console/users` 제외.
   - 확인: E2E 세션 없음 차단, 가입, 승인 요청 안내.
3. **PR 3 — 관리자 승인 화면**
   - 범위: `/console/users`, 감사 로그 보기, 신청 알림.
   - 확인: E2E 가입 → 승인 → 로그인, reader의 콘솔 접근 거부.
4. **PR 4 — 정리·운영**
   - 범위: 매직링크 코드·`admin_tokens` 삭제, Caddy(HTTP→HTTPS, rate limit), `check-env.sh`, 문서. 문서는 `docs/runbooks/reader-web.md`의 "로그인 없이 누구나" 수정, `ops-console.md`에 사용자 관리·복구 절차, `README.md`, 로드맵 D21을 대체하는 결정 항목.
   - 확인: 운영 배포 후 §3-6 4번 체크리스트.

## 6. 확인 필요 (기본안으로 진행)

1. **HTTP 포트** — 기본안: HTTP(8701)를 HTTPS(8700)로 리다이렉트. 비밀번호가 평문으로 오가지 않게 하려는 것이다.
2. **RSS·팟캐스트 피드** — 기본안: 공개 유지. 구독 앱은 그대로 동작하지만 제목·요약은 공개된다.
3. **가입 신청 알림** — 기본안: 콘솔 배지 + 운영 알림 메일(SMTP가 설정된 경우).
4. **관리자 2단계 인증(OTP)** — 기본안: 이번 범위에서 제외하고 후속 작업으로 둔다.
