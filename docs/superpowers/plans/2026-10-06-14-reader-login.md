# 사이트 로그인 — 아이디/비밀번호, 가입 신청 → 관리자 승인

> 요청(2026-10-06): "기본 페이지 로그인을 위한 내용을 개발 계획 세워주세요."
> 변경(2026-10-07): "이메일 토큰 방식이 아니라 id/pw 로그인 방식으로 변경 … 보안을 고려해서 … 가입 신청 후 admin이 승인한 사용자만 접근이 가능하도록."
> 실행 규칙은 [10-execution-progress](2026-10-04-10-execution-progress.md)와 같다(브랜치 → verify → PR → CI → 병합 → `NEWS_INSIGHT-live/scripts/deploy.sh`).

## 0. 목표

- 독자 화면 전체(`/` 탐색, `/briefings`, `/radar`, `/digests`, `/items`)와 콘솔(`/console`)을 **아이디/비밀번호 로그인** 뒤로 옮긴다.
- 누구나 **가입 신청**은 할 수 있지만, **관리자가 승인한 계정만** 로그인된다. 승인 전·거절·정지 계정은 어떤 화면도 열 수 없다.
- 역할은 둘: `reader`(독자 화면), `admin`(독자 화면 + 콘솔 + 사용자 관리).
- 이메일 매직링크 로그인(P8, D21)은 **없앤다**. SMTP는 운영 알림 메일(`mailer.send_email`)에만 남는다.

### 완료 기준

1. 세션 없이 어떤 화면을 열어도 `/login?next=…`로 간다. 서버가 세션을 매번 검증한다(쿠키만 보고 통과시키지 않음).
2. 가입 신청 → `pending` → 관리자가 `/console/users`에서 승인 → 로그인 가능. 거절·정지 계정과 승인 전 계정은 로그인되지 않는다.
3. 비밀번호는 Argon2id 해시로만 저장. 평문·되돌릴 수 있는 형태는 DB·로그 어디에도 없다.
4. 무차별 대입이 계정·IP 양쪽에서 막히고, 응답으로 아이디 존재 여부를 알 수 없다(가입 화면의 아이디 중복 확인은 예외, §3-4).
5. 비밀번호 변경·초기화·정지·역할 변경 시 그 사용자의 기존 세션이 모두 끊긴다.
6. 로그인·가입·승인 등 인증 이벤트가 감사 로그에 남는다.
7. 기존 E2E가 로그인 상태로 통과하고, 가입~승인~로그인 E2E가 추가된다.

## 1. 현재 상태 (출발점)

- **API** `apps/api/src/news_insight/auth/`: `admin_email` 한 주소만 매직링크를 받는다. 토큰은 `admin_tokens` 테이블에 SHA-256 해시로 저장(`login` 15분 1회용, `session` 14일). 링크 발급 제한은 전체 15분 5회.
- **경계**: `/api/admin/*`, `/api/public/*`은 Caddy가 외부에서 404로 막는다. 웹 서버만 내부망에서 `X-Console-Key` / `X-Public-Key`로 부른다. **인증 API도 이 경계 안에 둔다.**
- **웹** (Next 16.3): `proxy.ts`가 `ni_admin` 쿠키가 없으면 `/console*`을 `/login`으로 보내고, `lib/session.ts`의 `requireAdmin()`이 API로 세션을 검증한다(콘솔 레이아웃·액션·라우트 18곳).
- **독자 화면**: 로그인 없음. 데이터는 `PUBLIC_API_KEY`로 받아 Next 데이터 캐시(`tags: ["reader"]`)에 둔다.
- **평문 HTTP**: 2026-10-06부터 HTTP 포트(8701)도 같은 사이트를 서빙한다. 그대로 두면 **비밀번호가 평문으로 네트워크를 지난다**(§2-1).

## 2. 보안 설계

### 2-1. 전송 구간 — HTTPS 필수

