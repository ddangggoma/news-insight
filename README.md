# Daily IT Intelligence Platform

전 세계 기술 뉴스, 커뮤니티, 논문·특허, GitHub 트렌드를 4개 트랙으로 수집하고 매일 07:00 KST에 근거 기반 한국어 Daily 브리핑과 DX 전략 보고서를 발행하는 단일 서버 플랫폼입니다.

- 요구사항: `Chatgpt/daily-it-news/HIGH_LEVEL_REQUIREMENTS.md` v1.0
- 로드맵: `docs/superpowers/plans/2026-10-03-00-roadmap.md`
- 포트 배정: `docs/PORTS.md` (호스트 포트는 8700~8799만 사용)

## 개발 환경

`scripts/dev.sh`를 인자 없이 실행하면 전체 명령 목록이 나옵니다. (macOS 기본 `make`는 Xcode 라이선스 동의가 필요해서 셸 스크립트를 사용합니다.)

```bash
cp .env.example .env
scripts/dev.sh db        # PostgreSQL 16 → 127.0.0.1:8720, Redis 7 → 127.0.0.1:8721 (테스트 DB 생성)
scripts/dev.sh verify    # lint + type + test + alembic check + web build + compose config
scripts/dev.sh api-dev   # FastAPI → http://127.0.0.1:8711
scripts/dev.sh web-dev   # Next.js → http://localhost:8710
```

## 전체 스택

```bash
scripts/dev.sh up
curl -sk https://localhost:8700/api/health
```

LM Studio는 호스트에서 `qwen/qwen3.8-27b`를 포트 1234로 서빙하고, 컨테이너는 `host.docker.internal:1234`로 접근합니다.

## 소스 거버넌스 (V0~V6)

```bash
cd apps/api
uv run news-insight sources seed                 # catalog/sources.yaml → registry (멱등)
uv run news-insight sources validate the-verge   # V0 정체성 → V1 정책 → V2 네트워크 → V3 파서
uv run news-insight sources report               # 트랙 목표·지역 용량·단계 분포
uv run news-insight sources promote <key>        # V5 통과 소스의 V6 쿼터 게이트
```

- V1은 이용약관 검토 결과(`terms_url`, `storage_right`)가 카탈로그에 기록되어야 통과합니다.
- V4(24시간 Canary)와 V5(7일 품질)는 Phase 2 수집 엔진의 측정값으로 자동 판정합니다.
- 카탈로그에서 `endpoint_url`, `official_domain`, `access_method`가 바뀌면 검증이 `unverified`로 초기화됩니다.

## 수집 운영 (Phase 2)

V3를 통과한 후보 소스는 Canary 모드로, V6 활성 소스는 정식으로 수집됩니다. Celery Beat가 1분마다 기한이 된 소스를 배정하고, 1시간마다 V4 Canary를 판정하며, 매일 03:15 KST에 보존 기한이 지난 전문을 삭제합니다.

```bash
cd apps/api
uv run news-insight collect run the-verge        # 즉시 1회 수집 (도메인 예산은 지킴)
uv run news-insight collect status               # 다음 수집 시각·주기·연속 실패
uv run news-insight sources canary               # 24시간 관찰이 끝난 V3 소스의 V4 판정
uv run news-insight dlq list                     # 미해결 Dead Letter
uv run news-insight dlq retry <id>               # 소스를 즉시 재수집 대상으로
uv run news-insight sources resume <key>         # selector drift 등으로 멈춘 소스 재개
```

## 트랙 어댑터와 카탈로그 (Phase 3)

JSON API 소스는 `config.preset`으로 매핑을 고릅니다 (`github_search`, `bluesky_author_feed`, `mastodon_timeline`, `stackexchange_questions`, `hn_algolia`, `devto_articles`, `openalex_works`, `crossref_works`, `europepmc_search` 등).

```bash
cd apps/api
uv run --env-file ../../.env news-insight sources probe-catalog --track community   # 등록 전 V0·V2·V3 사전 점검
uv run news-insight sources probe <key>                                              # 등록된 소스 사전 점검
uv run news-insight trends movers --metric stars --days 1 --track oss                # 지표 상승 상위 항목
```

API 키는 카탈로그에 이름만 적고(`config.auth.secret: GITHUB_TOKEN`) 값은 `.env`의 `SOURCE_SECRET_GITHUB_TOKEN`에 둡니다.

## 운영 콘솔과 데일리 다이제스트 (Phase 3.5)

- 콘솔: `https://localhost:8700/console` (Basic Auth). 좌측 메뉴에서 대시보드, 다이제스트, 소스, 수집 현황, DLQ, 수집 항목, 지표 상승 화면을 엽니다.
- 다이제스트: 매일 05:00 KST에 호스트의 Claude CLI(Opus)가 전일 수집 항목을 트랙 → 하위 범주 → 종합 인사이트로 요약합니다. 모든 문장에 근거 기사 링크가 붙습니다.

```bash
scripts/dev.sh console-password        # 콘솔 비밀번호 설정 (bcrypt 해시만 .env에 저장)
scripts/install-digest-schedule.sh     # launchd에 05:00 다이제스트 등록
scripts/dev.sh digest                  # 지금 바로 다이제스트 생성
scripts/demo-db.sh                     # 화면 점검용 데모 DB(news_insight_demo) 생성
```

자세한 절차는 [운영 콘솔 런북](docs/runbooks/ops-console.md)을 보세요.

## 수집 자동화와 한국어 카드 뉴스 (Phase 3.6)

- **자동 수집:** 공개 RSS·API 소스는 robots.txt와 자격 증명만 확인되면 V1을 자동 통과합니다(D17). 10분마다 후보 100개가 V3까지 검증되고, 통과하면 바로 수집을 시작합니다.
- **카드 뉴스:** 모든 수집 항목을 한국어 카드(제목·요약·키워드·출처)로 만듭니다(D18). Antigravity CLI(Gemini Flash)를 주간 한도의 90%까지 쓰고, 한도가 바닥나면 로컬 Qwen으로 넘어갑니다. 콘솔 → 카드 뉴스에서 봅니다.

```bash
scripts/dev.sh sources-seed            # 카탈로그(1,000+)를 운영 DB에 등록
scripts/install-card-schedule.sh       # launchd에 10분 주기 카드 생성 등록
scripts/dev.sh cards                   # 지금 바로 카드 생성
```

자세한 절차는 [수집 자동화·카드 런북](docs/runbooks/cards-and-collection.md)을 보세요.

## 중복 묶음·교차 신호·분류 (Phase 4)

- 카드 생성 때 분야 15·테마 75·DX 사업부 6·영향·범위·관련도를 함께 분류합니다.
- 5분마다 같은 기사·유사 보도·같은 사건을 이슈로 묶고, arXiv·DOI·GitHub 식별자로 논문 → 오픈소스 → 커뮤니티 → 미디어를 잇습니다.
- 콘솔: 카드 뉴스(분류 필터, 이슈별 1건 보기) · 이슈 묶음 · 교차 신호 · 관련성 검토(AI 분류 일치율)

자세한 내용은 [중복 묶음·분류 런북](docs/runbooks/stories-classification.md)을 보세요.
