# Phase 1 — Platform Foundation & Source Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use dev_sp_subagent-driven-development (recommended) or dev_sp_executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `NEWS_INSIGHT` 저장소에 단일 서버 Docker Compose 스택을 세우고, 4개 수집 트랙의 소스를 등록한 뒤 V0~V3 검증과 V6 포트폴리오 쿼터 게이트를 통과시키는 소스 레지스트리를 완성합니다.

**Architecture:** `apps/api`는 FastAPI, Celery, SQLAlchemy 2, Alembic으로 구성한 Python 3.12 패키지 `news_insight`(uv로 관리)입니다. 소스 거버넌스는 순수 함수 검사기(V0/V1/V3/V6)와 SSRF 안전 Fetcher(V2)가 `CheckResult`를 만들고, 승격 사다리 상태 머신(`ladder.py`)이 이 결과를 단계 순서대로만 기록하는 구조입니다. `apps/web`은 Phase 8에서 본격 구현할 Next.js 셸이며, Caddy가 `/api/*`를 api로, 나머지를 web으로 프록시합니다.

**Tech Stack:** Python 3.12 · uv · FastAPI · SQLAlchemy 2.0 · Alembic · psycopg 3 · Celery 5 (Redis) · httpx · feedparser · pydantic v2 · Typer · pytest · ruff · mypy(strict) · Next.js 16.3.8 · React 19 · Tailwind 4 · Vitest · PostgreSQL 16 · Redis 7 · Caddy 2

## Global Constraints

- 수집 트랙 4개와 목표 활성 수: `news` 100, `community` 100, `research_ip` 35, `oss` 25 (합계 260)
- 지역 비율: 한국 25%, 글로벌 영어 45%, 일본 10%, 중화권 8%, 유럽·기타 12%. 소스 수 기준 용량 260 × 비율 = 65/117/26/21/31로 해석 (로드맵 D2)
- 원문 저장 등급 4종: `metadata_only`, `excerpt_allowed`, `fulltext_ttl`, `fulltext_permitted`
- 검증 단계 순서: `unverified → V0 → V1 → V2 → V3 → V4 → V5 → V6`, 단계 건너뛰기 금지. `V6` + `active` 상태인 소스만 스케줄 대상
- HTTP 수집 제한: 타임아웃 15초, 리다이렉트 최대 3회, 응답 최대 5MB (5 × 1024 × 1024 bytes), HTTPS(443) 전용, 사설·루프백·링크로컬·멀티캐스트 주소 차단
- V3: 식별자·URL·제목·발행일을 모두 갖춘 최신 항목 3건 이상
- 연구·특허 트랙: 페이월 우회 금지. 전문 저장 등급은 `config.open_access: true`일 때만 허용
- 시간대 `Asia/Seoul`, LM Studio 모델 `qwen/qwen3.8-27b`, 관리자 이메일 `ddangggoma@gmail.com`
- 컨테이너 런타임: PostgreSQL 16, Redis 7, Caddy 2. 호스트로 포트를 공개하는 서비스는 Caddy 하나뿐 (개발용 override 제외)
- Python 코드는 `ruff check`, `ruff format --check`, `mypy --strict`를 통과해야 함
- 모든 Python 명령은 `apps/api`에서 `uv run ...`으로 실행하고, 웹 명령은 `apps/web`에서 `npm ...`으로 실행

---

## File Structure

```
NEWS_INSIGHT/
├── .gitignore
├── .env.example                      # Compose 변수 (개발 기본값)
├── compose.yaml                      # 운영 스택 (Caddy만 포트 공개)
├── compose.override.yaml             # 개발 전용: DB/Redis 로컬 포트, 테스트 DB 생성
├── Makefile                          # verify / test / lint 진입점
├── README.md
├── ops/
│   ├── Caddyfile
│   └── postgres/init/01-test-database.sql
├── apps/api/
│   ├── pyproject.toml · uv.lock · .python-version · Dockerfile · .dockerignore
│   ├── alembic.ini
│   ├── migrations/{env.py, script.py.mako, versions/0001_baseline.py, versions/0002_source_registry.py}
│   ├── catalog/sources.yaml          # 소스 카탈로그 초안 (P3에서 260개로 확장)
│   ├── src/news_insight/
│   │   ├── __init__.py               # __version__
│   │   ├── config.py                 # Settings (요구사항 상수의 기본값)
│   │   ├── main.py                   # FastAPI app, /api/health
│   │   ├── db.py                     # Base, engine, session_scope
│   │   ├── model_registry.py         # Alembic이 import하는 모델 목록
│   │   ├── cli.py                    # news-insight CLI (Typer)
│   │   ├── jobs/celery_app.py        # Celery app (Asia/Seoul)
│   │   ├── net/safe_fetch.py         # V2: SSRF 안전 HTTP Fetcher
│   │   ├── parsers/feed_probe.py     # V3: RSS/Atom 파서 신뢰성 검사
│   │   └── sources/
│   │       ├── enums.py              # Track, Region, StorageRight, ValidationStage …
│   │       ├── models.py             # Source, SourceValidationEvent
│   │       ├── ladder.py             # CheckResult, 승격 상태 머신, pause/reset
│   │       ├── catalog.py            # YAML 카탈로그 스키마·로더·시드
│   │       ├── checks.py             # V0 identity, V1 policy, V2 network, V3 parser
│   │       ├── portfolio.py          # 트랙/지역 쿼터, 리포트, V6 쿼터 검사
│   │       └── service.py            # run_check / climb / get_source / stage_counts
│   └── tests/ (conftest.py, factories.py, test_*.py, sources/, net/, parsers/, jobs/)
└── apps/web/
    ├── package.json · package-lock.json · tsconfig.json · next.config.ts · postcss.config.mjs
    ├── vitest.config.ts · Dockerfile · .dockerignore
    ├── app/{layout.tsx, page.tsx, globals.css}
    └── tests/{setup.ts, home.test.tsx}
```

**책임 경계:** `checks.py`, `portfolio.py`, `feed_probe.py`, `safe_fetch.py`는 DB를 모르는 순수 로직입니다. DB 상태를 바꾸는 코드는 `ladder.py`(검증 상태)와 `catalog.py`(시드)뿐이며, `service.py`는 둘을 조합만 합니다.

---

### Task 1: API 패키지 골격 (설정 + 헬스체크)

**Files:**
- Create: `.gitignore`, `apps/api/.python-version`, `apps/api/pyproject.toml`
- Create: `apps/api/src/news_insight/__init__.py`, `apps/api/src/news_insight/config.py`, `apps/api/src/news_insight/main.py`
- Test: `apps/api/tests/__init__.py`, `apps/api/tests/test_config.py`, `apps/api/tests/test_health.py`

**Interfaces:**
- Consumes: 없음
- Produces: `news_insight.__version__: str = "0.1.0"`, `news_insight.config.Settings` (필드: `app_env`, `database_url`, `redis_url`, `timezone`, `lm_studio_url`, `lm_studio_model`, `admin_email`, `fetch_timeout_seconds: float`, `fetch_max_redirects: int`, `fetch_max_bytes: int`), `news_insight.config.get_settings() -> Settings`, `news_insight.main.create_app() -> FastAPI`, `news_insight.main.app`

- [ ] **Step 1: 저장소 초기화와 공통 파일 작성**

```bash
cd /Users/ggoma/WorkSpace/NEWS_INSIGHT && git init -b main
```

`.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
.next/
next-env.d.ts
*.tsbuildinfo
.DS_Store
```

`apps/api/.python-version`:

```
3.12
```

`apps/api/pyproject.toml`:

```toml
[project]
name = "news-insight-api"
version = "0.1.0"
description = "Daily IT Intelligence Platform API and workers"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic>=1.16,<2",
  "celery[redis]>=5.5,<5.7",
  "fastapi>=0.116,<1",
  "feedparser>=6.0,<7",
  "httpx>=0.28,<1",
  "psycopg[binary]>=3.2,<4",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.10,<3",
  "pyyaml>=6.0,<7",
  "sqlalchemy>=2.0.40,<2.1",
  "typer>=0.16,<1",
  "uvicorn[standard]>=0.35,<1",
]

[project.scripts]
news-insight = "news_insight.cli:app"

[dependency-groups]
dev = [
  "mypy>=1.17,<2",
  "pytest>=8.4,<9",
  "ruff>=0.12,<1",
  "types-pyyaml>=6.0,<7",
]

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_insight"]

[tool.pytest.ini_options]
addopts = "--strict-markers -q"
testpaths = ["tests"]
markers = ["db: requires the PostgreSQL test database"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
packages = ["news_insight"]

[[tool.mypy.overrides]]
module = ["celery", "celery.*", "feedparser"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["news_insight.jobs.*"]
disallow_untyped_decorators = false
```

`apps/api/src/news_insight/__init__.py`:

```python
"""Daily IT Intelligence Platform."""

__version__ = "0.1.0"
```

`apps/api/tests/__init__.py`: 빈 파일

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/api/tests/test_config.py`:

```python
import pytest

from news_insight.config import Settings


def test_defaults_follow_requirements() -> None:
    settings = Settings(_env_file=None)

    assert settings.timezone == "Asia/Seoul"
    assert settings.lm_studio_model == "qwen/qwen3.8-27b"
    assert settings.admin_email == "ddangggoma@gmail.com"
    assert settings.fetch_timeout_seconds == 15.0
    assert settings.fetch_max_redirects == 3
    assert settings.fetch_max_bytes == 5 * 1024 * 1024


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@db:5432/x"
```

`apps/api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from news_insight.main import create_app


def test_health_reports_ok_and_version() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd apps/api && uv sync && uv run pytest tests/test_config.py tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.config'` (uv가 Python 3.12를 자동으로 내려받고 `uv.lock`을 생성함)

- [ ] **Step 4: 최소 구현**

`apps/api/src/news_insight/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults encode the v1.0 requirement constants."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://news:news-dev-password@localhost:5432/news_insight"
    redis_url: str = "redis://localhost:6379/0"
    timezone: str = "Asia/Seoul"
    lm_studio_url: str = "http://host.docker.internal:1234"
    lm_studio_model: str = "qwen/qwen3.8-27b"
    admin_email: str = "ddangggoma@gmail.com"
    fetch_timeout_seconds: float = 15.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`apps/api/src/news_insight/main.py`:

```python
from fastapi import FastAPI

from news_insight import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="Daily IT Intelligence API", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
```

- [ ] **Step 5: 테스트 통과와 정적 검사 확인**

Run: `cd apps/api && uv run pytest -v && uv run ruff format . && uv run ruff check . && uv run mypy`
Expected: `3 passed`, ruff `All checks passed!`, mypy `Success: no issues found`

- [ ] **Step 6: Commit**

```bash
git add .gitignore apps/api
git commit -m "feat(api): scaffold FastAPI package with settings and health check"
```

---

### Task 2: 웹 셸 (Next.js)

**Files:**
- Create: `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/next.config.ts`, `apps/web/postcss.config.mjs`, `apps/web/vitest.config.ts`, `apps/web/.dockerignore`, `apps/web/Dockerfile`
- Create: `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`, `apps/web/app/globals.css`
- Test: `apps/web/tests/setup.ts`, `apps/web/tests/home.test.tsx`

**Interfaces:**
- Consumes: 없음
- Produces: 포트 3000에서 동작하는 Next.js standalone 서버 (`node server.js`), `/` 페이지. Phase 8에서 이 셸을 확장함

- [ ] **Step 1: 프로젝트 설정 파일 작성**

`apps/web/package.json`:

```json
{
  "name": "news-insight-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "test": "vitest"
  },
  "dependencies": {
    "@tailwindcss/postcss": "4.3.3",
    "next": "16.3.8",
    "react": "19.2.8",
    "react-dom": "19.2.8",
    "tailwindcss": "4.3.3"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "6.9.1",
    "@testing-library/react": "16.3.2",
    "@types/node": "22.19.15",
    "@types/react": "19.2.14",
    "@types/react-dom": "19.2.3",
    "jsdom": "29.1.1",
    "typescript": "5.9.3",
    "vitest": "4.1.11"
  }
}
```

`apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts", ".next/dev/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`apps/web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
```

`apps/web/postcss.config.mjs`:

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

`apps/web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": import.meta.dirname } },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
  },
});
```

`apps/web/tests/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());
```

Run: `cd apps/web && npm install`
Expected: `package-lock.json` 생성, 의존성 오류 없음

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/web/tests/home.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("states the daily publication schedule", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Daily IT Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/07:00 KST 정시 발행/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd apps/web && npm test -- --run`
Expected: FAIL — `Failed to resolve import "@/app/page"`

- [ ] **Step 4: 최소 구현**

`apps/web/app/globals.css`:

```css
@import "tailwindcss";
```

`apps/web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Daily IT Intelligence",
  description: "매일 07:00 KST 발행되는 근거 기반 DX 기술 인텔리전스 브리핑",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-white text-slate-900 antialiased">{children}</body>
    </html>
  );
}
```

`apps/web/app/page.tsx`:

```tsx
export default function HomePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-2xl font-semibold">Daily IT Intelligence</h1>
      <p className="mt-4 text-slate-600">
        매일 06:40 KST 후보 동결, 07:00 KST 정시 발행. 첫 브리핑을 준비하고 있습니다.
      </p>
    </main>
  );
}
```

`apps/web/.dockerignore`:

```
node_modules
.next
tests
*.tsbuildinfo
```

`apps/web/Dockerfile`:

```dockerfile
FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 5: 테스트·타입·빌드 확인**

Run: `cd apps/web && npm test -- --run && npm run typecheck && npm run build`
Expected: `1 passed`, tsc 출력 없음, `next build` 성공 (`.next/standalone` 생성)

