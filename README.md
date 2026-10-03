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
