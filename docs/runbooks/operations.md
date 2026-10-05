# 운영 런북 (Phase 9)

매일 무인으로 돌아가는 일정, 알림을 받았을 때의 대응, 백업·복구·릴리스·롤백 절차를 모았습니다. 콘솔 사용법은 [ops-console.md](ops-console.md), 수집·카드는 [cards-and-collection.md](cards-and-collection.md), 독자 화면은 [reader-web.md](reader-web.md)를 보세요.

## 1. 하루 일정 (KST)

| 시각 | 무엇 | 어디서 |
|---|---|---|
| 매분 | 수집 대상 배정 | Celery beat → worker |
| 5분마다 | 이슈 묶음, **운영 점검**(`ops.check`) | Celery |
| 10분마다 | 소스 자동 검증, 한국어 카드 생성 | Celery / 호스트 launchd(`com.newsinsight.cards`) |
| 03:00 | 암호화 백업 | 호스트 launchd(`com.newsinsight.backup`, 설치 시) |
| 03:15 | 만료 본문 삭제 + 지표 스냅샷 솎기(30일 지나면 항목·일당 1개, 180일 지나면 항목·주당 1개, 항목의 첫 스냅샷은 유지 — DATA-1) | Celery |
| 03:30 | V5/V6 소스 품질 판정 | Celery |
| 04:40 | 후보 동결 + 레이더 신호 저장(`radar_signals`, 이번 주·지난주 카드) | Celery |
| 05:00 | 다이제스트 → 페르소나·전략 → 게이트 → 발행 | 호스트 launchd(`com.newsinsight.digest`) |

## 2. 운영 알림

콘솔 → **운영 알림**(`/console/alerts`)과 콘솔 상단 띠에 표시됩니다. SMTP를 설정하면(ops-console.md §2-1) 새 긴급·주의 알림이 관리자 메일로 갑니다. 지금 상태는 `cd apps/api && uv run --env-file ../../.env news-insight ops check`로도 볼 수 있습니다.

| 키 | 수준 | 뜻 | 대응 |
|---|---|---|---|
| `freeze_missing` | 긴급 | 04:55까지 동결 없음 | `docker compose ps`로 scheduler·worker 확인 → `docker compose restart scheduler worker`. 05:00 발행 작업이 동결을 대신하므로 발행은 진행됩니다 |
| `publish_sla` | 긴급 | 05:20까지 브리핑 없음 | `ops/logs/digest.log` 확인. `claude -p "hi"`로 CLI 로그인 확인 후 `scripts/dev.sh digest` 수동 실행 |
| `publish_blocked` | 주의 | 게이트 차단, **Fail-safe**로 전일본 유지 | 알림의 실패 게이트를 콘솔 → 데일리 브리핑에서 확인. 번역 성공률이면 카드 적체(§3), 한국·공식 비중이면 소스 상태를 점검. 고친 뒤 `scripts/dev.sh digest`를 다시 돌리면 새 버전이 발행됩니다 |
| `strategy_failed` | 주의 | 페르소나·전략 Claude 호출 실패 | 같은 날 재실행. 계속 실패하면 Claude 사용량·로그인 확인 |
| `collection_stalled` | 긴급 | 1시간 동안 성공 수집 0 | worker·scheduler·redis 컨테이너와 인터넷 연결 확인 |
| `collection_degraded` | 주의 | 1시간 성공률 50% 미만 | 콘솔 → 수집 현황에서 오류 코드가 몰린 도메인 확인, 필요하면 소스 일시정지 |
| `dlq_backlog` | 주의 | 미해결 DLQ 50건 초과 | §4 |
| `queue_backlog` | 주의 | Celery 큐 500건 초과 | `docker compose logs worker`. 일시적이면 자연 해소, 계속되면 worker 재시작 |
| `redis_unreachable` | 긴급 | Redis 연결 실패 | `docker compose up -d redis` |
| `cards_stalled` | 주의 | 카드 생성 40분 이상 멈춤 | §3 |
| `cards_backlog` | 참고 | 카드 대기 5,000건 초과 | 05:00 후보는 카드가 있는 기사만 들어갑니다. 한도 상향 또는 Qwen 대기 |

알림은 검사가 다시 통과하면 자동으로 "해소"됩니다.

