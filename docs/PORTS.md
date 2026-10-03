# 포트 배정표

개발 서버에서 호스트로 공개하는 포트는 **8700~8799 대역**만 사용합니다. (2026-10-03 기준, 이 대역은 비어 있음)

| 호스트 포트 | 용도 | 바인딩 | 설정 위치 | 단계 |
|---:|---|---|---|---|
| 8700 | Caddy HTTPS — 전체 스택 진입점 (`https://localhost:8700`) | 0.0.0.0 | `CADDY_HTTPS_PORT` | P1 |
| 8701 | Caddy HTTP — HTTPS(8700)로 리다이렉트 | 0.0.0.0 | `CADDY_HTTP_PORT` | P1 |
| 8710 | Next.js 개발 서버 (`npm run dev`, Docker 없이 실행할 때) | localhost | `apps/web/package.json` | P1 |
| 8711 | FastAPI 개발 서버 (`scripts/dev.sh api-dev`, Docker 없이 실행할 때) | 127.0.0.1 | `scripts/dev.sh` | P1 |
| 8720 | PostgreSQL 16 (개발 override 전용) | 127.0.0.1 | `compose.override.yaml` | P1 |
| 8721 | Redis 7 (개발 override 전용) | 127.0.0.1 | `compose.override.yaml` | P1 |
| 8740 | 운영 모니터링 대시보드 (예약) | 127.0.0.1 | P9에서 확정 | P9 |

## 규칙

- **8770은 사용 금지:** 다른 프로젝트(`WorkSpace/부동산 분석`)의 개발 서버가 예약해 둔 포트입니다.
- 컨테이너 내부 포트(api `8000`, web `3000`, postgres `5432`, redis `6379`)는 Docker 내부망에서만 쓰이므로 바꾸지 않습니다.
- DB와 Redis는 개발용 `compose.override.yaml`에서만 `127.0.0.1`로 공개합니다. 운영 배포(`docker compose -f compose.yaml`)에서 호스트에 공개하는 서비스는 Caddy 하나뿐입니다.
- 공개 도메인으로 운영할 때(P9)는 `.env`에서 `CADDY_HTTPS_PORT=443`, `CADDY_HTTP_PORT=80`으로 바꿉니다. Let's Encrypt 인증서를 자동 발급받으려면 표준 포트가 필요합니다.
- 호스트 쪽 외부 서비스는 이 표의 관리 대상이 아닙니다: LM Studio `1234`. 이 프로젝트가 소유하지 않는 포트입니다.
- 새 포트가 필요하면 이 표에 먼저 추가한 다음 사용합니다. 추가 전에는 `lsof -nP -iTCP -sTCP:LISTEN | grep ':87'`로 비어 있는지 확인합니다.