- [ ] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat(web): add Next.js shell with publication schedule landing page"
```

---

### Task 3: 데이터 저장소와 마이그레이션 기반

**Files:**
- Create: `compose.yaml` (postgres, redis만), `compose.override.yaml`, `.env.example`, `ops/postgres/init/01-test-database.sql`
- Create: `apps/api/src/news_insight/db.py`, `apps/api/src/news_insight/model_registry.py`
- Create: `apps/api/alembic.ini`, `apps/api/migrations/env.py`, `apps/api/migrations/script.py.mako`, `apps/api/migrations/versions/0001_baseline.py`
- Test: `apps/api/tests/conftest.py`, `apps/api/tests/test_db_baseline.py`

**Interfaces:**
- Consumes: `news_insight.config.get_settings()`
- Produces: `news_insight.db.Base` (네이밍 규칙이 적용된 DeclarativeBase), `get_engine() -> Engine`, `get_session_factory() -> sessionmaker[Session]`, `session_scope() -> ContextManager[Session]` (정상 종료 시 commit, 예외 시 rollback). pytest fixture `db_engine` (session 범위, 테스트 DB에 Alembic head 적용), `db_session` (테스트마다 트랜잭션을 rollback하는 `Session`, 내부 `commit()`은 savepoint로 처리)

- [ ] **Step 1: 데이터 저장소 Compose 작성 및 기동**

`compose.yaml`:

```yaml
name: news-insight

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-news_insight}
      POSTGRES_USER: ${POSTGRES_USER:-news}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-news} -d ${POSTGRES_DB:-news_insight}"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

`compose.override.yaml` (개발 전용, `docker compose`가 자동으로 병합함. 운영 배포에서는 `-f compose.yaml`만 사용):

```yaml
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - ./ops/postgres/init:/docker-entrypoint-initdb.d:ro
  redis:
    ports:
      - "127.0.0.1:6379:6379"
```

`ops/postgres/init/01-test-database.sql`:

```sql
CREATE DATABASE news_insight_test;
```

`.env.example`:

```dotenv
# Development defaults. Copy to .env and replace secrets before any shared deployment.
# POSTGRES_PASSWORD is embedded in DATABASE_URL: use URL-safe characters only.
APP_ENV=development
POSTGRES_DB=news_insight
POSTGRES_USER=news
POSTGRES_PASSWORD=news-dev-password
PUBLIC_HOST=localhost
ADMIN_EMAIL=ddangggoma@gmail.com
LM_STUDIO_URL=http://host.docker.internal:1234
LM_STUDIO_MODEL=qwen/qwen3.8-27b
```

Run: `cp .env.example .env && docker compose up -d postgres redis && docker compose ps`
Expected: `postgres`, `redis` 모두 `(healthy)`. (5432나 6379 포트를 이미 다른 프로세스가 쓰고 있으면 그 프로세스를 먼저 종료)

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/api/tests/conftest.py`:

```python
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://news:news-dev-password@localhost:5432/news_insight_test",
)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    database = make_url(TEST_DATABASE_URL).database or ""
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to reset non-test database '{database}'")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
```

`apps/api/tests/test_db_baseline.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


def test_pg_trgm_extension_is_installed(db_session: Session) -> None:
    installed = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar_one_or_none()

    assert installed == "pg_trgm"


def test_server_is_postgres_16(db_session: Session) -> None:
    version_num = db_session.execute(text("SHOW server_version_num")).scalar_one()

    assert int(version_num) // 10000 == 16
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_db_baseline.py -v`
Expected: FAIL (ERROR at setup) — `alembic.ini` 경로를 찾지 못하는 오류 (`No 'script_location' key found` 또는 `FileNotFoundError`)

- [ ] **Step 4: DB 계층과 Alembic 구현**

`apps/api/src/news_insight/db.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from news_insight.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

`apps/api/src/news_insight/model_registry.py`:

```python
"""Import every ORM module here so Alembic sees the complete metadata."""
```