## 3. 카드 생성 장애 (Antigravity·LM Studio)

1. `tail -20 ops/logs/cards.log` — 마지막 실행의 엔진·한도(weekly·five_hour)를 봅니다.
2. agy 한도 소진(주간 ≤10%, 5시간 ≤2%)이면 자동으로 로컬 Qwen으로 넘어갑니다. Qwen도 실패하면 LM Studio가 떠 있는지(`curl -s localhost:1234/v1/models`)와 모델 로드를 확인합니다.
3. agy 로그인 만료: 터미널에서 `agy`를 한 번 실행해 로그인합니다.
4. launchd 상태: `launchctl print gui/$(id -u)/com.newsinsight.cards | grep -E "state|last exit"`. 재등록은 `scripts/install-card-schedule.sh`.
5. 잠금 파일이 남아 실행을 막으면(비정상 종료 후) 다음 실행이 잠금을 다시 잡습니다. 수동 실행: `scripts/dev.sh cards`.

## 4. DLQ 처리

콘솔 → DLQ에서 항목마다 **재시도** 또는 **종결**합니다.

- 같은 소스가 같은 오류로 **두 번째** DLQ에 가면 새 항목을 만들지 않고 기존 항목의 시도 수를 늘리며 소스를 일시정지합니다(사유 `repeated <코드>`). 차단하는 사이트를 주기마다 다시 두드리지 않기 위해서입니다. 재시도하려면 소스를 재개한 뒤 DLQ에서 재시도합니다.
- 콘텐츠 형식 오류(`blocked_mime`, 점검·동의 페이지가 잠깐 나오는 경우)도 두 번째에 정지합니다. 사설 주소 같은 다른 `blocked_*`는 첫 번째에 바로 정지합니다.
- 서버가 기다릴 시간을 알려 주면(429 `Retry-After`, Stack Exchange `throttle_violation`) 그만큼(최대 24시간) 뒤에 재시도하고 DLQ에 넣지 않습니다.
- 403 봇 차단(예: phonearena, euractiv, ericsson, huawei-central, pew)은 우회하지 않습니다. 정지된 채로 두거나 카탈로그에서 빼세요.

같은 소스가 반복되면:
- `config_error`(키·설정): `.env`의 `SOURCE_SECRET_*` 확인 후 `docker compose up -d` → 재시도
- `http_4xx`·`robots_disallowed`: 사이트 정책 변화. 소스를 일시정지하거나 카탈로그에서 빼고 `sources seed --prune`(cards-and-collection.md §12)
- `parse_error`: 사이트 구조 변경. 카탈로그 설정(선택자·피드 주소) 수정 후 시드

## 5. 소스 승격

V3(파서 통과) → 24시간 canary 수집 → V4 → 7일 카드 품질(DX 관련도 ≥ 35%, 번역 ≥ 95%) → V5 → 트랙 정원 안에서 V6(활성). 관련도 15% 미만은 자동 일시정지됩니다. 수동 판정: `news-insight sources canary`, `news-insight sources quality --apply`. 자세한 기준은 cards-and-collection.md §11.

## 6. 백업과 복구

- **백업**: `scripts/backup.sh` — `pg_dump`를 `age`로 암호화해 `~/NewsInsightBackups/`에 저장하고 14일 지난 파일을 지웁니다(`BACKUP_KEEP_DAYS`). 체크섬은 같은 폴더 `SHA256SUMS`.
- **키**: 첫 실행 때 `~/.config/news-insight/backup.age.key`가 만들어집니다. **이 키가 없으면 백업을 읽을 수 없습니다.** 비밀번호 관리자나 외장 매체에 사본을 두세요.
- **매일 자동 백업**: `scripts/install-backup-schedule.sh`(03:00, 로그 `ops/logs/backup.log`).
- **복구 리허설**: `scripts/restore-check.sh` — 최신 백업을 임시 DB(`news_insight_restore`)에 복원해 주요 테이블 행 수를 실제 DB와 비교하고 지웁니다. 실제 DB는 읽기만 합니다. 매주 한 번 권장.
- **실제 복구**: `scripts/restore.sh <파일>` — `RESTORE`를 입력해야 진행합니다. 앱 컨테이너를 멈추고 DB를 교체한 뒤 마이그레이션까지 돌려 다시 띄웁니다.

