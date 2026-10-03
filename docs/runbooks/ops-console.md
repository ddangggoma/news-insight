# 운영 콘솔 · 데일리 다이제스트 런북 (Phase 3.5)

운영 콘솔은 수집 상태를 보고 조작하며 수집 항목과 매일 05:00 KST 다이제스트를 열람하는 웹 화면입니다. 이 문서는 처음 설정부터 매일 운영까지 순서대로 설명합니다.

## 1. 구조 한눈에 보기

```
브라우저 ──HTTPS──▶ Caddy(8700) ──▶ web(Next.js) ──내부망 + X-Console-Key──▶ api(/api/admin)
                    │  /console*   : Basic Auth 필요
                    │  /api/admin* : 외부에서는 항상 404
호스트 launchd(05:00) ──▶ scripts/dev.sh digest ──▶ Claude CLI(Opus, 도구 비활성화) ──▶ DB(digests)
```

- 콘솔 API(`/api/admin`)는 웹 서버만 호출합니다. 외부 요청은 Caddy가 404로 막고, API도 `CONSOLE_API_KEY`가 맞지 않으면 401을 돌려줍니다.
- 다이제스트는 Claude CLI 로그인 정보가 있는 **호스트(Mac)** 에서 만듭니다. 컨테이너 안에서는 실행하지 않습니다.

## 2. 처음 설정 (1회)

### 2-1. 콘솔 비밀번호 정하기

```bash
scripts/dev.sh console-password
```

비밀번호를 두 번 입력하면 bcrypt 해시가 `.env`의 `CONSOLE_PASSWORD_HASH`에 저장됩니다. 비밀번호 원문은 어디에도 저장되지 않습니다. 기본 사용자 이름은 `admin`이고, `.env`의 `CONSOLE_USER`로 바꿀 수 있습니다.

> `.env.example`에 들어 있는 기본 해시는 아무도 모르는 무작위 비밀번호의 해시입니다. 이 단계를 하지 않으면 콘솔에 로그인할 수 없습니다.

### 2-2. 콘솔 API 키 확인

`.env`의 `CONSOLE_API_KEY`는 web과 api 컨테이너가 함께 쓰는 내부 키입니다. 길고 무작위인 값이어야 합니다. 바꾸고 싶으면 다음 명령으로 새 값을 만들어 `.env`에 넣습니다.

```bash
openssl rand -hex 32
```

### 2-3. 스택 반영

```bash
docker compose up -d --build
```

### 2-4. 05:00 다이제스트 스케줄 등록

```bash
scripts/install-digest-schedule.sh
```

- `~/Library/LaunchAgents/com.newsinsight.digest.plist`가 만들어지고 매일 05:00(Mac 로컬 시각 = KST)에 `scripts/dev.sh digest`가 실행됩니다.
- Mac이 잠자기 상태이면 깨어난 직후 한 번 실행됩니다(launchd 기본 동작).
- 등록 확인:

```bash
launchctl print gui/$(id -u)/com.newsinsight.digest
```

- 해제:

```bash
launchctl bootout gui/$(id -u)/com.newsinsight.digest
```

## 3. 접속

- 주소: `https://localhost:8700/console` (또는 `PUBLIC_HOST`)
- 브라우저가 사용자 이름과 비밀번호를 물으면 2-1에서 정한 값을 입력합니다.

## 4. 화면별 사용법

| 메뉴 | 용도 | 조작 |
|---|---|---|
| 대시보드 | 오늘의 다이제스트 요약, 활성/후보 소스, 최근 24시간 수집 건강도, 검증 단계 분포, 트랙 목표 대비 활성 수, 지역 용량, 최근 항목, 지표 상승 상위 | — |
| 데일리 다이제스트 | 날짜별 다이제스트 목록과 상세(종합 인사이트 → 트랙 → 하위 범주). 모든 문장에 근거 기사 링크가 붙습니다 | — |
| 소스 | 트랙·지역·단계·상태 필터와 키/이름 검색, 페이지 이동 | 상세에서 **즉시 수집**, **일시정지**(사유 필수), **재개** |
| 수집 현황 | 모든 수집 시도(최신순). 결과·HTTP 상태·신규/변경/동일 건수·지연·오류 | 결과 필터 |
| DLQ | 재시도 3회 후에도 실패했거나 구조 변경·설정 오류로 격리된 수집 | **재시도**(즉시 재수집 예약), **종결** |
| 수집 항목 | 제목 검색(pg_trgm), 트랙·기간 필터. 상세에서 요약·리비전·지표 이력 확인 | — |
| 지표 상승 | 스타·HN 점수·좋아요·반응·인용 수의 기간 내 증가 상위 | 지표·기간·트랙 필터 |