`apps/api/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/migrations
file_template = %%(rev)s_%%(slug)s
prepend_sys_path = src

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`apps/api/migrations/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import news_insight.model_registry  # noqa: F401
from news_insight.config import get_settings
from news_insight.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    override = config.attributes.get("database_url")
    return str(override) if override else get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`apps/api/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`apps/api/migrations/versions/0001_baseline.py`:

```python
"""Baseline: database extensions.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
```

- [ ] **Step 5: 테스트 통과와 마이그레이션 일치 확인**

Run: `cd apps/api && uv run pytest -v && uv run alembic upgrade head && uv run alembic check`
Expected: `5 passed`, `alembic check`에서 `No new upgrade operations detected.`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add compose.yaml compose.override.yaml .env.example ops apps/api
git commit -m "feat(api): add PostgreSQL/Redis stores and Alembic baseline with pg_trgm"
```

---

### Task 4: 전체 런타임 스택 (api · worker · scheduler · web · caddy)

**Files:**
- Modify: `compose.yaml` (아래 전체 내용으로 교체)
- Create: `apps/api/Dockerfile`, `apps/api/.dockerignore`, `apps/api/src/news_insight/jobs/__init__.py`, `apps/api/src/news_insight/jobs/celery_app.py`
- Create: `ops/Caddyfile`, `Makefile`, `README.md`
- Test: `apps/api/tests/test_compose.py`, `apps/api/tests/jobs/__init__.py`, `apps/api/tests/jobs/test_celery_app.py`

**Interfaces:**
- Consumes: `news_insight.config.get_settings()`, `news_insight.main:app`, 웹 셸 (Task 2), Alembic (Task 3)
- Produces: `news_insight.jobs.celery_app.celery_app: Celery` (timezone `Asia/Seoul`, Redis broker), 태스크 `system.ping -> "pong"`. Phase 2부터 이 app에 태스크와 Beat 스케줄을 등록함. `make verify` 진입점

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/test_compose.py`:

```python
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_services() -> dict[str, Any]:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services: dict[str, Any] = compose["services"]
    return services


def test_stack_defines_every_runtime_service() -> None:
    expected = {"migrate", "web", "api", "worker", "scheduler", "postgres", "redis", "caddy"}

    assert expected <= set(load_services())


def test_data_store_major_versions_are_pinned() -> None:
    services = load_services()

    assert services["postgres"]["image"].startswith("postgres:16")
    assert services["redis"]["image"].startswith("redis:7")


def test_only_caddy_publishes_host_ports() -> None:
    published = {name for name, service in load_services().items() if service.get("ports")}

    assert published == {"caddy"}


def test_worker_can_reach_host_lm_studio() -> None:
    worker = load_services()["worker"]

    assert "host.docker.internal:host-gateway" in worker["extra_hosts"]
    assert worker["environment"]["LM_STUDIO_MODEL"].endswith("qwen/qwen3.8-27b}")
```

`apps/api/tests/jobs/__init__.py`: 빈 파일

`apps/api/tests/jobs/test_celery_app.py`:

```python
from news_insight.jobs.celery_app import celery_app, ping


def test_celery_runs_on_seoul_time() -> None:
    assert celery_app.conf.timezone == "Asia/Seoul"


def test_ping_task_executes() -> None:
    assert ping.apply().get() == "pong"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_compose.py tests/jobs -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.jobs'`, `test_stack_defines_every_runtime_service`에서 누락된 서비스로 assertion 실패

- [ ] **Step 3: Celery app 구현**

`apps/api/src/news_insight/jobs/__init__.py`: 빈 파일

`apps/api/src/news_insight/jobs/celery_app.py`:

```python
from celery import Celery

from news_insight.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery("news_insight", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.update(
        timezone=settings.timezone,
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_default_queue="default",
    )
    return app


celery_app = create_celery()


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
```

- [ ] **Step 4: 컨테이너 이미지·Compose·Caddy 작성**

`apps/api/.dockerignore`:

```
.venv
**/__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
tests
```

`apps/api/Dockerfile`:

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

ENV PATH="/opt/venv/bin:$PATH"
RUN addgroup --system app && adduser --system --ingroup app app
USER app
EXPOSE 8000
CMD ["uvicorn", "news_insight.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`compose.yaml` (전체 교체):

```yaml
name: news-insight

x-python-env: &python-env
  APP_ENV: ${APP_ENV:-production}
  DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-news}:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/${POSTGRES_DB:-news_insight}
  REDIS_URL: redis://redis:6379/0
  TIMEZONE: Asia/Seoul
  LM_STUDIO_URL: ${LM_STUDIO_URL:-http://host.docker.internal:1234}
  LM_STUDIO_MODEL: ${LM_STUDIO_MODEL:-qwen/qwen3.8-27b}
  ADMIN_EMAIL: ${ADMIN_EMAIL:-ddangggoma@gmail.com}

x-python-image: &python-image
  image: news-insight-api:${IMAGE_TAG:-local}
  build:
    context: ./apps/api
  environment: *python-env
  extra_hosts:
    - "host.docker.internal:host-gateway"

x-python-runtime: &python-runtime
  <<: *python-image
  restart: unless-stopped
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
    migrate:
      condition: service_completed_successfully

services:
  migrate:
    <<: *python-image
    command: ["alembic", "upgrade", "head"]
    restart: "no"
    depends_on:
      postgres:
        condition: service_healthy

  api:
    <<: *python-runtime
    command: ["uvicorn", "news_insight.main:app", "--host", "0.0.0.0", "--port", "8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
      interval: 10s
      timeout: 5s
      retries: 10

  worker:
    <<: *python-runtime
    command: ["celery", "-A", "news_insight.jobs.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=4"]
    healthcheck:
      test: ["CMD-SHELL", "celery -A news_insight.jobs.celery_app:celery_app inspect ping --timeout 5"]
      interval: 30s
      timeout: 15s
      retries: 5

  scheduler:
    <<: *python-runtime
    command: ["celery", "-A", "news_insight.jobs.celery_app:celery_app", "beat", "--loglevel=INFO", "--schedule=/tmp/celerybeat-schedule"]

  web:
    image: news-insight-web:${IMAGE_TAG:-local}
    build:
      context: ./apps/web
    environment:
      API_INTERNAL_URL: http://api:8000
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 10
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-news_insight}
      POSTGRES_USER: ${POSTGRES_USER:-news}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-news} -d ${POSTGRES_DB:-news_insight}"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - redis_data:/data
    restart: unless-stopped

  caddy:
    image: caddy:2.10-alpine
    environment:
      PUBLIC_HOST: ${PUBLIC_HOST:-localhost}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./ops/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      api:
        condition: service_healthy
      web:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  caddy_data:
  caddy_config:
```

`ops/Caddyfile`:

```caddyfile
{$PUBLIC_HOST:localhost} {
	encode zstd gzip

	header {
		X-Content-Type-Options nosniff
		X-Frame-Options DENY
		Referrer-Policy strict-origin-when-cross-origin
		Permissions-Policy "camera=(), microphone=(), geolocation=()"
		-Server
	}

	handle /api/* {
		reverse_proxy api:8000
	}

	handle {
		reverse_proxy web:3000
	}
}
```

`Makefile` (레시피 들여쓰기는 반드시 탭):

```makefile
.PHONY: up down logs db migrate api-test api-lint web-test web-check compose-check alembic-check verify

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

db:
	docker compose up -d --wait postgres redis

migrate:
	cd apps/api && uv run alembic upgrade head

api-test:
	cd apps/api && uv run pytest

api-lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy

web-test:
	cd apps/web && npm test -- --run

web-check:
	cd apps/web && npm run typecheck && npm run build

compose-check:
	docker compose --env-file .env.example config --quiet

alembic-check:
	cd apps/api && uv run alembic check

verify: db migrate api-lint api-test alembic-check web-test web-check compose-check
```

`README.md`:

````markdown
# Daily IT Intelligence Platform

전 세계 기술 뉴스, 커뮤니티, 논문·특허, GitHub 트렌드를 4개 트랙으로 수집하고 매일 07:00 KST에 근거 기반 한국어 Daily 브리핑과 DX 전략 보고서를 발행하는 단일 서버 플랫폼입니다.

- 요구사항: `Chatgpt/daily-it-news/HIGH_LEVEL_REQUIREMENTS.md` v1.0
- 로드맵: `docs/superpowers/plans/2026-10-03-00-roadmap.md`

## 개발 환경

```bash
cp .env.example .env
make db        # PostgreSQL 16 / Redis 7 (개발 override: 127.0.0.1 포트 공개, 테스트 DB 생성)
make verify    # lint + type + test + alembic check + web build + compose config
```

## 전체 스택

```bash
make up
curl -sk https://localhost/api/health
```

LM Studio는 호스트에서 `qwen/qwen3.8-27b`를 포트 1234로 서빙하고, 컨테이너는 `host.docker.internal:1234`로 접근합니다.
````

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -v`
Expected: `11 passed`

- [ ] **Step 6: 스택 스모크 테스트**

Run: `make compose-check && docker compose up -d --build`

Run: `until curl -skf https://localhost/api/health; do sleep 3; done; echo; docker compose ps`
Expected: `{"status":"ok","version":"0.1.0"}` 출력. (Compose 2.18의 `--wait`는 종료되는 일회성 `migrate` 컨테이너를 오류로 볼 수 있어 대기 루프를 사용) `migrate`는 `exited (0)`, 나머지 서비스는 `running`이고 `healthy` (scheduler는 healthcheck가 없으므로 `running`). 80/443 포트 충돌이 나면 해당 프로세스를 먼저 종료

Run: `docker compose down`

- [ ] **Step 7: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add compose.yaml ops/Caddyfile Makefile README.md apps/api
git commit -m "feat: run full compose stack with Celery worker/beat, web and Caddy proxy"
```

---

### Task 5: 소스 레지스트리 스키마

**Files:**
- Create: `apps/api/src/news_insight/sources/__init__.py`, `apps/api/src/news_insight/sources/enums.py`, `apps/api/src/news_insight/sources/models.py`
- Modify: `apps/api/src/news_insight/model_registry.py`
- Create: `apps/api/migrations/versions/0002_source_registry.py`
- Test: `apps/api/tests/factories.py`, `apps/api/tests/sources/__init__.py`, `apps/api/tests/sources/test_source_models.py`

**Interfaces:**
- Consumes: `news_insight.db.Base`
- Produces:
  - `enums.py`: `Track` (`NEWS="news"`, `COMMUNITY="community"`, `RESEARCH_IP="research_ip"`, `OSS="oss"`), `Region` (`KR="kr"`, `GLOBAL_EN="global_en"`, `JP="jp"`, `GREATER_CHINA="greater_china"`, `EU_OTHER="eu_other"`), `AccessMethod` (`FEED`, `JSON_API`, `CRAWLER`, `GITHUB`, `ATPROTO`, `ACTIVITYPUB`, `RESEARCH_API`), `StorageRight` (4종), `PollClass` (`BREAKING`, `NEWS`, `COMMUNITY`, `RESEARCH`, `SLOW`), `ValidationStage` (`UNVERIFIED="unverified"`, `V0`~`V6`), `STAGE_ORDER: tuple[ValidationStage, ...]`, `SourceStatus` (`CANDIDATE`, `ACTIVE`, `PAUSED`, `RETIRED`), `ValidationOutcome` (`PASSED`, `FAILED`, `RESET`)
  - `models.py`: `Source` (컬럼: `id, key, name, track, category, access_method, endpoint_url, official_domain, operator, region, language, poll_class, dx_relevance, terms_url, storage_right, validation_stage, status, paused_reason, config, created_at, updated_at`, 관계 `validation_events`), `SourceValidationEvent` (`id, source_id, stage, outcome, reasons: list[str], metrics: dict[str, Any], created_at`, 관계 `source`)
  - `tests/factories.py`: `source_values(**overrides) -> dict[str, Any]`, `build_source(**overrides) -> Source` (stage `UNVERIFIED`와 status `CANDIDATE`를 명시적으로 설정)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/factories.py`:

```python
from typing import Any

from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationStage,
)
from news_insight.sources.models import Source


def source_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "key": "example-news",
        "name": "Example News",
        "track": Track.NEWS,
        "category": "independent_media",
        "access_method": AccessMethod.FEED,
        "endpoint_url": "https://www.example.com/feed.xml",
        "official_domain": "example.com",
        "operator": "Example Media Inc.",
        "region": Region.GLOBAL_EN,
        "language": "en",
        "poll_class": PollClass.NEWS,
        "dx_relevance": "모바일·가전·디스플레이 제품 동향을 다루는 테크 미디어",
        "terms_url": "https://www.example.com/terms",
        "storage_right": StorageRight.EXCERPT_ALLOWED,
        "config": {},
    }
    values.update(overrides)
    return values


def build_source(**overrides: Any) -> Source:
    values = {
        "validation_stage": ValidationStage.UNVERIFIED,
        "status": SourceStatus.CANDIDATE,
        **source_values(),
    }
    values.update(overrides)
    return Source(**values)
```

`apps/api/tests/sources/__init__.py`: 빈 파일

`apps/api/tests/sources/test_source_models.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent
from tests.factories import build_source, source_values

pytestmark = pytest.mark.db


def test_stage_order_is_unverified_then_v0_to_v6() -> None:
    assert [stage.value for stage in STAGE_ORDER] == [
        "unverified", "V0", "V1", "V2", "V3", "V4", "V5", "V6",
    ]


def test_new_source_defaults_to_unverified_candidate(db_session: Session) -> None:
    source = Source(**source_values())
    db_session.add(source)
    db_session.flush()
    db_session.refresh(source)

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.status is SourceStatus.CANDIDATE
    assert source.config == {}
    assert source.created_at is not None


def test_source_key_is_unique(db_session: Session) -> None:
    db_session.add(build_source(key="dup"))
    db_session.flush()
    db_session.add(build_source(key="dup"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_enums_are_stored_as_plain_values(db_session: Session) -> None:
    db_session.add(build_source(key="plain"))
    db_session.flush()

    row = db_session.execute(
        text("SELECT track, region, validation_stage FROM sources WHERE key = 'plain'")
    ).one()

    assert tuple(row) == ("news", "global_en", "unverified")


def test_validation_events_are_ordered_by_insertion(db_session: Session) -> None:
    source = build_source(key="ordered")
    db_session.add(source)
    db_session.flush()
    for stage in (ValidationStage.V0, ValidationStage.V1):
        db_session.add(
            SourceValidationEvent(
                source=source, stage=stage, outcome=ValidationOutcome.PASSED, reasons=[], metrics={}
            )
        )
    db_session.flush()
    db_session.expire(source)

    assert [event.stage for event in source.validation_events] == [
        ValidationStage.V0,
        ValidationStage.V1,
    ]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_source_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources'`

- [ ] **Step 3: Enum과 모델 구현**

`apps/api/src/news_insight/sources/__init__.py`: 빈 파일

`apps/api/src/news_insight/sources/enums.py`:

```python
from enum import StrEnum


class Track(StrEnum):
    NEWS = "news"  # IT 기술 뉴스 및 공식 소스
    COMMUNITY = "community"  # 커뮤니티 및 공개 SNS
    RESEARCH_IP = "research_ip"  # 논문·학회·표준·특허
    OSS = "oss"  # GitHub 오픈소스 트렌드


class Region(StrEnum):
    KR = "kr"
    GLOBAL_EN = "global_en"
    JP = "jp"
    GREATER_CHINA = "greater_china"
    EU_OTHER = "eu_other"


class AccessMethod(StrEnum):
    FEED = "feed"  # RSS / Atom
    JSON_API = "json_api"
    CRAWLER = "crawler"  # declarative, terms-reviewed crawler
    GITHUB = "github"
    ATPROTO = "atproto"
    ACTIVITYPUB = "activitypub"
    RESEARCH_API = "research_api"


class StorageRight(StrEnum):
    METADATA_ONLY = "metadata_only"
    EXCERPT_ALLOWED = "excerpt_allowed"
    FULLTEXT_TTL = "fulltext_ttl"
    FULLTEXT_PERMITTED = "fulltext_permitted"


class PollClass(StrEnum):
    BREAKING = "breaking"  # 5-15 min
    NEWS = "news"  # 15-60 min
    COMMUNITY = "community"  # 10-30 min
    RESEARCH = "research"  # 2 h
    SLOW = "slow"  # patents / OSS: 6-24 h


class ValidationStage(StrEnum):
    UNVERIFIED = "unverified"
    V0 = "V0"  # identity
    V1 = "V1"  # policy / terms
    V2 = "V2"  # security / network
    V3 = "V3"  # parser reliability
    V4 = "V4"  # 24 h canary
    V5 = "V5"  # 7 day quality
    V6 = "V6"  # active portfolio


STAGE_ORDER: tuple[ValidationStage, ...] = tuple(ValidationStage)


class SourceStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class ValidationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    RESET = "reset"
```

`apps/api/src/news_insight/sources/models.py`:

```python
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_insight.db import Base
from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationOutcome,
    ValidationStage,
)


def _enum(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_status_stage", "status", "validation_stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    track: Mapped[Track] = mapped_column(_enum(Track), index=True)
    category: Mapped[str] = mapped_column(String(40))
    access_method: Mapped[AccessMethod] = mapped_column(_enum(AccessMethod))
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    official_domain: Mapped[str] = mapped_column(String(253))
    operator: Mapped[str] = mapped_column(String(200))
    region: Mapped[Region] = mapped_column(_enum(Region))
    language: Mapped[str] = mapped_column(String(16))
    poll_class: Mapped[PollClass] = mapped_column(_enum(PollClass))
    dx_relevance: Mapped[str] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(String(2048))
    storage_right: Mapped[StorageRight | None] = mapped_column(_enum(StorageRight))
    validation_stage: Mapped[ValidationStage] = mapped_column(
        _enum(ValidationStage),
        default=ValidationStage.UNVERIFIED,
        server_default=ValidationStage.UNVERIFIED.value,
    )
    status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus),
        default=SourceStatus.CANDIDATE,
        server_default=SourceStatus.CANDIDATE.value,
    )
    paused_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    validation_events: Mapped[list["SourceValidationEvent"]] = relationship(
        back_populates="source", order_by="SourceValidationEvent.id"
    )


class SourceValidationEvent(Base):
    """Append-only audit trail of every ladder check and reset."""

    __tablename__ = "source_validation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    stage: Mapped[ValidationStage] = mapped_column(_enum(ValidationStage))
    outcome: Mapped[ValidationOutcome] = mapped_column(_enum(ValidationOutcome))
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="validation_events")
```

`apps/api/src/news_insight/model_registry.py` (전체 교체):

```python
"""Import every ORM module here so Alembic sees the complete metadata."""

import news_insight.sources.models  # noqa: F401
```

- [ ] **Step 4: 마이그레이션 작성**

`apps/api/migrations/versions/0002_source_registry.py`:

```python
"""Source registry and validation ladder audit trail.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("track", sa.String(32), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("access_method", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.String(2048), nullable=False),
        sa.Column("official_domain", sa.String(253), nullable=False),
        sa.Column("operator", sa.String(200), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("poll_class", sa.String(32), nullable=False),
        sa.Column("dx_relevance", sa.Text(), nullable=False),
        sa.Column("terms_url", sa.String(2048), nullable=True),
        sa.Column("storage_right", sa.String(32), nullable=True),
        sa.Column("validation_stage", sa.String(32), server_default="unverified", nullable=False),
        sa.Column("status", sa.String(32), server_default="candidate", nullable=False),
        sa.Column("paused_reason", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("key", name="uq_sources_key"),
    )
    op.create_index("ix_sources_track", "sources", ["track"])
    op.create_index("ix_sources_status_stage", "sources", ["status", "validation_stage"])

    op.create_table(
        "source_validation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_validation_events_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_validation_events"),
    )
    op.create_index(
        "ix_source_validation_events_source_id", "source_validation_events", ["source_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_validation_events_source_id", table_name="source_validation_events")
    op.drop_table("source_validation_events")
    op.drop_index("ix_sources_status_stage", table_name="sources")
    op.drop_index("ix_sources_track", table_name="sources")
    op.drop_table("sources")
```

- [ ] **Step 5: 테스트 통과와 모델-마이그레이션 일치 확인**

Run: `cd apps/api && uv run pytest -v && uv run alembic upgrade head && uv run alembic check`
Expected: `16 passed`, `No new upgrade operations detected.` (차이가 보고되면 보고된 컬럼의 타입·nullable을 모델 기준으로 마이그레이션에 맞추고 다시 실행)

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): add source registry schema with append-only validation events"
```

---

### Task 6: V0~V6 승격 사다리 상태 머신

**Files:**
- Create: `apps/api/src/news_insight/sources/ladder.py`
- Test: `apps/api/tests/sources/test_ladder.py`

**Interfaces:**
- Consumes: `Source`, `SourceValidationEvent`, `STAGE_ORDER`, `SourceStatus`, `ValidationOutcome`, `ValidationStage`
- Produces:
  - `class LadderError(Exception)`
  - `@dataclass(frozen=True) class CheckResult(passed: bool, reasons: list[str] = [], metrics: dict[str, Any] = {})`와 `CheckResult.from_reasons(reasons: list[str], metrics: dict[str, Any] | None = None) -> CheckResult` (`reasons`가 비어 있으면 통과)
  - `next_stage(current: ValidationStage) -> ValidationStage | None`
  - `ensure_next_stage(source: Source, stage: ValidationStage) -> None` (순서가 어긋나면 `LadderError`)
  - `record_check(session: Session, source: Source, stage: ValidationStage, result: CheckResult) -> SourceValidationEvent`
  - `reset_validation(session: Session, source: Source, *, reason: str) -> SourceValidationEvent`
  - `pause_source(session: Session, source: Source, *, reason: str) -> None`, `resume_source(session: Session, source: Source) -> None`
  - `is_schedulable(source: Source) -> bool`, `schedulable_sources(session: Session) -> list[Source]`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_ladder.py`:

```python
import pytest
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.ladder import (
    CheckResult,
    LadderError,
    is_schedulable,
    next_stage,
    pause_source,
    record_check,
    reset_validation,
    resume_source,
    schedulable_sources,
)
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db

PASS = CheckResult(passed=True)


def persisted(session: Session, **overrides: object) -> Source:
    source = build_source(**overrides)
    session.add(source)
    session.flush()
    return source


def climb_to(session: Session, source: Source, target: ValidationStage) -> None:
    for stage in STAGE_ORDER[1 : STAGE_ORDER.index(target) + 1]:
        record_check(session, source, stage, PASS)


def test_check_result_passes_only_without_reasons() -> None:
    assert CheckResult.from_reasons([]).passed is True
    failed = CheckResult.from_reasons(["terms_url is missing"], {"k": 1})
    assert failed.passed is False
    assert failed.reasons == ["terms_url is missing"]
    assert failed.metrics == {"k": 1}


def test_next_stage_walks_the_ladder() -> None:
    assert next_stage(ValidationStage.UNVERIFIED) is ValidationStage.V0
    assert next_stage(ValidationStage.V5) is ValidationStage.V6
    assert next_stage(ValidationStage.V6) is None


def test_passing_check_advances_stage_and_records_event(db_session: Session) -> None:
    source = persisted(db_session)

    event = record_check(db_session, source, ValidationStage.V0, PASS)

    assert source.validation_stage is ValidationStage.V0
    assert event.outcome is ValidationOutcome.PASSED
    assert event.source_id == source.id


def test_failing_check_keeps_stage_and_records_reasons(db_session: Session) -> None:
    source = persisted(db_session)

    event = record_check(
        db_session, source, ValidationStage.V0, CheckResult.from_reasons(["operator is missing"])
    )

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert event.outcome is ValidationOutcome.FAILED
    assert event.reasons == ["operator is missing"]


def test_skipping_a_stage_is_rejected(db_session: Session) -> None:
    source = persisted(db_session)

    with pytest.raises(LadderError, match="next stage is V0"):
        record_check(db_session, source, ValidationStage.V2, PASS)


def test_reaching_v6_activates_candidate(db_session: Session) -> None:
    source = persisted(db_session)

    climb_to(db_session, source, ValidationStage.V6)

    assert source.status is SourceStatus.ACTIVE
    assert is_schedulable(source) is True
    assert schedulable_sources(db_session) == [source]
    with pytest.raises(LadderError, match="already at V6"):
        record_check(db_session, source, ValidationStage.V6, PASS)


def test_paused_source_is_not_schedulable_until_resumed(db_session: Session) -> None:
    source = persisted(db_session)
    climb_to(db_session, source, ValidationStage.V6)

    pause_source(db_session, source, reason="selector drift")

    assert source.status is SourceStatus.PAUSED
    assert source.paused_reason == "selector drift"
    assert schedulable_sources(db_session) == []

    resume_source(db_session, source)

    assert source.status is SourceStatus.ACTIVE
    assert source.paused_reason is None


def test_resume_of_unvalidated_source_returns_to_candidate(db_session: Session) -> None:
    source = persisted(db_session)
    pause_source(db_session, source, reason="operator hold")

    resume_source(db_session, source)

    assert source.status is SourceStatus.CANDIDATE


def test_reset_returns_to_unverified_candidate(db_session: Session) -> None:
    source = persisted(db_session)
    climb_to(db_session, source, ValidationStage.V6)

    event = reset_validation(db_session, source, reason="endpoint changed")

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.status is SourceStatus.CANDIDATE
    assert event.outcome is ValidationOutcome.RESET
    assert event.reasons == ["endpoint changed"]


def test_retired_source_cannot_be_validated(db_session: Session) -> None:
    source = persisted(db_session, status=SourceStatus.RETIRED)

    with pytest.raises(LadderError, match="retired"):
        record_check(db_session, source, ValidationStage.V0, PASS)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_ladder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources.ladder'`

- [ ] **Step 3: 최소 구현**

`apps/api/src/news_insight/sources/ladder.py`:

```python
"""V0-V6 validation ladder: stages advance strictly in order and every attempt is audited."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent


class LadderError(Exception):
    """A validation step was attempted out of order or on an ineligible source."""


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_reasons(
        cls, reasons: list[str], metrics: dict[str, Any] | None = None
    ) -> "CheckResult":
        return cls(passed=not reasons, reasons=reasons, metrics=metrics or {})


def next_stage(current: ValidationStage) -> ValidationStage | None:
    index = STAGE_ORDER.index(current)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


def ensure_next_stage(source: Source, stage: ValidationStage) -> None:
    if source.status is SourceStatus.RETIRED:
        raise LadderError(f"{source.key}: retired sources cannot be validated")
    expected = next_stage(source.validation_stage)
    if expected is None:
        raise LadderError(f"{source.key}: already at {ValidationStage.V6.value}")
    if stage != expected:
        raise LadderError(f"{source.key}: next stage is {expected.value}, not {stage.value}")


def record_check(
    session: Session, source: Source, stage: ValidationStage, result: CheckResult
) -> SourceValidationEvent:
    ensure_next_stage(source, stage)
    event = SourceValidationEvent(
        source=source,
        stage=stage,
        outcome=ValidationOutcome.PASSED if result.passed else ValidationOutcome.FAILED,
        reasons=list(result.reasons),
        metrics=dict(result.metrics),
    )
    session.add(event)
    if result.passed:
        source.validation_stage = stage
        if stage is ValidationStage.V6 and source.status is SourceStatus.CANDIDATE:
            source.status = SourceStatus.ACTIVE
    session.flush()
    return event


def reset_validation(session: Session, source: Source, *, reason: str) -> SourceValidationEvent:
    source.validation_stage = ValidationStage.UNVERIFIED
    if source.status is not SourceStatus.RETIRED:
        source.status = SourceStatus.CANDIDATE
    source.paused_reason = None
    event = SourceValidationEvent(
        source=source,
        stage=ValidationStage.UNVERIFIED,
        outcome=ValidationOutcome.RESET,
        reasons=[reason],
        metrics={},
    )
    session.add(event)
    session.flush()
    return event


def pause_source(session: Session, source: Source, *, reason: str) -> None:
    if source.status is SourceStatus.RETIRED:
        raise LadderError(f"{source.key}: retired sources cannot be paused")
    source.status = SourceStatus.PAUSED
    source.paused_reason = reason
    session.flush()


def resume_source(session: Session, source: Source) -> None:
    if source.status is not SourceStatus.PAUSED:
        raise LadderError(f"{source.key}: only paused sources can resume")
    is_active = source.validation_stage is ValidationStage.V6
    source.status = SourceStatus.ACTIVE if is_active else SourceStatus.CANDIDATE
    source.paused_reason = None
    session.flush()


def is_schedulable(source: Source) -> bool:
    return source.status is SourceStatus.ACTIVE and source.validation_stage is ValidationStage.V6


def schedulable_sources(session: Session) -> list[Source]:
    statement = (
        select(Source)
        .where(Source.status == SourceStatus.ACTIVE, Source.validation_stage == ValidationStage.V6)
        .order_by(Source.key)
    )
    return list(session.scalars(statement))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_ladder.py -v`
Expected: `10 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): enforce ordered V0-V6 validation ladder with pause/reset"
```

---

### Task 7: 소스 카탈로그 (YAML 스키마 · 로더 · 시드)

**Files:**
- Create: `apps/api/src/news_insight/sources/catalog.py`, `apps/api/catalog/sources.yaml`
- Test: `apps/api/tests/sources/test_catalog.py`

**Interfaces:**
- Consumes: `Source`, enum 전체, `reset_validation` (Task 6)
- Produces:
  - `DEFAULT_CATALOG_PATH: Path` (`apps/api/catalog/sources.yaml`)
  - `class CatalogEntry(BaseModel)` (필드는 `Source`의 카탈로그 관리 필드와 동일: `key, name, track, category, access_method, endpoint_url, official_domain, operator, region, language, poll_class, dx_relevance, terms_url, storage_right, config`), `class Catalog(BaseModel)` (`version: Literal[1]`, `sources: list[CatalogEntry]`, 키 중복 금지)
  - `load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog`
  - `@dataclass(frozen=True) class SeedResult(created: list[str], updated: list[str], reset: list[str])`
  - `seed_catalog(session: Session, catalog: Catalog) -> SeedResult`. 식별 필드(`endpoint_url`, `official_domain`, `access_method`)가 바뀌면 검증을 초기화함. 카탈로그에 없는 기존 소스는 건드리지 않음

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_catalog.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.catalog import (
    DEFAULT_CATALOG_PATH,
    Catalog,
    load_catalog,
    seed_catalog,
)
from news_insight.sources.enums import (
    SourceStatus,
    Track,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source

ENTRY = """
  - key: example-news
    name: Example News
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://www.example.com/feed.xml
    official_domain: example.com
    operator: Example Media Inc.
    region: global_en
    language: en
    poll_class: news
    dx_relevance: 모바일·가전 제품 동향을 다루는 테크 미디어
    terms_url: https://www.example.com/terms
    storage_right: excerpt_allowed
"""


def write_catalog(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(f"version: 1\nsources:{body}", encoding="utf-8")
    return path


def test_load_valid_catalog(tmp_path: Path) -> None:
    catalog = load_catalog(write_catalog(tmp_path, ENTRY))

    assert [entry.key for entry in catalog.sources] == ["example-news"]
    assert catalog.sources[0].track is Track.NEWS


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="duplicate source keys: example-news"):
        load_catalog(write_catalog(tmp_path, ENTRY + ENTRY))


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_catalog(write_catalog(tmp_path, ENTRY + "    surprise: true\n"))


def test_non_http_endpoint_is_rejected(tmp_path: Path) -> None:
    body = ENTRY.replace("https://www.example.com/feed.xml", "ftp://example.com/feed.xml")

    with pytest.raises(ValidationError, match="absolute http"):
        load_catalog(write_catalog(tmp_path, body))


def test_bundled_catalog_loads_and_covers_every_track() -> None:
    catalog = load_catalog(DEFAULT_CATALOG_PATH)

    assert {entry.track for entry in catalog.sources} == set(Track)


@pytest.mark.db
def test_seed_creates_candidates_and_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    catalog = load_catalog(write_catalog(tmp_path, ENTRY))

    first = seed_catalog(db_session, catalog)
    second = seed_catalog(db_session, catalog)

    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    assert first.created == ["example-news"]
    assert (second.created, second.updated, second.reset) == ([], [], [])
    assert source.status is SourceStatus.CANDIDATE
    assert source.validation_stage is ValidationStage.UNVERIFIED


@pytest.mark.db
def test_seed_updates_descriptive_fields_without_reset(db_session: Session, tmp_path: Path) -> None:
    seed_catalog(db_session, load_catalog(write_catalog(tmp_path, ENTRY)))
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    record_check(db_session, source, ValidationStage.V0, CheckResult(passed=True))

    renamed = ENTRY.replace("name: Example News", "name: Example News Daily")
    result = seed_catalog(db_session, load_catalog(write_catalog(tmp_path, renamed)))

    assert result.updated == ["example-news"]
    assert source.name == "Example News Daily"
    assert source.validation_stage is ValidationStage.V0


@pytest.mark.db
def test_seed_resets_validation_when_endpoint_changes(db_session: Session, tmp_path: Path) -> None:
    seed_catalog(db_session, load_catalog(write_catalog(tmp_path, ENTRY)))
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    record_check(db_session, source, ValidationStage.V0, CheckResult(passed=True))

    moved = ENTRY.replace("/feed.xml", "/rss.xml")
    result = seed_catalog(db_session, load_catalog(write_catalog(tmp_path, moved)))

    assert result.reset == ["example-news"]
    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.validation_events[-1].outcome is ValidationOutcome.RESET


def test_catalog_model_requires_version_1() -> None:
    with pytest.raises(ValidationError):
        Catalog.model_validate({"version": 2, "sources": []})
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources.catalog'`

- [ ] **Step 3: 카탈로그 모듈 구현**

`apps/api/src/news_insight/sources/catalog.py`:

```python
"""Declarative source catalog (YAML) and idempotent seeding into the registry."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationStage,
)
from news_insight.sources.ladder import reset_validation
from news_insight.sources.models import Source

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "sources.yaml"
IDENTITY_FIELDS = ("endpoint_url", "official_domain", "access_method")


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
    name: str = Field(min_length=1, max_length=200)
    track: Track
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    access_method: AccessMethod
    endpoint_url: str = Field(max_length=2048)
    official_domain: str = Field(pattern=r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", max_length=253)
    operator: str = Field(min_length=1, max_length=200)
    region: Region
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Za-z]{2,4})?$")
    poll_class: PollClass
    dx_relevance: str = Field(min_length=10)
    terms_url: str | None = None
    storage_right: StorageRight | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_url", "terms_url")
    @classmethod
    def _absolute_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError(f"must be an absolute http(s) URL: {value}")
        return value


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    sources: list[CatalogEntry]

    @model_validator(mode="after")
    def _unique_keys(self) -> "Catalog":
        counts = Counter(entry.key for entry in self.sources)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate source keys: {', '.join(duplicates)}")
        return self


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)


@dataclass(frozen=True)
class SeedResult:
    created: list[str]
    updated: list[str]
    reset: list[str]


def seed_catalog(session: Session, catalog: Catalog) -> SeedResult:
    keys = [entry.key for entry in catalog.sources]
    existing = {
        source.key: source
        for source in session.scalars(select(Source).where(Source.key.in_(keys)))
    }
    created: list[str] = []
    updated: list[str] = []
    reset: list[str] = []
    for entry in catalog.sources:
        values = entry.model_dump()
        source = existing.get(entry.key)
        if source is None:
            session.add(
                Source(
                    **values,
                    validation_stage=ValidationStage.UNVERIFIED,
                    status=SourceStatus.CANDIDATE,
                )
            )
            created.append(entry.key)
            continue
        identity_changed = any(getattr(source, name) != values[name] for name in IDENTITY_FIELDS)
        changed = False
        for name, value in values.items():
            if getattr(source, name) != value:
                setattr(source, name, value)
                changed = True
        if identity_changed:
            reset_validation(session, source, reason="catalog identity fields changed")
            reset.append(entry.key)
        elif changed:
            updated.append(entry.key)
    session.flush()
    return SeedResult(created=created, updated=updated, reset=reset)
```

- [ ] **Step 4: 카탈로그 초안 작성**

`apps/api/catalog/sources.yaml`. 모든 항목은 **검토 전 후보**입니다. `terms_url`을 비워 두었기 때문에 운영자가 이용약관을 검토하고 채우기 전까지는 V1에서 의도적으로 실패합니다. Phase 3에서 260개로 확장합니다.

```yaml
version: 1
sources:
  # ── Track 1: IT 기술 뉴스 및 공식 소스 ──
  - key: the-verge
    name: The Verge
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://www.theverge.com/rss/index.xml
    official_domain: theverge.com
    operator: Vox Media
    region: global_en
    language: en
    poll_class: news
    dx_relevance: 모바일·디스플레이·스마트홈 완제품 리뷰와 업계 동향 보도
    storage_right: metadata_only
  - key: ars-technica
    name: Ars Technica
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://feeds.arstechnica.com/arstechnica/index
    official_domain: arstechnica.com
    operator: Condé Nast
    region: global_en
    language: en
    poll_class: news
    dx_relevance: 소비자 기기, 통신, 보안 기술의 심층 분석 기사
    storage_right: metadata_only
  - key: etnews
    name: 전자신문
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://rss.etnews.com/Section901.xml
    official_domain: etnews.com
    operator: 전자신문사
    region: kr
    language: ko
    poll_class: news
    dx_relevance: 국내 전자·통신·가전 산업과 정책 동향 보도
    storage_right: metadata_only
  - key: itmedia-news
    name: ITmedia NEWS
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml
    official_domain: itmedia.co.jp
    operator: ITmedia Inc.
    region: jp
    language: ja
    poll_class: news
    dx_relevance: 일본 전자·모바일·AI 산업 뉴스와 제조사 발표
    storage_right: metadata_only
  - key: google-blog
    name: Google The Keyword
    track: news
    category: official_vendor
    access_method: feed
    endpoint_url: https://blog.google/rss/
    official_domain: blog.google
    operator: Google LLC
    region: global_en
    language: en
    poll_class: news
    dx_relevance: Android·온디바이스 AI·스마트홈 플랫폼 공식 발표
    storage_right: metadata_only

  # ── Track 2: 커뮤니티 및 공개 SNS ──
  - key: hacker-news
    name: Hacker News Front Page
    track: community
    category: dev_forum
    access_method: feed
    endpoint_url: https://news.ycombinator.com/rss
    official_domain: ycombinator.com
    operator: Y Combinator
    region: global_en
    language: en
    poll_class: community
    dx_relevance: 개발자 커뮤니티의 기술 화제와 오픈소스 반응 신호
    storage_right: metadata_only
  - key: bluesky-official
    name: Bluesky Official Account
    track: community
    category: open_social
    access_method: atproto
    endpoint_url: https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed
    official_domain: bsky.app
    operator: Bluesky Social PBC
    region: global_en
    language: en
    poll_class: community
    dx_relevance: 탈중앙 소셜 프로토콜과 공개 기술 커뮤니티 신호
    storage_right: metadata_only
    config:
      actor: bsky.app
      probe_url: https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=bsky.app&limit=5

  # ── Track 3: 논문·학회·표준·특허 ──
  - key: arxiv-cs-ai
    name: arXiv cs.AI
    track: research_ip
    category: academic_paper
    access_method: feed
    endpoint_url: https://rss.arxiv.org/rss/cs.AI
    official_domain: arxiv.org
    operator: Cornell University
    region: global_en
    language: en
    poll_class: research
    dx_relevance: 온디바이스 AI·에이전트·멀티모달 모델 연구 동향
    storage_right: metadata_only
    config:
      probe_max_age_days: 7
  - key: openalex-works
    name: OpenAlex Works
    track: research_ip
    category: academic_index
    access_method: research_api
    endpoint_url: https://api.openalex.org/works
    official_domain: openalex.org
    operator: OurResearch
    region: global_en
    language: en
    poll_class: research
    dx_relevance: DX 기술 키워드 기반 논문 메타데이터와 인용 신호
    storage_right: metadata_only
    config:
      probe_url: https://api.openalex.org/works?per-page=5

  # ── Track 4: GitHub 오픈소스 트렌드 ──
  - key: github-on-device-ai
    name: GitHub On-device AI Trend
    track: oss
    category: oss_trend
    access_method: github
    endpoint_url: https://api.github.com/search/repositories
    official_domain: github.com
    operator: GitHub, Inc.
    region: global_en
    language: en
    poll_class: slow
    dx_relevance: 온디바이스 LLM·NPU 추론 런타임 오픈소스 급상승 신호
    storage_right: metadata_only
    config:
      query: "on-device llm in:name,description,readme pushed:>{today-30d}"
      sort: stars
      probe_url: https://api.github.com/rate_limit
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_catalog.py -v`
Expected: `9 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): add validated YAML source catalog with idempotent seeding"
```

---

### Task 8: V0 정체성 검사 · V1 정책 검사

**Files:**
- Create: `apps/api/src/news_insight/sources/checks.py`
- Test: `apps/api/tests/sources/test_checks_policy.py`

**Interfaces:**
- Consumes: `Source`, `CheckResult`, enum
- Produces: `probe_url(source: Source) -> str` (`config.probe_url`이 있으면 그 값, 없으면 `endpoint_url`), `check_identity(source: Source) -> CheckResult` (V0), `check_policy(source: Source) -> CheckResult` (V1), `REGION_LANGUAGES: dict[Region, frozenset[str] | None]`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_checks_policy.py` (DB 불필요. 저장하지 않은 `Source` 객체를 사용):

```python
from news_insight.sources.checks import check_identity, check_policy, probe_url
from news_insight.sources.enums import AccessMethod, Region, StorageRight, Track
from tests.factories import build_source


def test_identity_passes_for_subdomain_of_official_domain() -> None:
    result = check_identity(build_source(endpoint_url="https://feeds.example.com/rss"))

    assert result.passed, result.reasons
    assert result.metrics["endpoint_host"] == "feeds.example.com"


def test_identity_rejects_foreign_host() -> None:
    result = check_identity(build_source(endpoint_url="https://evil-example.com/rss"))

    assert not result.passed
    assert "endpoint host 'evil-example.com' is not under official domain 'example.com'" in (
        result.reasons
    )


def test_identity_accepts_explicitly_allowed_host() -> None:
    source = build_source(
        endpoint_url="https://feeds.feedburner.com/example",
        config={"allowed_hosts": ["feeds.feedburner.com"]},
    )

    assert check_identity(source).passed


def test_identity_checks_probe_url_host_too() -> None:
    source = build_source(config={"probe_url": "https://other.org/probe"})

    result = check_identity(source)

    assert "probe host 'other.org' is not under official domain 'example.com'" in result.reasons


def test_identity_requires_operator_and_dx_rationale() -> None:
    result = check_identity(build_source(operator=" ", dx_relevance="short"))

    assert "operator is missing" in result.reasons
    assert "dx_relevance rationale is missing or too short" in result.reasons


def test_identity_flags_language_region_mismatch() -> None:
    result = check_identity(build_source(region=Region.KR, language="ja"))

    assert "language 'ja' does not match region 'kr'" in result.reasons


def test_identity_allows_any_language_for_eu_other() -> None:
    assert check_identity(build_source(region=Region.EU_OTHER, language="de")).passed


def test_policy_passes_with_terms_and_storage_right() -> None:
    assert check_policy(build_source()).passed


def test_policy_requires_https_terms_and_storage_right() -> None:
    missing = check_policy(build_source(terms_url=None, storage_right=None))
    insecure = check_policy(build_source(terms_url="http://www.example.com/terms"))

    assert missing.reasons == ["terms_url is missing", "storage_right is not declared"]
    assert insecure.reasons == ["terms_url must use https"]


def test_policy_requires_reviewed_declarative_crawler() -> None:
    result = check_policy(build_source(access_method=AccessMethod.CRAWLER, config={}))

    assert result.reasons == [
        "crawler requires config.crawl_permitted=true after terms review",
        "crawler requires config.robots_checked=true",
        "crawler requires declarative config.selectors",
    ]


def test_policy_blocks_research_fulltext_without_open_access() -> None:
    source = build_source(track=Track.RESEARCH_IP, storage_right=StorageRight.FULLTEXT_PERMITTED)

    result = check_policy(source)

    assert not result.passed
    assert "paywall bypass is forbidden" in result.reasons[0]


def test_policy_allows_research_fulltext_with_open_access() -> None:
    source = build_source(
        track=Track.RESEARCH_IP,
        storage_right=StorageRight.FULLTEXT_TTL,
        config={"open_access": True},
    )

    assert check_policy(source).passed


def test_probe_url_prefers_config_override() -> None:
    assert probe_url(build_source()) == "https://www.example.com/feed.xml"
    assert probe_url(build_source(config={"probe_url": "https://example.com/p"})) == (
        "https://example.com/p"
    )
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_checks_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources.checks'`

- [ ] **Step 3: 최소 구현**

`apps/api/src/news_insight/sources/checks.py`:

```python
"""Pure validation checks for ladder stages. They never touch the database."""

from urllib.parse import urlsplit

from news_insight.sources.enums import AccessMethod, Region, StorageRight, Track
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source

REGION_LANGUAGES: dict[Region, frozenset[str] | None] = {
    Region.KR: frozenset({"ko", "en"}),
    Region.GLOBAL_EN: frozenset({"en"}),
    Region.JP: frozenset({"ja", "en"}),
    Region.GREATER_CHINA: frozenset({"zh", "en"}),
    Region.EU_OTHER: None,
}
FULLTEXT_RIGHTS = frozenset({StorageRight.FULLTEXT_TTL, StorageRight.FULLTEXT_PERMITTED})


def probe_url(source: Source) -> str:
    return str(source.config.get("probe_url") or source.endpoint_url)


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def check_identity(source: Source) -> CheckResult:
    """V0: official domain, operator, region/language and DX relevance."""
    reasons: list[str] = []
    allowed_hosts = {str(host).lower() for host in source.config.get("allowed_hosts", [])}
    endpoint_host = (urlsplit(source.endpoint_url).hostname or "").lower()
    for label, url in (("endpoint", source.endpoint_url), ("probe", source.config.get("probe_url"))):
        if not url:
            continue
        host = (urlsplit(str(url)).hostname or "").lower()
        if not (_host_matches(host, source.official_domain) or host in allowed_hosts):
            reasons.append(
                f"{label} host '{host}' is not under official domain '{source.official_domain}'"
            )
    if not source.operator.strip():
        reasons.append("operator is missing")
    if len(source.dx_relevance.strip()) < 10:
        reasons.append("dx_relevance rationale is missing or too short")
    expected = REGION_LANGUAGES[source.region]
    primary_language = source.language.split("-", 1)[0].lower()
    if expected is not None and primary_language not in expected:
        reasons.append(
            f"language '{source.language}' does not match region '{source.region.value}'"
        )
    return CheckResult.from_reasons(reasons, {"endpoint_host": endpoint_host})


def check_policy(source: Source) -> CheckResult:
    """V1: terms reviewed, storage right declared, crawler and paywall rules."""
    reasons: list[str] = []
    if not source.terms_url:
        reasons.append("terms_url is missing")
    elif urlsplit(source.terms_url).scheme != "https":
        reasons.append("terms_url must use https")
    if source.storage_right is None:
        reasons.append("storage_right is not declared")
    if source.access_method is AccessMethod.CRAWLER:
        if source.config.get("crawl_permitted") is not True:
            reasons.append("crawler requires config.crawl_permitted=true after terms review")
        if source.config.get("robots_checked") is not True:
            reasons.append("crawler requires config.robots_checked=true")
        if not source.config.get("selectors"):
            reasons.append("crawler requires declarative config.selectors")
    if (
        source.track is Track.RESEARCH_IP
        and source.storage_right in FULLTEXT_RIGHTS
        and source.config.get("open_access") is not True
    ):
        reasons.append(
            "full-text storage for research/IP requires config.open_access=true "
            "(paywall bypass is forbidden)"
        )
    storage = source.storage_right.value if source.storage_right else None
    return CheckResult.from_reasons(reasons, {"storage_right": storage})
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_checks_policy.py -v`
Expected: `13 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): add V0 identity and V1 policy checks"
```

---

### Task 9: V2 SSRF 안전 Fetcher와 네트워크 검사

**Files:**
- Create: `apps/api/src/news_insight/net/__init__.py`, `apps/api/src/news_insight/net/safe_fetch.py`
- Modify: `apps/api/src/news_insight/sources/checks.py` (`EXPECTED_MIME`, `check_network` 추가)
- Test: `apps/api/tests/net/__init__.py`, `apps/api/tests/net/test_safe_fetch.py`, `apps/api/tests/sources/test_checks_network.py`

**Interfaces:**
- Consumes: `Settings.fetch_timeout_seconds`, `fetch_max_redirects`, `fetch_max_bytes`, `CheckResult`, `probe_url`
- Produces:
  - `safe_fetch.py`: `Resolver = Callable[[str, int], list[str]]`, `system_resolver`, `assert_public_ip(raw: str) -> None`, `class FetchError(Exception)` (속성 `code: str`), `class FetchBlocked(FetchError)`, `class FetchFailed(FetchError)`, `@dataclass(frozen=True) class FetchResponse(url: str, status_code: int, headers: Mapping[str, str], content: bytes, content_type: str, redirects: tuple[str, ...], elapsed_ms: int)`, `class SafeFetcher` (`__init__(*, client=None, resolver=system_resolver, timeout_seconds=15.0, max_redirects=3, max_bytes=5 MiB, verify_peer=True, user_agent=DEFAULT_USER_AGENT)`, `from_settings(settings) -> SafeFetcher`, `fetch(url, *, allowed_mime: frozenset[str] | None = None, headers: Mapping[str, str] | None = None) -> FetchResponse`, context manager, `close()`)
  - 차단 코드: `scheme`, `userinfo`, `host`, `port`, `private_address`, `peer_address`, `mime`, `too_large`, `too_many_redirects`. 실패 코드: `dns`, `timeout`, `transport`, `bad_redirect`
  - `checks.py`: `FEED_MIME: frozenset[str]`, `EXPECTED_MIME: dict[AccessMethod, frozenset[str]]`, `check_network(source: Source, fetcher: SafeFetcher) -> CheckResult` (V2)
  - Phase 2의 모든 수집기는 이 `SafeFetcher`를 거쳐 요청함

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/net/__init__.py`: 빈 파일

`apps/api/tests/net/test_safe_fetch.py`:

```python
from collections.abc import Callable

import httpx
import pytest

from news_insight.net.safe_fetch import FetchBlocked, FetchFailed, SafeFetcher

PUBLIC_IP = "93.184.216.34"
Handler = Callable[[httpx.Request], httpx.Response]


def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


def make_fetcher(
    handler: Handler,
    *,
    resolver: Callable[[str, int], list[str]] = public_resolver,
    verify_peer: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
) -> SafeFetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return SafeFetcher(
        client=client, resolver=resolver, verify_peer=verify_peer, max_bytes=max_bytes
    )


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=b"<rss/>")


class FakeStream:
    def __init__(self, address: str) -> None:
        self.address = address

    def get_extra_info(self, info: str) -> tuple[str, int] | None:
        return (self.address, 443) if info == "server_addr" else None


def test_fetches_public_https_resource() -> None:
    response = make_fetcher(ok).fetch("https://example.com/feed")

    assert response.status_code == 200
    assert response.content == b"<rss/>"
    assert response.content_type == "application/rss+xml"
    assert response.redirects == ()


def test_sends_identifying_user_agent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return ok(request)

    make_fetcher(handler).fetch("https://example.com/feed")

    assert seen[0].startswith("DailyITIntelligenceBot/")


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://example.com/feed", "scheme"),
        ("https://user:pw@example.com/feed", "userinfo"),
        ("https://example.com:8443/feed", "port"),
    ],
)
def test_rejects_unsafe_urls(url: str, code: str) -> None:
    with pytest.raises(FetchBlocked) as error:
        make_fetcher(ok).fetch(url)

    assert error.value.code == code


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "127.0.0.1",
        "169.254.169.254",
        "192.168.1.10",
        "100.64.0.1",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
    ],
)
def test_rejects_non_public_resolution(address: str) -> None:
    fetcher = make_fetcher(ok, resolver=lambda host, port: [address])

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/feed")

    assert error.value.code == "private_address"