비밀번호를 받는 순간부터 HTTP는 허용할 수 없다. 권장안은 **HTTP 포트를 HTTPS로 다시 리다이렉트**하는 것(2026-10-06 이전 동작으로 복귀)이다. HTTP 접속을 꼭 유지해야 하면 최소한 `/login`, `/signup`, `/account`, 서버 액션 요청은 HTTPS로 보내고, 세션 쿠키는 `Secure`로만 발급한다(그러면 HTTP에서는 로그인 상태가 유지되지 않는다). → §6-1 결정.

HTTPS 전용이 되면 HSTS(`max-age=31536000`)를 다시 켜고, 세션 쿠키 이름에 `__Host-` 접두사를 쓴다.

### 2-2. 비밀번호 저장

- **Argon2id** (`argon2-cffi`, 새 의존성 1개). 파라미터는 OWASP 권장 하한 이상: memory 19 MiB, time 2, parallelism 1에서 시작해 운영 서버에서 한 번 검증 시간이 0.2~0.5초가 되도록 맞춘다. 파라미터는 해시 문자열에 들어 있으므로, 로그인 성공 시 `check_needs_rehash`로 자동 갱신한다.
- 해시 계산은 이벤트 루프를 막지 않게 동기 라우트(스레드풀)에서 한다(FastAPI `def` 라우트, 기존 auth 라우트와 같은 형태).

### 2-3. 비밀번호 정책 (NIST SP 800-63B 기준)

- 길이 10~128자. 조합 규칙(대문자·특수문자 강제)과 주기적 변경 강제는 두지 않는다.
- 거부: 흔한 비밀번호 목록(상위 10만 개, 저장소에 파일로 포함 — 외부 API 호출 없음), 아이디·이름이 들어간 비밀번호, 같은 문자 반복.
- 화면에 강도 표시와 거부 이유를 보여 준다. 붙여넣기·비밀번호 관리자 허용(`autocomplete="new-password"` / `"current-password"`).

### 2-4. 무차별 대입·열거 방지

| 장치 | 규칙 |
|---|---|
| 계정 잠금 | 연속 실패 5회 → 15분 잠금, 이후 실패마다 잠금 시간 2배(최대 24시간). 성공하면 초기화. 잠금 중에도 응답은 일반 실패와 같다 |
| IP 제한 | API에서 Redis로 IP당 로그인 10회/분, 가입 신청 3회/시간. 웹이 Caddy가 붙인 `X-Forwarded-For`의 클라이언트 IP를 `X-Client-IP`로 넘긴다(외부 요청은 Caddy만 거치므로 신뢰 가능) |
| Caddy | `/login`, `/signup` 경로에 별도 `rate_limit` zone(분당 20) |
| 열거 방지 | 로그인 실패 메시지는 하나: "아이디 또는 비밀번호가 올바르지 않습니다". 없는 아이디에도 더미 해시로 Argon2 검증을 돌려 응답 시간을 맞춘다 |
| 상태 노출 | `pending`·`rejected`·`suspended`는 **비밀번호가 맞을 때만** 알려 준다("승인 대기 중입니다" 등). 비밀번호가 틀리면 일반 실패와 같다 |

### 2-5. 세션

- 로그인 성공 시 새 토큰(`secrets.token_urlsafe(32)`)을 발급하고 SHA-256 해시만 저장한다(지금 방식 유지). 로그인 전 쿠키는 재사용하지 않는다(세션 고정 방지).
- 쿠키: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`. 절대 만료 14일, 유휴 만료 3일(마지막 사용 기준, `last_seen_at`).
- 비밀번호 변경·초기화, 정지, 역할 변경, 거절 시 그 사용자의 세션을 **전부 폐기**. 본인 비밀번호 변경 시 현재 세션만 새로 발급.
- `/account`에서 "다른 기기 모두 로그아웃".
- 세션 확인 응답에 `user_id`, `username`, `role`, `must_change_password`를 담는다. 웹은 이 값으로만 권한을 판단한다.

### 2-6. CSRF·리다이렉트

- 로그인·가입·로그아웃·승인 등 모든 변경은 **Server Actions**(POST)로 한다. Next가 `Origin`과 `Host`를 비교해 다른 출처 요청을 거부한다. GET으로 상태를 바꾸는 경로는 만들지 않는다.
- `next` 파라미터는 `/`로 시작하고 `//`·`/\`로 시작하지 않는 같은 출처 경로만 허용(오픈 리다이렉트 방지).

