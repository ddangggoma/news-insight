# 수집 자동화 · 한국어 카드 뉴스 런북 (Phase 3.6)

공개 RSS·API 소스가 사람 손을 거치지 않고 수집되기 시작하는 과정과, 모든 수집 항목이 한국어 카드로 정리되는 과정을 설명합니다.

## 1. 전체 흐름

```
카탈로그(sources.yaml, 1,000+) ──seed──▶ 운영 DB(후보)
   │
   ▼  sources.auto_validate (Celery, 10분마다 100개)
V0 정체성 → V1 자동 승인(robots.txt·자격 증명) → V2 네트워크 → V3 실제 수집 3건 이상
   │
   ▼  collect.dispatch_due (1분마다)            sources.run_canaries (1시간마다)
V3 이상 소스를 주기적으로 수집(Canary) ─────────▶ 24시간 관찰 후 V4 판정
   │
   ▼  호스트 launchd (10분마다) scripts/dev.sh cards
신규·변경 항목 → Antigravity CLI(Gemini Flash, 100건 배치) ─ 한도 소진·오류 ─▶ 로컬 Qwen(5건 배치)
   │
   ▼
item_cards (한국어 제목·요약 1~3문장·키워드) → 콘솔 "카드 뉴스"
```

## 2. 처음 한 번 할 일

### 2-1. 카탈로그를 운영 DB에 등록

```bash
scripts/dev.sh sources-seed
```

- 출력 예: `created=1093 updated=0 reset=0`
- 이미 있는 소스는 설명 필드만 갱신합니다. 엔드포인트가 바뀐 소스만 검증을 처음부터 다시 합니다.

### 2-2. 최신 코드로 컨테이너 재시작

```bash
docker compose up -d --build
```

자동 검증 잡(`sources.auto_validate`)은 scheduler·worker 컨테이너에서 돕니다. 첫 바퀴(1,000개 이상)를 도는 데 약 2시간이 걸립니다. 바로 시작하려면 아래 명령을 실행합니다.

```bash
cd apps/api && uv run --env-file ../../.env news-insight sources auto-validate --limit 200
```

### 2-3. 카드 자동 생성 등록 (호스트 launchd, 10분마다)

```bash
scripts/install-card-schedule.sh
```

- Mac 로그인 상태에서 `agy`(Antigravity CLI)와 LM Studio를 사용합니다.
- 해제:

```bash
launchctl bootout gui/$(id -u)/com.newsinsight.cards
```

### 2-4. GitHub 소스 활성화 (선택)

`.env`에 `SOURCE_SECRET_GITHUB_TOKEN=`을 직접 채우고 `docker compose up -d`를 실행합니다. 다음 자동 검증 때 GitHub 소스들이 V1을 통과합니다.

## 3. V1 자동 승인 규칙 (D17)

| 조건 | 결과 |
|---|---|
| `terms_url`이 있는 소스 | 기존 수동 검토 규칙(check_policy) 적용 |
| 크롤러(HTML) 소스, `config.manual_review: true` | 자동 승인 안 함 — 약관 검토 필요 |
| robots.txt가 엔드포인트를 막음 | 실패 (이유가 검증 이력에 남음) |
| robots.txt 없음(4xx) | 허용 |
| robots.txt 서버 오류·접속 불가 | 실패, 24시간 뒤 재시도 |
| 필요한 자격 증명(`SOURCE_SECRET_*`)이 없음 | 실패 |
| 통과 | 저장 등급을 `excerpt_allowed`(발췌 500자)로 설정 |

검증 이력(콘솔 → 소스 → 상세 → 검증 이력)에서 `auto_approved`와 robots 판단 근거를 확인할 수 있습니다.

## 4. 한국어 카드 규칙 (D18)

- **대상:** 수집된 모든 항목. 항목 내용이 바뀌면(content_hash) 카드를 다시 만듭니다.
- **카드 내용:** 한국어 제목, 발췌가 있을 때만 요약 1~3문장, 키워드 2~4개, 출처와 원문 링크.
  - 발췌가 없는 항목에 엔진이 요약을 써 오면 버립니다(지어낸 내용 방지).
- **엔진 선택:**
  1. Antigravity CLI(`gemini-3.8-flash-low`)로 100건씩 처리합니다.
  2. 배치마다 `agy /usage`로 Gemini 한도를 확인합니다. 주간 남은 한도가 10% 이하이거나 5시간 남은 한도가 2% 이하이면 로컬 Qwen으로 바꿉니다. 주간 한도의 90%까지만 카드에 쓰는 셈입니다.
  3. Antigravity가 한도 초과·오류를 내면 그 실행의 남은 시간은 Qwen으로 처리합니다.
  4. Qwen(LM Studio)이 꺼져 있으면 항목을 대기 상태로 두고, 다음 실행에서 다시 시도합니다.
- **실패:** 엔진 출력에서 빠진 항목은 최대 3회 다시 시도하고, 그래도 실패하면 원래 제목으로 표시합니다.
- **안전:** 도구 권한 없이(헤드리스 모드에서 자동 거부) 빈 임시 폴더에서 실행합니다. 비밀 환경 변수는 넘기지 않고 슬래시 명령도 끕니다. 엔진에는 공개 제목·출처·발췌만 보냅니다.

## 5. 처리량 (2026-10-04 실측)

| 엔진 | 속도 | 하루 최대 |
|---|---|---|
| Antigravity (Gemini 3.8 Flash Low) | 100건 약 60초 | 한도에 따라 약 8,000~16,000건(추정). 100건마다 5시간 한도 약 1%p 사용 |
| 로컬 Qwen 3.8 27B (추론 끔) | 카드당 약 20초 | 약 4,000건 |

10분 실행마다 시간 예산은 540초입니다(`CARD_TIME_BUDGET_SECONDS`). 겹치는 실행은 잠금 파일로 건너뜁니다.

## 6. 점검 명령

```bash
cd apps/api
uv run --env-file ../../.env news-insight cards status                   # 대기·완료·실패·마지막 실행
LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file ../../.env news-insight cards run --budget 120
uv run --env-file ../../.env news-insight cards run --qwen-only          # Antigravity 없이 시험
uv run --env-file ../../.env news-insight sources report                 # 단계별 소스 수
```

- 카드 실행 로그: `ops/logs/cards.log`
- 콘솔: 카드 뉴스 화면 상단에 오늘 만든 카드, 대기, 엔진별 수, Antigravity 남은 한도(주간·5시간)가 표시됩니다.

## 7. 문제 해결

| 증상 | 조치 |
|---|---|
| 카드 대기가 줄지 않음 | `ops/logs/cards.log` 확인. `agy -p /usage`로 로그인·한도 확인. LM Studio 서버 실행 여부 확인 |
| 모든 카드가 Qwen으로 만들어짐 | Antigravity 한도가 기준 아래. `/usage`가 다시 차면 자동으로 Antigravity로 돌아감 |
| 소스가 V1에서 계속 실패 | 검증 이력의 이유 확인. robots.txt가 막으면 수동 검토(`terms_url`)로 전환하거나 제외 |
| GitHub 소스가 모두 V1 실패 | `SOURCE_SECRET_GITHUB_TOKEN` 미설정 (2-4 참고) |