def test_rejects_when_any_resolved_address_is_private() -> None:
    fetcher = make_fetcher(ok, resolver=lambda host, port: [PUBLIC_IP, "10.0.0.1"])

    with pytest.raises(FetchBlocked):
        fetcher.fetch("https://example.com/feed")


def test_unresolvable_host_fails() -> None:
    def resolver(host: str, port: int) -> list[str]:
        raise OSError("nodename nor servname provided")

    with pytest.raises(FetchFailed) as error:
        make_fetcher(ok, resolver=resolver).fetch("https://example.com/feed")

    assert error.value.code == "dns"


def redirect_chain(hops: dict[str, str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in hops:
            return httpx.Response(302, headers={"location": hops[request.url.path]})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"done")

    return handler


def test_follows_up_to_three_redirects() -> None:
    fetcher = make_fetcher(redirect_chain({"/a": "/b", "/b": "/c", "/c": "/d"}))

    response = fetcher.fetch("https://example.com/a")

    assert response.content == b"done"
    assert response.url == "https://example.com/d"
    assert response.redirects == (
        "https://example.com/b",
        "https://example.com/c",
        "https://example.com/d",
    )


def test_rejects_fourth_redirect() -> None:
    fetcher = make_fetcher(redirect_chain({"/a": "/b", "/b": "/c", "/c": "/d", "/d": "/e"}))

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "too_many_redirects"


def test_revalidates_every_redirect_hop() -> None:
    def resolver(host: str, port: int) -> list[str]:
        return ["10.0.0.1"] if host == "internal.example" else [PUBLIC_IP]

    fetcher = make_fetcher(redirect_chain({"/a": "https://internal.example/x"}), resolver=resolver)

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "private_address"


def test_redirect_without_location_fails() -> None:
    fetcher = make_fetcher(lambda request: httpx.Response(302))

    with pytest.raises(FetchFailed) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "bad_redirect"


def test_rejects_unexpected_mime() -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"")

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(html).fetch(
            "https://example.com/feed", allowed_mime=frozenset({"application/rss+xml"})
        )

    assert error.value.code == "mime"