### 2-7. 가입 남용 방지

- 가입 신청 폼에 허니팟 필드, IP 제한(§2-4), `pending` 계정 상한(기본 50개 — 넘으면 "지금은 신청을 받을 수 없습니다").
- 거절된 신청은 30일 뒤, 승인되지 않은 `pending`은 90일 뒤 자동 삭제(기존 정리 작업에 추가).

### 2-8. 개인정보

- 받는 항목은 최소로: 아이디, 비밀번호, 이름, 소속·신청 사유(관리자가 승인 판단에 쓰는 자유 입력). 이메일은 받지 않는다(메일로 하는 일이 없으므로). → §6-3.
- 가입 화면에 수집 항목·목적(접근 승인 판단)·보관 기간(탈퇴·거절 시 삭제)을 적고 동의 체크를 받는다.
- 로그·감사 로그에 비밀번호, 세션 토큰, 원문 요청 본문을 남기지 않는다.

### 2-9. 감사 로그

`auth_events` 테이블: `at`, `event`(signup, login_ok, login_fail, locked, logout, approve, reject, suspend, reactivate, role_change, password_change, password_reset), `user_id`, `actor_id`(관리자 조치일 때), `ip`, `user_agent`(200자). 180일 보관. 콘솔에서 사용자별로 본다.

## 3. 구현

### 3-1. 데이터 모델 (마이그레이션 `0028_users`)

`users`

| 필드 | 뜻 |
|---|---|
| `id` | PK |
| `username` | 4~32자, `[a-z0-9._-]`, 소문자로 정규화, unique |
| `password_hash` | Argon2id 문자열 |
| `display_name`, `note` | 이름, 소속·신청 사유(500자) |
| `role` | `reader` · `admin` |
| `status` | `pending` · `active` · `rejected` · `suspended` |
| `must_change_password` | 관리자 초기화 후 첫 로그인 시 변경 강제 |
| `failed_count`, `locked_until` | 계정 잠금(§2-4) |
| `created_at`, `approved_at`, `approved_by`, `last_login_at`, `password_changed_at` | |

`user_sessions`: `id`, `user_id`(FK, cascade), `token_hash`(unique), `created_at`, `expires_at`, `last_seen_at`, `revoked_at`, `ip`, `user_agent`.

`auth_events`: §2-9.

`admin_tokens`는 전환이 끝난 뒤 PR 4에서 삭제한다.

### 3-2. API (`apps/api/src/news_insight/auth/`)

- `passwords.py`: 해시·검증·재해시, 정책 검사(흔한 비밀번호 목록 `catalog/common-passwords.txt`).
- `service.py`를 사용자 기반으로 다시 쓴다: `register`, `authenticate`(잠금·더미 검증 포함), `issue_session`, `check_session`, `revoke_session(s)`, `change_password`, 관리자 조치 `approve`/`reject`/`suspend`/`reactivate`/`set_role`/`reset_password`(임시 비밀번호를 한 번만 돌려주고 `must_change_password=true`).
- 라우트는 지금처럼 `/api/admin/auth/*`(내부망 + `X-Console-Key`):
  - `POST /signup`, `POST /login`, `POST /session`, `POST /logout`, `POST /logout-all`, `POST /password`
  - 관리자용 `GET /users?status=`, `POST /users/{id}/approve|reject|suspend|reactivate|role|reset-password`, `GET /users/{id}/events`. 관리자 라우트는 요청 본문의 세션 토큰으로 `role == admin`을 **API에서도** 다시 확인한다(웹만 믿지 않음).
- 요청마다 `X-Client-IP`를 받아 IP 제한과 감사 로그에 쓴다.
- CLI: `news-insight users create-admin <username>`(비밀번호는 프롬프트로 두 번 입력, 인자·환경 변수로 받지 않음), `users list`, `users reset-password <username>`, `users unlock <username>`. 마지막 관리자를 정지·강등할 수 없게 막는다(관리자가 모두 잠기면 CLI로 복구).
- `admin link` 명령과 매직링크 코드(`mailer.login_url`, `build_message`, `send_login_link`)는 PR 4에서 삭제. `admin_email`은 운영 알림 수신 주소로만 남는다.