- 오른쪽 위 해/달 버튼으로 라이트/다크 모드를 바꿉니다(기본값은 OS 설정).
- 일시정지된 소스는 DLQ 재시도가 거부됩니다. 먼저 재개하세요.

## 5. 데일리 다이제스트 동작

1. **대상:** 발행일 D의 다이제스트는 D-1일 00:00~24:00 KST에 **처음 수집된** 항목을 다룹니다.
2. **입력 묶음:** 항목을 트랙 → 하위 범주로 묶고, 범주마다 반응 지표와 최신순으로 상위 12건을 고릅니다. 각 항목은 id·제목·출처·지역·발행 시각·요약(최대 280자)·지표만 보냅니다.
3. **생성:** Claude CLI(`DIGEST_MODEL`, 기본 `opus`)가 정해진 JSON 스키마로 답합니다. 실행 조건은 다음과 같습니다.
   - 도구 전부 비활성화(`--tools ""`), MCP 비활성화, 세션 저장 안 함
   - 빈 임시 폴더에서 실행
   - `SOURCE_SECRET_*`, 비밀번호, `DATABASE_URL`, `CONSOLE_API_KEY` 같은 비밀 환경 변수는 넘기지 않음
   - 입력 안의 지시문은 데이터로만 취급하도록 시스템 프롬프트로 고정
4. **근거 검증:** 모든 문장은 입력에 실제로 있는 항목 id를 1개 이상, 종합 인사이트는 서로 다른 id를 2개 이상 가져야 합니다. 조건을 못 채운 문장은 버리고, 남는 내용이 없으면 실패로 처리합니다.
5. **대체본:** Claude가 실패하거나(시간 초과 900초, 오류) 검증에서 떨어지면 **규칙 기반 대체본**(트랙·범주별 상위 제목)을 발행합니다. 콘솔에 "규칙 기반 대체본" 배지와 원인이 표시됩니다. 전날 항목이 0건이면 Claude를 부르지 않습니다.
6. **중복 방지:** 같은 날짜에 같은 입력으로 이미 Claude 요약이 발행됐다면 다시 만들지 않습니다. 입력이 바뀌면 버전(v2, v3…)이 올라가고, 콘솔은 최신 버전을 보여 줍니다.

## 6. 수동 실행과 로그

- 오늘 날짜(KST)로 지금 바로 생성:

```bash
scripts/dev.sh digest
```

- 특정 발행일로 생성:

```bash
cd apps/api && uv run --env-file ../../.env news-insight digest run --date 2026-10-04
```

- 출력 예: `2026-10-04 v1 published items=1204 model=claude-opus-4-8 cost=$0.221`
- launchd 실행 로그: `ops/logs/digest.log`

## 7. 비용과 사용량

- 실측: 전날 1,204건(Claude에는 범주별 상위 항목만 전달) → Opus 1회 약 $0.22, 약 90초.
- 실행마다 비용(`cost_usd`)과 실제 모델명이 `digests` 테이블에 저장되고, 콘솔 다이제스트 상세 상단에도 표시됩니다.
- 비용을 줄이려면 `.env`에서 `DIGEST_MODEL=sonnet`으로 바꿉니다.

## 8. 화면 점검용 데모 데이터

실제 운영 DB를 건드리지 않고 화면을 확인하려면 별도 DB(`news_insight_demo`)를 만듭니다.

```bash
scripts/demo-db.sh
```

- 시드 후 소스 35개를 V3로 올려 실제로 두 번 수집합니다. GitHub 토큰이 없으면 GitHub 소스 2개는 설정 오류로 DLQ에 들어갑니다(오류 화면 확인용).
- 데모 DB로 다이제스트를 만들고 개발 서버(8711/8710)를 이 DB에 연결해 화면을 확인합니다.

## 9. 문제 해결

| 증상 | 원인과 조치 |
|---|---|
| `/console`에서 계속 로그인 창이 뜸 | 비밀번호 불일치. `scripts/dev.sh console-password` 후 `docker compose up -d caddy` |
| 콘솔에 "데이터를 불러오지 못했습니다 … 401" | web과 api의 `CONSOLE_API_KEY`가 다름. `.env` 확인 후 `docker compose up -d` |
| "CONSOLE_API_KEY is not configured" | web 컨테이너에 키가 없음. `.env`에 값을 넣고 재기동 |
| 다이제스트가 계속 대체본 | `ops/logs/digest.log`와 콘솔의 오류 문구 확인. `claude -p "hi"`로 CLI 로그인 상태 확인 |
| 05:00에 실행되지 않음 | `launchctl print gui/$(id -u)/com.newsinsight.digest`로 등록 상태와 마지막 종료 코드 확인 |