def test_rejects_declared_oversized_body() -> None:
    fetcher = make_fetcher(
        lambda request: httpx.Response(200, content=b"x" * 2000), max_bytes=1000
    )

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/big")

    assert error.value.code == "too_large"


def test_rejects_streamed_oversized_body_without_content_length() -> None:
    def chunked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=iter([b"a" * 600, b"b" * 600]))

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(chunked, max_bytes=1000).fetch("https://example.com/big")

    assert error.value.code == "too_large"


def test_peer_verification_blocks_rebinding_to_private_address() -> None:
    def rebound(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"secret", extensions={"network_stream": FakeStream("10.0.0.9")}
        )

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(rebound, verify_peer=True).fetch("https://example.com/feed")

    assert error.value.code == "private_address"


def test_peer_verification_requires_known_peer() -> None:
    with pytest.raises(FetchBlocked) as error:
        make_fetcher(ok, verify_peer=True).fetch("https://example.com/feed")

    assert error.value.code == "peer_address"


def test_peer_verification_accepts_public_peer() -> None:
    def public(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"ok", extensions={"network_stream": FakeStream(PUBLIC_IP)}
        )

    assert make_fetcher(public, verify_peer=True).fetch("https://example.com/").content == b"ok"


def test_timeout_is_reported_as_failure() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(FetchFailed) as error:
        make_fetcher(slow).fetch("https://example.com/feed")

    assert error.value.code == "timeout"