### 3-3. 웹: 가드 (`apps/web`)

- `proxy.ts`: matcher를 사이트 전체로 넓히고, 세션 쿠키가 없으면 `/login?next=…`. 제외: `/login`, `/signup`, `/internal/*`, `/_next/*`, `/icon.svg`, `/favicon.ico`, §6-2에서 공개로 정한 피드. 이 버전의 matcher 문법은 `node_modules/next/dist/docs/`에서 먼저 확인한다(`AGENTS.md`).
- `lib/session.ts`: `currentUser()`(React `cache`), `requireUser(next?)`, `requireAdmin()`(역할이 admin이 아니면 403 화면). `must_change_password`면 `/account/password`로 보낸다.
- `app/(reader)/layout.tsx`에서 `requireUser()`. 레이아웃은 클라이언트 이동 때 다시 실행되지 않을 수 있으므로 데이터를 내주는 라우트 핸들러(`radar/[period]/[key]/companies`, `.../topic`)에도 같은 검사(실패 시 401).
- 콘솔의 기존 `requireAdmin()` 호출 18곳은 시그니처를 유지해 그대로 쓴다.
- `cookies()`를 읽으면 독자 페이지가 동적 렌더링이 된다. API 응답은 데이터 캐시에 남으므로 API 부하는 늘지 않고, 요청마다 세션 확인 1회가 는다. 배포 전후 첫 화면 응답 시간을 비교해 기록한다.

### 3-4. 웹: 화면

| 경로 | 내용 |
|---|---|
| `/login` | 아이디·비밀번호, "가입 신청" 링크. 상태별 안내(승인 대기·거절·정지)는 비밀번호가 맞을 때만 |
| `/signup` | 아이디(중복 확인 — 열거가 되지만 가입에 꼭 필요하므로 IP 제한으로 완화), 비밀번호·확인, 이름, 소속·사유, 개인정보 동의, 허니팟. 완료 후 "관리자 승인 후 로그인할 수 있습니다" |
| `/account` | 내 정보, 비밀번호 변경(현재 비밀번호 필요), 다른 기기 모두 로그아웃 |
| `/account/password` | 임시 비밀번호로 들어온 경우 변경 강제 |
| `/console/users` | 탭: 승인 대기(개수 배지) · 사용자 · 거절. 승인/거절, 정지/재활성, 역할 변경, 비밀번호 초기화(임시 비밀번호를 한 번만 표시), 잠금 해제, 사용자별 감사 로그. 사이드바에 메뉴 추가 |
| 헤더 | 독자 헤더 우측에 계정 메뉴(내 계정, 콘솔 — admin만, 로그아웃) |

- 신청이 들어오면 관리자에게 운영 알림 메일 1통(기존 `send_email`, SMTP 미설정이면 생략) + 콘솔 대시보드 배지. → §6-4.

### 3-5. 피드·오디오

`/feed.xml`, `/podcast.xml`은 구독 앱이 로그인을 못 하므로 §6-2 결정에 따른다. 공개로 두면 브리핑 제목·요약은 로그인 없이 보인다는 점을 런북에 적는다. 토큰으로 막으려면 사용자별 피드 토큰(`/account`에서 발급·재발급)과 Caddy `@audio` 경로의 토큰 검사가 함께 필요하다.

### 3-6. 배포 전환 순서

1. 마이그레이션 → `news-insight users create-admin <id>`로 관리자 계정을 먼저 만든다(이게 없으면 전환 후 아무도 못 들어간다). `scripts/check-env.sh`에 "관리자 계정 존재" 확인 추가.
2. 웹 배포 → 기존 `ni_admin` 쿠키는 무효가 되므로 관리자는 새 아이디로 다시 로그인.
3. Caddy 설정(HTTPS 리다이렉트·HSTS·rate limit zone) 반영.
4. 운영 사이트에서 직접 확인: 무세션 접근 차단, 가입 신청 → 승인 → 로그인, 5회 실패 잠금, 로그아웃 후 뒤로 가기로 화면이 안 보이는지.