## 7. 릴리스와 롤백

- **릴리스**: main을 최신으로 맞추고(`git pull`) `scripts/release.sh`. 백업 → 커밋 해시로 이미지 빌드 → `.env`에 `IMAGE_TAG` 기록 → 마이그레이션 후 교체 → `ops/releases.log` 기록.
- **롤백**: `scripts/rollback.sh [tag]`. 인자가 없으면 직전 태그로 돌아갑니다. 마이그레이션 서비스는 건너뜁니다(구버전 코드는 새 스키마에서 동작하도록 마이그레이션을 추가형으로만 작성). 데이터 호환이 깨진 릴리스라면 릴리스 직전 백업으로 복구(§6)합니다.
- launchd 작업(카드·다이제스트)은 저장소 작업 트리에서 실행되므로 릴리스 뒤에는 작업 트리가 main인지 확인하세요.

## 8. 보안 점검 (2026-10-04)

| 항목 | 결과 |
|---|---|
| Python 런타임 의존성(`pip-audit`) | 알려진 취약점 0 |
| 웹 운영 의존성(`npm audit --omit=dev`) | 0. 개발 도구 `shadcn` CLI 경로(fast-glob → micromatch → braces)에만 경고 7건 — 운영 이미지에 포함되지 않음 |
| SSRF | 사설·루프백·링크로컬 주소 차단, 리다이렉트 매 홉 재검증, DNS 재바인딩 대비 피어 검증, 교차 호스트 리다이렉트에서 자격 증명 제거(테스트 19개) |
| XSS | 요약·제목은 React 텍스트로만 렌더링. `dangerouslySetInnerHTML`은 콘솔 차트의 고정 색상 CSS 한 곳뿐(사용자 데이터 없음) |
| 관리자 인증 | 매직링크(해시 저장, 15분 1회용, 14일 세션, 발급 한도, 스캐너 안전 확인 버튼), 콘솔 레이아웃·액션·내보내기에서 서버 검증 |
| 내부 API | `/api/admin`, `/api/public`은 Caddy에서 404. 각각 별도 키 |
| 응답 헤더 | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, COOP. HSTS는 실제 도메인(`PUBLIC_HOST`가 localhost가 아닐 때)에서만 |
| 컨테이너 | api·web 모두 비root 사용자로 실행 |
| 비밀 값 | `.env`는 커밋하지 않음. 푸시 전 토큰 패턴 검사 |

## 9. 7일 번인

P9 완료 기준은 7일 연속 05:00 발행 성공(또는 Fail-safe 정상 동작)입니다. 콘솔 → 운영 알림에서 `publish_sla`가 7일 동안 열리지 않았는지, 데일리 브리핑 이력에 날짜마다 발행본(또는 차단+전일본 유지)이 있는지 확인합니다.

## 10. 성능·관측성 기반 (2026-10-04, 점검표 단계 A)

- **인덱스** (마이그레이션 0016): `items.first_seen_at`, `(source_id, first_seen_at)`, 본문 만료 부분 인덱스, `item_cards.themes` GIN, 지표 스냅샷 `captured_at`. 시간 창 조회 1,018ms → 31ms, 테마 필터 379ms → 2ms.
- **속도 제한**: Caddy를 `ops/caddy/Dockerfile`로 빌드합니다(`caddy-ratelimit` 포함). IP당 분당 120회, `/radar*`는 20회이고 초과하면 429와 `Retry-After`를 돌려줍니다. 정적 파일은 제외입니다. 값은 `.env`의 `RATE_LIMIT_PAGES`·`RATE_LIMIT_RADAR`로 바꿉니다. Docker Desktop(Mac)에서는 모든 접속이 같은 게이트웨이 IP로 보이므로 한도가 공유됩니다. 리눅스 서버나 도메인 배포에서는 실제 IP 기준입니다.
- **구조화 로그**: API·Celery·CLI가 모두 JSON 한 줄로 stderr에 남깁니다(`service`, `request_id`, `source_id` 등). 찾을 때는 `docker compose logs api | grep '"level": "warning"'`. API 응답에는 `X-Request-ID`가 붙습니다.
- **새 알림**:
  - `api_slow`: 최근 1시간에 5초 넘게 걸린 API 응답이 5건 이상
  - `cards_failing`: 마지막 카드 실행의 실패율이 30% 이상