```

`apps/api/tests/sources/test_checks_network.py`:

```python
import httpx

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import EXPECTED_MIME, check_network
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source


def fetcher_returning(status: int, content_type: str) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"content-type": content_type}, content=b"<rss/>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SafeFetcher(
        client=client, resolver=lambda host, port: ["93.184.216.34"], verify_peer=False
    )


def test_every_access_method_declares_expected_mime() -> None:
    assert set(EXPECTED_MIME) == set(AccessMethod)


def test_network_check_passes_for_feed_mime() -> None:
    result = check_network(build_source(), fetcher_returning(200, "application/rss+xml"))

    assert result.passed, result.reasons
    assert result.metrics["status"] == 200
    assert result.metrics["content_type"] == "application/rss+xml"


def test_network_check_reports_blocked_mime() -> None:
    result = check_network(build_source(), fetcher_returning(200, "text/html"))

    assert not result.passed
    assert result.metrics["error"] == "mime"


def test_network_check_fails_on_non_200() -> None:
    result = check_network(build_source(), fetcher_returning(404, "text/html"))

    assert result.reasons == ["unexpected HTTP status 404"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/net tests/sources/test_checks_network.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.net'`

- [ ] **Step 3: Safe Fetcher 구현**

`apps/api/src/news_insight/net/__init__.py`: 빈 파일

`apps/api/src/news_insight/net/safe_fetch.py`:

```python
"""SSRF-safe HTTP fetcher shared by source validation (V2) and collectors.

Safety layers: https-only on port 443, no URL credentials, every resolved address must be
public, every redirect hop is re-validated (max 3), the connected peer address is re-checked
to defeat DNS rebinding, MIME allow-list, and a streamed byte cap.
"""

import ipaddress
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType

import httpx

from news_insight import __version__
from news_insight.config import Settings

Resolver = Callable[[str, int], list[str]]
DEFAULT_USER_AGENT = f"DailyITIntelligenceBot/{__version__}"
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FetchBlocked(FetchError):
    """Refused by a safety policy."""


class FetchFailed(FetchError):
    """Could not be completed (DNS, timeout, transport, malformed redirect)."""


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def assert_public_ip(raw: str) -> None:
    address = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global or address.is_multicast:
        raise FetchBlocked("private_address", f"refusing non-public address {raw}")


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    content_type: str
    redirects: tuple[str, ...]
    elapsed_ms: int


class SafeFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = system_resolver,
        timeout_seconds: float = 15.0,
        max_redirects: int = 3,
        max_bytes: int = 5 * 1024 * 1024,
        verify_peer: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds), follow_redirects=False, trust_env=False
        )
        self._resolver = resolver
        self._max_redirects = max_redirects
        self._max_bytes = max_bytes
        self._verify_peer = verify_peer
        self._user_agent = user_agent

    @classmethod
    def from_settings(cls, settings: Settings) -> "SafeFetcher":
        return cls(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_redirects=settings.fetch_max_redirects,
            max_bytes=settings.fetch_max_bytes,
        )

    def __enter__(self) -> "SafeFetcher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(
        self,
        url: str,
        *,
        allowed_mime: frozenset[str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResponse:
        started = time.monotonic()
        request_headers = {"User-Agent": self._user_agent, **(headers or {})}
        current = url
        redirects: list[str] = []
        for _ in range(self._max_redirects + 1):
            self._validate_target(current)
            try:
                with self._client.stream("GET", current, headers=request_headers) as response:
                    self._check_peer(response)
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchFailed("bad_redirect", f"redirect without Location: {current}")
                        current = str(response.url.join(location))
                        redirects.append(current)
                        continue
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    if (
                        allowed_mime is not None
                        and response.status_code == 200
                        and content_type not in allowed_mime
                    ):
                        raise FetchBlocked("mime", f"unexpected content type '{content_type}'")
                    body = self._read_limited(response)
                    return FetchResponse(
                        url=current,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content=body,
                        content_type=content_type,
                        redirects=tuple(redirects),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
            except httpx.TimeoutException as exc:
                raise FetchFailed("timeout", f"timed out fetching {current}") from exc
            except httpx.TransportError as exc:
                raise FetchFailed("transport", f"transport error fetching {current}: {exc}") from exc
        raise FetchBlocked("too_many_redirects", f"more than {self._max_redirects} redirects")

    def _validate_target(self, url: str) -> None:
        parts = httpx.URL(url)
        if parts.scheme != "https":
            raise FetchBlocked("scheme", f"only https is allowed: {url}")
        if parts.userinfo:
            raise FetchBlocked("userinfo", "credentials in URLs are not allowed")
        host = parts.host
        if not host:
            raise FetchBlocked("host", f"missing host: {url}")
        port = parts.port or 443
        if port != 443:
            raise FetchBlocked("port", f"only port 443 is allowed: {url}")
        try:
            addresses = self._resolver(host, port)
        except OSError as exc:
            raise FetchFailed("dns", f"cannot resolve {host}") from exc
        if not addresses:
            raise FetchFailed("dns", f"no addresses for {host}")
        for address in addresses:
            assert_public_ip(address)

    def _check_peer(self, response: httpx.Response) -> None:
        if not self._verify_peer:
            return
        stream = response.extensions.get("network_stream")
        server_addr = stream.get_extra_info("server_addr") if stream is not None else None
        if not server_addr:
            raise FetchBlocked("peer_address", "cannot confirm the connected peer address")
        assert_public_ip(str(server_addr[0]))

    def _read_limited(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_bytes:
            raise FetchBlocked("too_large", f"declared size {declared} exceeds {self._max_bytes}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > self._max_bytes:
                raise FetchBlocked("too_large", f"response exceeds {self._max_bytes} bytes")
        return bytes(body)
```

- [ ] **Step 4: V2 네트워크 검사 추가**

`apps/api/src/news_insight/sources/checks.py`에서 import 블록을 다음으로 교체:

```python
from urllib.parse import urlsplit

from news_insight.net.safe_fetch import FetchError, SafeFetcher
from news_insight.sources.enums import AccessMethod, Region, StorageRight, Track
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source
```

`FULLTEXT_RIGHTS` 정의 바로 아래에 추가:

```python
FEED_MIME = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/rdf+xml",
        "application/xml",
        "text/xml",
    }
)
JSON_MIME = frozenset({"application/json", "application/activity+json", "application/ld+json"})
EXPECTED_MIME: dict[AccessMethod, frozenset[str]] = {
    AccessMethod.FEED: FEED_MIME,
    AccessMethod.JSON_API: JSON_MIME,
    AccessMethod.CRAWLER: frozenset({"text/html", "application/xhtml+xml"}),
    AccessMethod.GITHUB: JSON_MIME,
    AccessMethod.ATPROTO: JSON_MIME,
    AccessMethod.ACTIVITYPUB: JSON_MIME,
    AccessMethod.RESEARCH_API: JSON_MIME | FEED_MIME,
}
```

파일 끝에 추가:

```python
def check_network(source: Source, fetcher: SafeFetcher) -> CheckResult:
    """V2: SSRF/DNS-rebinding guard, TLS, MIME and size limits via SafeFetcher."""
    try:
        response = fetcher.fetch(probe_url(source), allowed_mime=EXPECTED_MIME[source.access_method])
    except FetchError as exc:
        return CheckResult.from_reasons([str(exc)], {"error": exc.code})
    reasons: list[str] = []
    if response.status_code != 200:
        reasons.append(f"unexpected HTTP status {response.status_code}")
    return CheckResult.from_reasons(
        reasons,
        {
            "status": response.status_code,
            "content_type": response.content_type,
            "bytes": len(response.content),
            "redirects": len(response.redirects),
            "elapsed_ms": response.elapsed_ms,
        },
    )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/net tests/sources/test_checks_network.py -v`
Expected: `31 passed` (`test_safe_fetch.py` 27개 + `test_checks_network.py` 4개)

- [ ] **Step 6: 실제 네트워크 스모크 테스트 (수동, 1회)**

Run: `cd apps/api && uv run python -c "from news_insight.net.safe_fetch import SafeFetcher; r = SafeFetcher().fetch('https://news.ycombinator.com/rss'); print(r.status_code, r.content_type, len(r.content))"`
Expected: `200 application/rss+xml <bytes>`. 실제 httpcore 연결에서 `network_stream` 피어 검증이 동작하는지 확인하는 단계. `peer_address` 오류가 나면 HTTP 프록시 환경 변수의 영향인지 확인

- [ ] **Step 7: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(net): add SSRF-safe fetcher and V2 network validation"
```

---

### Task 10: V3 Feed 파서 신뢰성 검사

**Files:**
- Create: `apps/api/src/news_insight/parsers/__init__.py`, `apps/api/src/news_insight/parsers/feed_probe.py`
- Modify: `apps/api/src/news_insight/sources/checks.py` (`check_parser` 추가)
- Test: `apps/api/tests/parsers/__init__.py`, `apps/api/tests/parsers/test_feed_probe.py`, `apps/api/tests/sources/test_checks_parser.py`

**Interfaces:**
- Consumes: `CheckResult`, `SafeFetcher`, `FetchError`, `FEED_MIME`, `probe_url`
- Produces: `feed_probe.MIN_PROBE_ITEMS = 3`, `@dataclass(frozen=True) ProbedItem(stable_id: str, url: str, title: str, published_at: datetime)`, `extract_items(content: bytes) -> list[ProbedItem]`, `probe_feed(content: bytes, *, now: datetime, min_items: int = 3, max_age_days: int = 30) -> CheckResult`. `checks.check_parser(source: Source, fetcher: SafeFetcher, *, now: datetime) -> CheckResult` (V3, `config.probe_min_items`는 3 미만으로 내려가지 않음, `config.probe_max_age_days` 지원, Feed가 아닌 접근 방식은 사유와 함께 실패 처리 — Phase 3에서 어댑터별 프로브 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/parsers/__init__.py`: 빈 파일

`apps/api/tests/parsers/test_feed_probe.py`:

```python
from datetime import UTC, datetime

from news_insight.parsers.feed_probe import extract_items, probe_feed

NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)
RECENT = "Thu, 01 Oct 2026 09:00:00 GMT"
STALE = "Mon, 01 Jun 2026 09:00:00 GMT"


def rss(*items: dict[str, str]) -> bytes:
    body = ""
    for item in items:
        title = f"<title>{item['title']}</title>" if item.get("title") else ""
        body += (
            f"<item><guid>{item['guid']}</guid><link>{item['link']}</link>{title}"
            f"<pubDate>{item['date']}</pubDate></item>"
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        f"<link>https://example.com</link><description>d</description>{body}</channel></rss>"
    ).encode()


def item(n: int, date: str = RECENT, title: str = "Title") -> dict[str, str]:
    return {"guid": f"id-{n}", "link": f"https://example.com/{n}", "title": f"{title} {n}", "date": date}


def test_three_complete_recent_items_pass() -> None:
    result = probe_feed(rss(item(1), item(2), item(3)), now=NOW)

    assert result.passed, result.reasons
    assert result.metrics == {"entries": 3, "complete": 3, "recent": 3}


def test_items_missing_required_fields_do_not_count() -> None:
    incomplete = {"guid": "id-3", "link": "https://example.com/3", "title": "", "date": RECENT}

    result = probe_feed(rss(item(1), item(2), incomplete), now=NOW)

    assert result.reasons == ["only 2 recent complete items (need 3)"]


def test_stale_items_do_not_count() -> None:
    result = probe_feed(rss(item(1), item(2), item(3, date=STALE)), now=NOW)

    assert not result.passed
    assert result.metrics["recent"] == 2


def test_atom_feed_is_supported() -> None:
    entries = "".join(
        f'<entry><id>urn:{n}</id><title>A {n}</title><link href="https://example.com/{n}"/>'
        f"<updated>2026-10-01T09:00:00Z</updated></entry>"
        for n in range(3)
    )
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><id>urn:feed</id>'
        f"<updated>2026-10-01T09:00:00Z</updated>{entries}</feed>"
    ).encode()

    assert probe_feed(atom, now=NOW).passed


def test_garbage_is_rejected() -> None:
    result = probe_feed(b"definitely not a feed", now=NOW)

    assert result.reasons[0].startswith("feed could not be parsed")


def test_extract_items_returns_normalized_fields() -> None:
    [first] = extract_items(rss(item(7)))

    assert first.stable_id == "id-7"
    assert first.url == "https://example.com/7"
    assert first.title == "Title 7"
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
```

`apps/api/tests/sources/test_checks_parser.py`:

```python
from datetime import UTC, datetime

import httpx

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import check_parser
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source
from tests.parsers.test_feed_probe import item, rss

NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


def fetcher_serving(content: bytes) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=content)

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )


def test_parser_check_passes_for_healthy_feed() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2), item(3)))

    assert check_parser(build_source(), fetcher, now=NOW).passed


def test_parser_check_never_lowers_minimum_below_three() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2)))

    result = check_parser(build_source(config={"probe_min_items": 1}), fetcher, now=NOW)

    assert result.reasons == ["only 2 recent complete items (need 3)"]


def test_parser_check_honours_max_age_override() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2), item(3)))

    result = check_parser(build_source(config={"probe_max_age_days": 1}), fetcher, now=NOW)

    assert not result.passed


def test_non_feed_access_methods_fail_closed() -> None:
    source = build_source(access_method=AccessMethod.GITHUB)

    result = check_parser(source, fetcher_serving(b""), now=NOW)

    assert result.reasons == ["no V3 parser probe for access method 'github' yet"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/parsers tests/sources/test_checks_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.parsers'`

- [ ] **Step 3: Feed 프로브 구현**

`apps/api/src/news_insight/parsers/__init__.py`: 빈 파일

`apps/api/src/news_insight/parsers/feed_probe.py`:

```python
"""V3 parser reliability probe for RSS/Atom feeds."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import feedparser

from news_insight.sources.ladder import CheckResult

MIN_PROBE_ITEMS = 3


@dataclass(frozen=True)
class ProbedItem:
    stable_id: str
    url: str
    title: str
    published_at: datetime


def extract_items(content: bytes) -> list[ProbedItem]:
    """Return entries that carry every field V3 requires: id, url, title, published date."""
    parsed = feedparser.parse(content)
    items: list[ProbedItem] = []
    for entry in parsed.entries:
        url = str(entry.get("link") or "").strip()
        stable_id = str(entry.get("id") or url).strip()
        title = str(entry.get("title") or "").strip()
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not (stable_id and url and title and published):
            continue
        items.append(
            ProbedItem(
                stable_id=stable_id,
                url=url,
                title=title,
                published_at=datetime(*published[:6], tzinfo=UTC),
            )
        )
    return items


def probe_feed(
    content: bytes,
    *,
    now: datetime,
    min_items: int = MIN_PROBE_ITEMS,
    max_age_days: int = 30,
) -> CheckResult:
    parsed = feedparser.parse(content)
    if not parsed.entries:
        detail = str(parsed.get("bozo_exception") or "no entries")
        return CheckResult.from_reasons(
            [f"feed could not be parsed: {detail}"], {"entries": 0, "complete": 0, "recent": 0}
        )
    items = extract_items(content)
    cutoff = now - timedelta(days=max_age_days)
    recent = [item for item in items if item.published_at >= cutoff]
    reasons: list[str] = []
    if len(recent) < min_items:
        reasons.append(f"only {len(recent)} recent complete items (need {min_items})")
    return CheckResult.from_reasons(
        reasons, {"entries": len(parsed.entries), "complete": len(items), "recent": len(recent)}
    )
```

- [ ] **Step 4: V3 검사 추가**

`apps/api/src/news_insight/sources/checks.py`의 import 블록 맨 위에 추가:

```python
from datetime import datetime
```

import 블록의 `news_insight.net.safe_fetch` 줄 아래에 추가:

```python
from news_insight.parsers.feed_probe import MIN_PROBE_ITEMS, probe_feed
```

파일 끝에 추가:

```python
def check_parser(source: Source, fetcher: SafeFetcher, *, now: datetime) -> CheckResult:
    """V3: at least three recent items with id, url, title and published date."""
    if source.access_method is not AccessMethod.FEED:
        return CheckResult.from_reasons(
            [f"no V3 parser probe for access method '{source.access_method.value}' yet"]
        )
    try:
        response = fetcher.fetch(probe_url(source), allowed_mime=FEED_MIME)
    except FetchError as exc:
        return CheckResult.from_reasons([str(exc)], {"error": exc.code})
    if response.status_code != 200:
        return CheckResult.from_reasons([f"unexpected HTTP status {response.status_code}"])
    min_items = max(MIN_PROBE_ITEMS, int(source.config.get("probe_min_items", MIN_PROBE_ITEMS)))
    max_age_days = int(source.config.get("probe_max_age_days", 30))
    return probe_feed(response.content, now=now, min_items=min_items, max_age_days=max_age_days)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/parsers tests/sources/test_checks_parser.py -v`
Expected: `10 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(parsers): add V3 feed reliability probe"
```

---

### Task 11: 포트폴리오 쿼터와 V6 게이트, 검증 서비스

**Files:**
- Create: `apps/api/src/news_insight/sources/portfolio.py`, `apps/api/src/news_insight/sources/service.py`
- Test: `apps/api/tests/sources/test_portfolio.py`, `apps/api/tests/sources/test_service.py`

**Interfaces:**
- Consumes: `check_identity`, `check_policy`, `check_network`, `check_parser`, `record_check`, `ensure_next_stage`, `next_stage`, `SafeFetcher`, `Source`, enum
- Produces:
  - `portfolio.py`: `TRACK_TARGETS: dict[Track, int]`, `TOTAL_TARGET: int = 260`, `REGION_FLOORS: dict[Region, float]`, `region_capacity(region: Region) -> int`, `@dataclass(frozen=True) PortfolioReport(track_counts: dict[Track, int], region_counts: dict[Region, int], total: int)` 및 메서드 `track_gap(track) -> int`, `region_share(region) -> float`, `region_shortfalls() -> dict[Region, float]`, `build_report(pairs: Iterable[tuple[Track, Region]]) -> PortfolioReport`, `active_portfolio(session: Session) -> list[tuple[Track, Region]]`, `check_quota(active: Sequence[tuple[Track, Region]], *, track: Track, region: Region) -> CheckResult`
  - `service.py`: `class SourceNotFound(LookupError)`, `class StageNotAutomated(LadderError)`, `AUTOMATED_STAGES: frozenset[ValidationStage]` (V0, V1, V2, V3, V6), `get_source(session, key) -> Source`, `run_check(session, source, stage, *, fetcher, now) -> SourceValidationEvent`, `climb(session, source, *, fetcher, now, until: ValidationStage = ValidationStage.V3) -> list[SourceValidationEvent]` (첫 실패에서 멈춤), `stage_counts(session) -> dict[ValidationStage, int]`
  - Phase 2에서는 V4·V5 러너가 `record_check`를 직접 호출하고, `AUTOMATED_STAGES`에 V4·V5를 추가함

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_portfolio.py`:

```python
import pytest
from sqlalchemy.orm import Session

from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.portfolio import (
    REGION_FLOORS,
    TOTAL_TARGET,
    TRACK_TARGETS,
    active_portfolio,
    build_report,
    check_quota,
    region_capacity,
)
from tests.factories import build_source


def test_targets_match_requirements() -> None:
    assert TRACK_TARGETS == {
        Track.NEWS: 100,
        Track.COMMUNITY: 100,
        Track.RESEARCH_IP: 35,
        Track.OSS: 25,
    }
    assert TOTAL_TARGET == 260
    assert sum(REGION_FLOORS.values()) == pytest.approx(1.0)


def test_region_capacities_partition_the_total() -> None:
    capacities = {region: region_capacity(region) for region in Region}

    assert capacities == {
        Region.KR: 65,
        Region.GLOBAL_EN: 117,
        Region.JP: 26,
        Region.GREATER_CHINA: 21,
        Region.EU_OTHER: 31,
    }
    assert sum(capacities.values()) == TOTAL_TARGET


def test_report_counts_shares_and_shortfalls() -> None:
    report = build_report([(Track.NEWS, Region.KR), (Track.NEWS, Region.GLOBAL_EN)] * 2)

    assert report.total == 4
    assert report.track_counts[Track.NEWS] == 4
    assert report.track_gap(Track.NEWS) == 96
    assert report.region_share(Region.KR) == 0.5
    shortfalls = report.region_shortfalls()
    assert Region.KR not in shortfalls
    assert shortfalls[Region.JP] == pytest.approx(0.10)


def test_empty_report_has_zero_shares() -> None:
    assert build_report([]).region_share(Region.KR) == 0.0


def test_quota_blocks_full_track() -> None:
    active = [(Track.OSS, Region.GLOBAL_EN)] * 25

    result = check_quota(active, track=Track.OSS, region=Region.GLOBAL_EN)

    assert result.reasons == ["track 'oss' is full (25/25)"]


def test_quota_blocks_region_at_capacity() -> None:
    active = [(Track.NEWS, Region.GREATER_CHINA)] * 21

    result = check_quota(active, track=Track.NEWS, region=Region.GREATER_CHINA)

    assert result.reasons == ["region 'greater_china' is at capacity (21/21)"]


def test_quota_passes_with_room() -> None:
    result = check_quota([], track=Track.NEWS, region=Region.KR)

    assert result.passed
    assert result.metrics == {"track_active": 0, "region_active": 0}


@pytest.mark.db
def test_active_portfolio_only_counts_active_v6(db_session: Session) -> None:
    db_session.add_all(
        [
            build_source(
                key="live",
                validation_stage=ValidationStage.V6,
                status=SourceStatus.ACTIVE,
                region=Region.KR,
                language="ko",
            ),
            build_source(key="pending", validation_stage=ValidationStage.V3),
            build_source(
                key="paused", validation_stage=ValidationStage.V6, status=SourceStatus.PAUSED
            ),
        ]
    )
    db_session.flush()

    assert active_portfolio(db_session) == [(Track.NEWS, Region.KR)]
```

`apps/api/tests/sources/test_service.py`:

```python
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import SourceStatus, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import LadderError
from news_insight.sources.service import (
    SourceNotFound,
    StageNotAutomated,
    climb,
    get_source,
    run_check,
    stage_counts,
)
from tests.factories import build_source
from tests.parsers.test_feed_probe import item, rss

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


@pytest.fixture
def feed_fetcher() -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            content=rss(item(1), item(2), item(3)),
        )

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )


def test_climb_runs_v0_to_v3_for_healthy_feed(
    db_session: Session, feed_fetcher: SafeFetcher
) -> None:
    source = build_source()
    db_session.add(source)
    db_session.flush()

    events = climb(db_session, source, fetcher=feed_fetcher, now=NOW)

    assert [event.stage for event in events] == [
        ValidationStage.V0,
        ValidationStage.V1,
        ValidationStage.V2,
        ValidationStage.V3,
    ]
    assert all(event.outcome is ValidationOutcome.PASSED for event in events)
    assert source.validation_stage is ValidationStage.V3


def test_climb_stops_at_first_failure(db_session: Session, feed_fetcher: SafeFetcher) -> None:
    source = build_source(terms_url=None)
    db_session.add(source)
    db_session.flush()

    events = climb(db_session, source, fetcher=feed_fetcher, now=NOW)

    assert [(e.stage, e.outcome) for e in events] == [
        (ValidationStage.V0, ValidationOutcome.PASSED),
        (ValidationStage.V1, ValidationOutcome.FAILED),
    ]
    assert source.validation_stage is ValidationStage.V0


def test_v4_and_v5_are_not_automated_yet(db_session: Session, feed_fetcher: SafeFetcher) -> None:
    source = build_source(validation_stage=ValidationStage.V3)
    db_session.add(source)
    db_session.flush()

    with pytest.raises(StageNotAutomated, match="V4"):
        run_check(db_session, source, ValidationStage.V4, fetcher=feed_fetcher, now=NOW)


def test_out_of_order_check_is_rejected_before_any_network_call(db_session: Session) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    fetcher = SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(explode)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )
    source = build_source()
    db_session.add(source)
    db_session.flush()

    with pytest.raises(LadderError):
        run_check(db_session, source, ValidationStage.V2, fetcher=fetcher, now=NOW)


def test_v6_gate_activates_source_with_quota_room(
    db_session: Session, feed_fetcher: SafeFetcher
) -> None:
    source = build_source(validation_stage=ValidationStage.V5)
    db_session.add(source)
    db_session.flush()

    event = run_check(db_session, source, ValidationStage.V6, fetcher=feed_fetcher, now=NOW)

    assert event.outcome is ValidationOutcome.PASSED
    assert source.status is SourceStatus.ACTIVE


def test_get_source_and_stage_counts(db_session: Session) -> None:
    db_session.add_all([build_source(key="a"), build_source(key="b", validation_stage=ValidationStage.V2)])
    db_session.flush()

    assert get_source(db_session, "a").key == "a"
    with pytest.raises(SourceNotFound):
        get_source(db_session, "missing")
    counts = stage_counts(db_session)
    assert counts[ValidationStage.UNVERIFIED] == 1
    assert counts[ValidationStage.V2] == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_portfolio.py tests/sources/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources.portfolio'`

- [ ] **Step 3: 포트폴리오 구현**

`apps/api/src/news_insight/sources/portfolio.py`:

```python
"""Active-source portfolio quotas: per-track targets and per-region capacity (roadmap D2)."""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source

TRACK_TARGETS: dict[Track, int] = {
    Track.NEWS: 100,
    Track.COMMUNITY: 100,
    Track.RESEARCH_IP: 35,
    Track.OSS: 25,
}
TOTAL_TARGET = sum(TRACK_TARGETS.values())
REGION_FLOORS: dict[Region, float] = {
    Region.KR: 0.25,
    Region.GLOBAL_EN: 0.45,
    Region.JP: 0.10,
    Region.GREATER_CHINA: 0.08,
    Region.EU_OTHER: 0.12,
}


def region_capacity(region: Region) -> int:
    return math.floor(REGION_FLOORS[region] * TOTAL_TARGET + 0.5)


@dataclass(frozen=True)
class PortfolioReport:
    track_counts: dict[Track, int]
    region_counts: dict[Region, int]
    total: int

    def track_gap(self, track: Track) -> int:
        return max(TRACK_TARGETS[track] - self.track_counts[track], 0)

    def region_share(self, region: Region) -> float:
        return self.region_counts[region] / self.total if self.total else 0.0

    def region_shortfalls(self) -> dict[Region, float]:
        return {
            region: round(floor - self.region_share(region), 4)
            for region, floor in REGION_FLOORS.items()
            if self.region_share(region) < floor
        }


def build_report(pairs: Iterable[tuple[Track, Region]]) -> PortfolioReport:
    items = list(pairs)
    tracks = Counter(track for track, _ in items)
    regions = Counter(region for _, region in items)
    return PortfolioReport(
        track_counts={track: tracks.get(track, 0) for track in Track},
        region_counts={region: regions.get(region, 0) for region in Region},
        total=len(items),
    )


def active_portfolio(session: Session) -> list[tuple[Track, Region]]:
    rows = session.execute(
        select(Source.track, Source.region).where(
            Source.status == SourceStatus.ACTIVE, Source.validation_stage == ValidationStage.V6
        )
    )
    return [(track, region) for track, region in rows]


def check_quota(
    active: Sequence[tuple[Track, Region]], *, track: Track, region: Region
) -> CheckResult:
    """V6 portfolio gate: refuse promotion into a full track or a region at capacity."""
    report = build_report(active)
    reasons: list[str] = []
    track_active = report.track_counts[track]
    region_active = report.region_counts[region]
    if track_active >= TRACK_TARGETS[track]:
        reasons.append(f"track '{track.value}' is full ({track_active}/{TRACK_TARGETS[track]})")
    if region_active >= region_capacity(region):
        reasons.append(
            f"region '{region.value}' is at capacity ({region_active}/{region_capacity(region)})"
        )
    return CheckResult.from_reasons(
        reasons, {"track_active": track_active, "region_active": region_active}
    )
```