## 4. 테스트

| 층 | 내용 |
|---|---|
| pytest | 해시가 Argon2id이고 평문이 DB에 없음, 재해시; 정책(길이·흔한 비밀번호·아이디 포함); 상태별 로그인 결과(`pending`/`rejected`/`suspended`는 비밀번호가 맞을 때만 구분); 없는 아이디와 틀린 비밀번호가 같은 응답; 5회 실패 잠금과 해제; IP 제한; 세션 유휴·절대 만료; 비밀번호 변경·정지·역할 변경 시 세션 전부 폐기; 관리자 라우트가 reader 세션을 거부; 마지막 관리자 보호; pending 상한·허니팟; 감사 로그 기록 |
| vitest | `next` 경로 검증(`//evil`, `/\evil`, 절대 URL, 빈 값), proxy 제외 목록, 비밀번호 강도 표시 |
| Playwright | 무세션 → `/login?next=…` → 로그인 후 복귀; 가입 신청 → 로그인 시 "승인 대기" → 관리자가 승인 → 로그인 성공; reader가 `/console` 접근 시 거부; 비밀번호 초기화 → 변경 강제; 로그아웃; 레이더 라우트 핸들러 무세션 401 |
| 기존 E2E | `globalSetup`에서 CLI로 admin·reader 계정을 만들고 로그인해 `storageState` 저장. `reader.spec.ts`는 reader, `admin.spec.ts`는 admin 상태로 실행. 매직링크 테스트(`loginLink`)는 삭제 |
| 보안 점검 | PR 3 전에 `/security-review`로 변경분 검토, `curl`로 쿠키 속성·HTTP 리다이렉트 확인 |

검증: `scripts/dev.sh verify`, `scripts/dev.sh web-e2e`.

## 5. 작업 순서 (PR 단위)

1. **PR 1 — API 사용자·세션** (§3-1, §3-2, 매직링크와 병존) → 확인: pytest, CLI로 관리자 생성·로그인 API 호출.
2. **PR 2 — 웹 로그인·가입·가드·계정 화면** (§3-3, §3-4 중 `/console/users` 제외) → 확인: E2E 무세션 차단·가입·로그인.
3. **PR 3 — 관리자 승인 화면** (`/console/users`, 감사 로그 보기, 신청 알림) → 확인: E2E 가입→승인→로그인, reader 콘솔 거부.
4. **PR 4 — 정리·운영** 매직링크 코드·`admin_tokens` 삭제, Caddy(HTTPS·HSTS·rate limit), `check-env.sh`, 문서(`docs/runbooks/reader-web.md` "로그인 없이 누구나" 수정, `ops-console.md` 사용자 관리·복구 절차, `README.md`, 로드맵 D21을 대체하는 결정 항목) → 확인: 운영 배포 후 §3-6 4번 체크리스트.

## 6. 결정 필요

1. **평문 HTTP** — (a) HTTP를 HTTPS로 리다이렉트(권장, 비밀번호가 평문으로 오가지 않음) (b) HTTP 접속은 두되 로그인 상태는 HTTPS에서만 유지.
2. **RSS·팟캐스트 피드** — (a) 공개 유지(구독 앱이 그대로 동작, 제목·요약은 공개) (b) 사용자별 토큰 URL (c) 피드 제거.
3. **가입 항목** — 아이디·비밀번호·이름·소속/사유로 충분한지, 이메일도 받을지(받으면 승인 결과 알림 메일을 보낼 수 있지만 개인정보가 는다).
4. **신청 알림** — 새 가입 신청을 관리자에게 메일로 알릴지, 콘솔 배지만으로 충분한지.
5. **2단계 인증(TOTP)** — 관리자 계정에 OTP 앱 인증을 추가할지. 이번 범위에서는 제외하고 후속 작업으로 두는 것을 권장.