- **배포 직후 캐시**:
  - 웹은 공개 API의 스키마 해시(`/api/public/version`, 30초 캐시)를 모든 캐시 키에 넣습니다. 응답 모양이 바뀌면 옛 JSON을 쓰지 않습니다.
  - `scripts/release.sh`는 배포 뒤 웹의 `/internal/revalidate`(콘솔 키 필요, Caddy가 외부에는 404)를 호출해 독자 캐시를 비웁니다.
- **E2E 브라우저**: 기본은 시스템 Chrome입니다. 컨테이너처럼 Chrome이 없는 곳에서는 `E2E_BROWSER_CHANNEL= npx playwright install chromium && E2E_BROWSER_CHANNEL= scripts/dev.sh web-e2e`로 돌립니다.

## 11. 운영 트리와 개발 트리 분리 (2026-10-04)

- 운영은 `/Users/ggoma/WorkSpace/NEWS_INSIGHT-live`에서 합니다. 이 트리는 `origin/main`에 고정된 git worktree이고 `.env`는 개발 트리의 파일을 가리키는 심볼릭 링크입니다.
  - launchd 카드(10분)·다이제스트(05:00) 작업은 이 트리에서 돌고, 로그는 `NEWS_INSIGHT-live/ops/logs/`에 남습니다.
  - 배포는 이 트리에서 `scripts/deploy.sh`로 합니다. `docker compose up -d --build`는 2026-10-05 네 번 멈췄습니다(Docker Desktop 24 / Compose 2.18: 새 컨테이너를 만들고 시작하지 않음). 스크립트는 이미지를 먼저 빌드하고, 앱 컨테이너(migrate·api·worker·scheduler·web)만 지운 뒤 `--no-build`로 띄우고, 상태·스모크 검사를 합니다. 마이그레이션이 바뀌면 먼저 백업합니다. postgres·redis는 건드리지 않습니다. 정지 시간은 약 1분입니다.
- 새 main을 반영하는 순서:
  ```bash
  cd /Users/ggoma/WorkSpace/NEWS_INSIGHT-live && scripts/deploy.sh
  ```
  마이그레이션은 compose의 migrate 서비스가 실행합니다.
- 개발 트리(`NEWS_INSIGHT`)에서는 어떤 브랜치를 체크아웃해도 운영 작업에 영향이 없습니다.
- `scripts/dev.sh verify`는 더 이상 운영 DB를 마이그레이션하지 않습니다. 마이그레이션 검사는 임시 DB(`news_insight_check`)에서 합니다.

- **개발 트리에서 compose를 띄우지 않습니다.** 두 트리가 같은 compose 프로젝트(`news-insight`)를 쓰지만 바인드 마운트 경로가 트리마다 달라, 다른 트리에서 `compose up`을 하면 실행 중인 컨테이너가 새로 만들어집니다. 2026-10-05 개발 트리의 `verify`(db 단계)가 운영 postgres를 다시 만들려다 Docker가 멈추지 못해 DB가 약 10분, 그 전 배포에서 약 20분 내려갔습니다. 이제 `scripts/dev.sh`의 `db`는 postgres·redis가 건강하면 건드리지 않고, `up`·`down`·`db`는 다른 트리가 띄운 스택이면 거부합니다(`FORCE=1`로만 넘김).
- 앱 컨테이너(migrate·api·worker·scheduler·web)는 `init: true`(tini)로 돕니다. 이전에는 PID 1(uvicorn·celery)이 헬스체크 프로세스를 거두지 못해 좀비가 쌓였고, Docker가 컨테이너를 멈추거나 바꾸지 못해 배포가 세 번 멈췄습니다(2026-10-05).
- 그래도 멈추면: `docker ps -a | grep news-insight`로 이름 앞에 해시가 붙은 반쯤 만든 컨테이너를 `docker rm`, 좀비가 된 컨테이너는 `docker rm -f` 뒤 운영 트리에서 `docker compose up -d --no-deps <서비스>`. 데이터는 볼륨에 있어 안전합니다.