- [ ] **Step 4: 검증 서비스 구현**

`apps/api/src/news_insight/sources/service.py`:

```python
"""Orchestrates ladder checks: picks the checker for a stage and records the outcome."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import (
    check_identity,
    check_network,
    check_parser,
    check_policy,
)
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import (
    CheckResult,
    LadderError,
    ensure_next_stage,
    next_stage,
    record_check,
)
from news_insight.sources.models import Source, SourceValidationEvent
from news_insight.sources.portfolio import active_portfolio, check_quota

AUTOMATED_STAGES = frozenset(
    {
        ValidationStage.V0,
        ValidationStage.V1,
        ValidationStage.V2,
        ValidationStage.V3,
        ValidationStage.V6,
    }
)


class SourceNotFound(LookupError):
    """No source with the requested key."""


class StageNotAutomated(LadderError):
    """The stage needs collection metrics that Phase 2 runners will provide."""


def get_source(session: Session, key: str) -> Source:
    source = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if source is None:
        raise SourceNotFound(f"unknown source '{key}'")
    return source


def _evaluate(
    session: Session, source: Source, stage: ValidationStage, fetcher: SafeFetcher, now: datetime
) -> CheckResult:
    if stage is ValidationStage.V0:
        return check_identity(source)
    if stage is ValidationStage.V1:
        return check_policy(source)
    if stage is ValidationStage.V2:
        return check_network(source, fetcher)
    if stage is ValidationStage.V3:
        return check_parser(source, fetcher, now=now)
    if stage is ValidationStage.V6:
        return check_quota(active_portfolio(session), track=source.track, region=source.region)
    raise StageNotAutomated(
        f"{stage.value} needs collection metrics from the Phase 2 canary/quality runners"
    )


def run_check(
    session: Session,
    source: Source,
    stage: ValidationStage,
    *,
    fetcher: SafeFetcher,
    now: datetime,
) -> SourceValidationEvent:
    ensure_next_stage(source, stage)
    if stage not in AUTOMATED_STAGES:
        raise StageNotAutomated(
            f"{stage.value} needs collection metrics from the Phase 2 canary/quality runners"
        )
    result = _evaluate(session, source, stage, fetcher, now)
    return record_check(session, source, stage, result)


def climb(
    session: Session,
    source: Source,
    *,
    fetcher: SafeFetcher,
    now: datetime,
    until: ValidationStage = ValidationStage.V3,
) -> list[SourceValidationEvent]:
    events: list[SourceValidationEvent] = []
    while (stage := next_stage(source.validation_stage)) is not None and STAGE_ORDER.index(
        stage
    ) <= STAGE_ORDER.index(until):
        event = run_check(session, source, stage, fetcher=fetcher, now=now)
        events.append(event)
        if event.outcome is ValidationOutcome.FAILED:
            break
    return events


def stage_counts(session: Session) -> dict[ValidationStage, int]:
    rows = session.execute(
        select(Source.validation_stage, func.count()).group_by(Source.validation_stage)
    )
    return {stage: count for stage, count in rows}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_portfolio.py tests/sources/test_service.py -v`
Expected: `14 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): add portfolio quotas, V6 gate and validation service"
```

---

### Task 12: 운영 CLI (`news-insight sources …`)

**Files:**
- Create: `apps/api/src/news_insight/cli.py`
- Modify: `README.md` (소스 거버넌스 절 추가)
- Test: `apps/api/tests/test_cli.py`

**Interfaces:**
- Consumes: `session_scope`, `get_settings`, `SafeFetcher.from_settings`, `load_catalog`, `seed_catalog`, `DEFAULT_CATALOG_PATH`, `get_source`, `climb`, `run_check`, `stage_counts`, `build_report`, `active_portfolio`, `TRACK_TARGETS`, `REGION_FLOORS`, `region_capacity`, `STAGE_ORDER`
- Produces: Typer `app` (콘솔 스크립트 `news-insight`)와 명령 `sources seed [--catalog PATH]`, `sources validate KEY [--until V0|V1|V2|V3]` (실패 시 종료 코드 1), `sources promote KEY` (V6 게이트, 실패 시 1, 순서 오류 시 2), `sources report`. 테스트에서 교체할 수 있도록 모듈 수준 이름 `session_scope`와 `_fetcher()`를 사용함

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/test_cli.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.net.safe_fetch import SafeFetcher
from tests.sources.test_catalog import ENTRY, write_catalog

pytestmark = pytest.mark.db
runner = CliRunner()


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("CLI tests must not reach the network")

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda: SafeFetcher(
            client=httpx.Client(transport=httpx.MockTransport(no_network)),
            resolver=lambda host, port: ["93.184.216.34"],
            verify_peer=False,
        ),
    )


def test_seed_reports_created_sources(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, ENTRY))])

    assert result.exit_code == 0, result.output
    assert "created=1 updated=0 reset=0" in result.output


def test_validate_stops_at_policy_failure_with_exit_code_1(tmp_path: Path) -> None:
    no_terms = ENTRY.replace("    terms_url: https://www.example.com/terms\n", "")
    runner.invoke(cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, no_terms))])

    result = runner.invoke(cli.app, ["sources", "validate", "example-news"])

    assert result.exit_code == 1
    assert "V0 passed: ok" in result.output
    assert "V1 failed: terms_url is missing" in result.output
    assert "example-news: stage=V0 status=candidate" in result.output


def test_validate_rejects_targets_beyond_v3() -> None:
    result = runner.invoke(cli.app, ["sources", "validate", "example-news", "--until", "V6"])

    assert result.exit_code == 2
    assert "use 'promote' for V6" in result.output


def test_validate_unknown_source_exits_2() -> None:
    result = runner.invoke(cli.app, ["sources", "validate", "nope"])

    assert result.exit_code == 2
    assert "unknown source 'nope'" in result.output


def test_promote_requires_v5(tmp_path: Path) -> None:
    runner.invoke(cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, ENTRY))])

    result = runner.invoke(cli.app, ["sources", "promote", "example-news"])

    assert result.exit_code == 2
    assert "next stage is V0, not V6" in result.output


def test_report_lists_tracks_regions_and_stages(tmp_path: Path) -> None:
    runner.invoke(cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, ENTRY))])

    result = runner.invoke(cli.app, ["sources", "report"])

    assert result.exit_code == 0, result.output
    assert "news" in result.output and "0/100" in result.output
    assert "greater_china" in result.output and "0/21" in result.output
    assert "unverified" in result.output
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'cli' from 'news_insight'`

- [ ] **Step 3: CLI 구현**

`apps/api/src/news_insight/cli.py`:

```python
"""Operator CLI: `news-insight sources seed|validate|promote|report`."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.catalog import DEFAULT_CATALOG_PATH, load_catalog, seed_catalog
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import LadderError
from news_insight.sources.portfolio import (
    REGION_FLOORS,
    TRACK_TARGETS,
    active_portfolio,
    build_report,
    region_capacity,
)
from news_insight.sources.service import (
    SourceNotFound,
    climb,
    get_source,
    run_check,
    stage_counts,
)

app = typer.Typer(help="Daily IT Intelligence operations CLI", no_args_is_help=True)
sources_app = typer.Typer(help="Source registry and V0-V6 validation ladder", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

CLIMBABLE = (ValidationStage.V0, ValidationStage.V1, ValidationStage.V2, ValidationStage.V3)


def _fetcher() -> SafeFetcher:
    return SafeFetcher.from_settings(get_settings())


def _fail(message: str, code: int = 2) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=code)


@sources_app.command("seed")
def seed(
    catalog: Annotated[Path, typer.Option(help="Catalog YAML path")] = DEFAULT_CATALOG_PATH,
) -> None:
    """Upsert catalog entries; identity changes reset validation."""
    with session_scope() as session:
        result = seed_catalog(session, load_catalog(catalog))
    typer.echo(
        f"created={len(result.created)} updated={len(result.updated)} reset={len(result.reset)}"
    )


@sources_app.command("validate")
def validate(
    key: str,
    until: Annotated[
        ValidationStage, typer.Option(help="Highest stage to attempt (V0-V3)")
    ] = ValidationStage.V3,
) -> None:
    """Climb the ladder from the current stage up to --until, stopping at the first failure."""
    if until not in CLIMBABLE:
        raise _fail("validate climbs V0-V3 only; use 'promote' for V6")
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            events = climb(session, source, fetcher=fetcher, now=datetime.now(UTC), until=until)
            lines = [
                f"{event.stage.value} {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
                for event in events
            ]
            summary = (
                f"{source.key}: stage={source.validation_stage.value} status={source.status.value}"
            )
            failed = any(event.outcome is ValidationOutcome.FAILED for event in events)
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    for line in lines:
        typer.echo(line)
    typer.echo(summary)
    if failed:
        raise typer.Exit(code=1)


@sources_app.command("promote")
def promote(key: str) -> None:
    """Run the V6 portfolio gate for a source that has passed V5."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            event = run_check(
                session, source, ValidationStage.V6, fetcher=fetcher, now=datetime.now(UTC)
            )
            line = f"V6 {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
            passed = event.outcome is ValidationOutcome.PASSED
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)
    if not passed:
        raise typer.Exit(code=1)


@sources_app.command("report")
def report() -> None:
    """Show active sources against track targets, region capacity and stage distribution."""
    with session_scope() as session:
        portfolio = build_report(active_portfolio(session))
        stages = stage_counts(session)
    typer.echo("Tracks (active/target)")
    for track, target in TRACK_TARGETS.items():
        typer.echo(f"  {track.value:<14} {portfolio.track_counts[track]:>3}/{target}")
    typer.echo("Regions (active/capacity, share vs floor)")
    for region, floor in REGION_FLOORS.items():
        typer.echo(
            f"  {region.value:<14} {portfolio.region_counts[region]:>3}/{region_capacity(region):<4}"
            f"{portfolio.region_share(region):6.1%} (floor {floor:.0%})"
        )
    typer.echo("Validation stages")
    for stage in STAGE_ORDER:
        typer.echo(f"  {stage.value:<14} {stages.get(stage, 0)}")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/test_cli.py -v`
Expected: `6 passed`

- [ ] **Step 5: README에 소스 거버넌스 절 추가**

`README.md` 끝에 추가:

````markdown
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
````

- [ ] **Step 6: 전체 검증 후 Commit**

Run: `make verify`
Expected: ruff, mypy, pytest 전체 통과 (`109 passed`), `No new upgrade operations detected.`, 웹 테스트 1개 통과, `next build` 성공, compose config 오류 없음

```bash
git add apps/api README.md
git commit -m "feat(cli): add source seed/validate/promote/report commands"
```

---

## Phase 1 완료 검증 (M1)

모든 태스크가 끝난 뒤 아래 순서로 시연하고 결과를 기록합니다.

1. `make verify` — 전 항목 통과
2. `docker compose up -d --build` 후 `until curl -skf https://localhost/api/health; do sleep 3; done` → `{"status":"ok","version":"0.1.0"}`
3. 개발 DB에서 실제 카탈로그 검증:
   ```bash
   cd apps/api
   uv run alembic upgrade head
   uv run news-insight sources seed
   uv run news-insight sources validate hacker-news
   uv run news-insight sources report
   ```
   Expected: `V0 passed`, 이어서 `V1 failed: terms_url is missing`가 나오면 정상입니다 (약관 검토 전이므로 의도된 차단). 운영자가 `catalog/sources.yaml`에 `terms_url`을 채우고 다시 `seed`·`validate`를 실행하면 V2(실제 HTTPS·피어 검증)와 V3(실제 Feed 파싱)까지 통과해야 합니다.
4. `docker compose down`

## Self-Review 결과

- **요구사항 대비 범위:** §3 V0·V1·V2·V3·V6 → Task 8·9·10·11, 승격 순서 → Task 6. §2 트랙·지역 쿼터 → Task 11 (해석은 로드맵 D2). §10 Compose 7개 서비스 → Task 3·4. V4·V5는 수집 지표가 필요하므로 Phase 2로 명시적 이관 (`StageNotAutomated`). §4~§9는 로드맵 P2~P8에서 다룹니다.
- **누락 표시 점검:** 미완성 표시나 "Task N과 동일" 같은 참조 없이, 모든 코드 단계에 전체 코드를 포함했습니다.
- **이름 일관성:** `CheckResult.from_reasons`, `ensure_next_stage`, `record_check`, `probe_url`, `FEED_MIME`, `EXPECTED_MIME`, `MIN_PROBE_ITEMS`, `check_quota(active, *, track, region)`, `climb(..., until=)`가 정의한 곳과 사용하는 곳에서 같은 시그니처로 쓰이는 것을 확인했습니다.
- **테스트 수 누계 (Python):** Task 1: 3 → Task 3: 5 → Task 4: 11 → Task 5: 16 → Task 6: 26 → Task 7: 35 → Task 8: 48 → Task 9: 79 → Task 10: 89 → Task 11: 103 → Task 12: 109. 각 단계의 Expected 수치와 다르면 누락되었거나 중복 수집된 테스트 파일이 있는지 먼저 확인합니다.
