# Daily IT Intelligence Platform

전 세계 기술 뉴스, 커뮤니티, 논문·특허, GitHub 트렌드를 4개 트랙으로 수집하고 매일 07:00 KST에 근거 기반 한국어 Daily 브리핑과 DX 전략 보고서를 발행하는 단일 서버 플랫폼입니다.

- 요구사항: `Chatgpt/daily-it-news/HIGH_LEVEL_REQUIREMENTS.md` v1.0
- 로드맵: `docs/superpowers/plans/2026-10-03-00-roadmap.md`
- 포트 배정: `docs/PORTS.md` (호스트 포트는 8700~8799만 사용)

## 개발 환경

```bash
cp .env.example .env
make db        # PostgreSQL 16 → 127.0.0.1:8720, Redis 7 → 127.0.0.1:8721 (테스트 DB 생성)
make verify    # lint + type + test + alembic check + web build + compose config
make api-dev   # FastAPI → http://127.0.0.1:8711
make web-dev   # Next.js → http://localhost:8710
```

## 전체 스택

```bash
make up
curl -sk https://localhost:8700/api/health
```

LM Studio는 호스트에서 `qwen/qwen3.8-27b`를 포트 1234로 서빙하고, 컨테이너는 `host.docker.internal:1234`로 접근합니다.
