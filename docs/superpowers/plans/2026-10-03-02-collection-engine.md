# Phase 2 — Collection Engine & Adaptive Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use dev_sp_subagent-driven-development (recommended) or dev_sp_executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** V3 이상 소스를 적응형 주기로 실제 수집합니다. Seen Ledger로 변경된 내용만 저장하고, 실패는 백오프·Dead Letter·자동 일시정지로 격리합니다. 24시간 Canary 지표로 V4를 자동 판정합니다.

**Architecture:** Celery Beat가 1분마다 `collect.dispatch_due`를 실행합니다. 이 디스패처는 `source_runtimes.next_due_at`이 지난 소스를 임대(lease)로 확보해서 `collect.source` 작업으로 넘깁니다. 작업은 Redis 소스 락과 도메인별 토큰 버킷을 통과한 뒤 접근 방식별 Collector(Feed / JSON API / 선언형 크롤러, 모두 Phase 1의 `SafeFetcher` 사용)를 호출합니다. 수집 결과는 `ingest_items`(Seen Ledger)가 저장하고, `collect_source`가 결과에 따라 다음 주기·재시도·DLQ·일시정지를 결정합니다. 모든 시도는 `fetch_runs`에 남으며, V4 Canary 러너가 이 기록을 집계합니다.

**Tech Stack:** Phase 1 스택 + selectolax 0.4 (HTML 파싱), redis-py 6 (토큰 버킷·락, Lua 스크립트), Celery Beat 스케줄

## Global Constraints

- 적응형 주기 범위 (요구사항 §4): 속보 5~15분, 뉴스 15~60분, 커뮤니티 10~30분, 논문 2시간 고정, 특허/OSS 6~24시간. 304 또는 신규·변경 0건이면 ×1.5 연장, 신규 5건 이상이면 최소 주기로 복귀, 신규 1~4건이면 ÷1.5 단축
- 일시 오류(타임아웃, 전송 오류, 429, 5xx)는 지수 백오프 60초·120초·240초로 **최대 3회 재시도**한 뒤 Dead Letter로 격리
- `selector_drift`(필수 필드가 절반 넘게 빠짐, 크롤러 목록 선택자 0건, JSON 목록 경로 소실)와 `blocked_*`(SafeFetcher 보안 정책 차단)는 재시도 없이 Dead Letter로 보내고 소스를 `paused`로 전환
- Seen Ledger: `(source_id, stable_id)`로 조회해 `content_hash`가 같으면 **아무것도 쓰지 않음**. 해시는 정규화된 제목·요약·본문(저장하지 않는 본문 포함)의 SHA-256
- 원문 저장 정책 (D9): `metadata_only` 제목·URL·발행일·저자 / `excerpt_allowed` 요약 최대 500자 / `fulltext_ttl` 전문 저장 후 30일 뒤 본문 삭제 / `fulltext_permitted` 전문 영구
- 수집 대상: `candidate` 상태의 V3~V5 소스(Canary 모드, 저장 항목에 `canary=true`)와 `active` 상태의 V6 소스. `paused`·`retired`·V2 이하는 수집하지 않음
- 이번 Phase의 Collector는 `feed`, `json_api`, `crawler`만 지원. `github`, `atproto`, `activitypub`, `research_api`는 Phase 3
- 모든 HTTP 요청은 `SafeFetcher`를 거침 (15초, 리다이렉트 3회, 5MB, HTTPS 443, 사설 IP 차단)
- 도메인별 요청 예산 기본 분당 30회 (`Settings.domain_rate_per_minute`), 소스 `config.rate_per_minute`로 낮출 수 있음. 예산 초과 시 60초 뒤 재시도
- V5·V6 자동 승격은 이번 Phase 범위가 아님 (D8, P5에서 구현). LLM 호출 없음
- Redis 논리 DB: 애플리케이션 0번, 테스트 15번. 새 호스트 포트 없음 (`docs/PORTS.md`)
- Python 코드는 `ruff check`, `ruff format --check`, `mypy --strict` 통과. 검증 명령은 `scripts/dev.sh verify`

---

## File Structure

```
apps/api/src/news_insight/
├── db.py                         # (수정) str_enum 헬퍼 추가
├── config.py                     # (수정) domain_rate_per_minute
├── content/
│   ├── normalize.py              # canonical_url, html_to_text, clean_text, stable_key, content_hash
│   ├── policy.py                 # 저장 등급별 저장 범위 (D9)
│   ├── models.py                 # Item, ItemRevision
│   ├── ingest.py                 # Seen Ledger 수집 결과 반영
│   └── retention.py              # fulltext_ttl 본문 삭제
├── collect/
│   ├── contracts.py              # RawItem, CollectContext, CollectResult, CollectorError, Collector
│   ├── macros.py                 # {today}, {today-30d} 날짜 매크로
│   ├── http.py                   # SafeFetcher 결과 → CollectorError, 조건부 요청 헤더
│   ├── fields.py                 # dotted_get, parse_datetime, text_or_none
│   ├── feed.py                   # RSS/Atom Collector
│   ├── json_api.py               # 선언형 매핑 JSON Collector
│   ├── crawler.py                # 선언형 HTML 목록 크롤러
│   ├── registry.py               # 접근 방식 → Collector
│   ├── models.py                 # SourceRuntime, FetchRun, DeadLetter
│   ├── service.py                # collect_source (수집 1회의 전체 흐름)
│   ├── dispatch.py               # 기한이 된 소스 임대·확보
│   └── dead_letters.py           # DLQ 조회·재시도·종결
├── scheduling/
│   ├── policy.py                 # 적응형 주기·재시도 지연
│   └── redis_guards.py           # DomainRateLimiter, SourceLock, get_redis
├── sources/canary.py             # V4 Canary 지표·판정·러너
├── jobs/celery_app.py            # (수정) include, beat_schedule
├── jobs/tasks.py                 # Celery 진입점 (얇게 유지)
├── parsers/feed_probe.py         # (수정) struct_to_datetime 공용화
└── cli.py                        # (수정) collect / dlq / sources canary·pause·resume
apps/api/migrations/versions/0003_collection_runtime.py, 0004_items.py
apps/api/tests/helpers.py         # 테스트용 SafeFetcher 팩토리
```

**책임 경계:** `content/normalize.py`, `content/policy.py`, `collect/*` Collector, `scheduling/policy.py`는 DB를 모르는 순수 로직입니다. DB 상태를 바꾸는 곳은 `content/ingest.py`(항목), `collect/service.py`(런타임·실행 기록·DLQ·일시정지), `collect/dispatch.py`(임대), `sources/canary.py`(V4 이벤트), `content/retention.py`, `collect/dead_letters.py`입니다. `jobs/tasks.py`는 세션·락·Fetcher를 엮어서 서비스 함수를 호출하는 역할만 합니다.

---

### Task 1: 콘텐츠 정규화와 저장 정책

**Files:**
- Modify: `apps/api/pyproject.toml` (selectolax 의존성, mypy override)
- Create: `apps/api/src/news_insight/content/__init__.py`, `apps/api/src/news_insight/content/normalize.py`, `apps/api/src/news_insight/content/policy.py`
- Test: `apps/api/tests/content/__init__.py`, `apps/api/tests/content/test_normalize.py`, `apps/api/tests/content/test_policy.py`

**Interfaces:**
- Consumes: `StorageRight` (Phase 1)
- Produces: `canonical_url(url: str) -> str`, `html_to_text(value: str | None) -> str`, `truncate(text: str, limit: int) -> str`, `clean_text(value: str | None, *, limit: int | None = None) -> str | None`, `stable_key(stable_id: str) -> str` (500자 초과 시 `sha256:<hex>`), `content_hash(*parts: str | None) -> str`; `EXCERPT_MAX_CHARS = 500`, `FULLTEXT_TTL = timedelta(days=30)`, `StoredContent(summary, body, body_expires_at)`, `apply_storage_right(right, *, summary, body, now) -> StoredContent`

- [ ] **Step 1: 의존성 추가**

Run: `cd apps/api && uv add "selectolax>=0.4.13,<0.5"`
Expected: `pyproject.toml` dependencies에 `selectolax`가 추가되고 `uv.lock` 갱신

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/api/tests/content/__init__.py`: 빈 파일

`apps/api/tests/content/test_normalize.py`:

```python
from news_insight.content.normalize import (
    canonical_url,
    clean_text,
    content_hash,
    html_to_text,
    stable_key,
    truncate,
)


def test_canonical_url_strips_tracking_and_fragment() -> None:
    url = "HTTPS://Example.COM:443/news/a/?utm_source=x&b=2&fbclid=z&a=1#comments"

    assert canonical_url(url) == "https://example.com/news/a?a=1&b=2"


def test_canonical_url_keeps_root_and_non_default_port() -> None:
    assert canonical_url("https://example.com") == "https://example.com/"
    assert canonical_url("http://example.com:80/x") == "http://example.com/x"
    assert canonical_url("https://example.com:8443/x") == "https://example.com:8443/x"


def test_html_to_text_drops_markup_scripts_and_entities() -> None:
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p><script>track()</script>") == "Hello world"
    assert html_to_text("AT&amp;T  ships\n6G") == "AT&T ships 6G"
    assert html_to_text(None) == ""


def test_content_hash_ignores_markup_and_whitespace() -> None:
    assert content_hash("<p>Galaxy  S30</p>", None) == content_hash("Galaxy S30", "")


def test_content_hash_changes_with_text() -> None:
    assert content_hash("Galaxy S30", "128GB") != content_hash("Galaxy S30", "256GB")


def test_stable_key_hashes_overlong_ids() -> None:
    assert stable_key(" id-1 ") == "id-1"
    hashed = stable_key("x" * 600)
    assert hashed.startswith("sha256:")
    assert len(hashed) == 71


def test_truncate_and_clean_text() -> None:
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 4) == "abc"
    assert clean_text("<p> </p>") is None
    assert clean_text("<b>Long title</b>", limit=6) == "Long…"
```

`apps/api/tests/content/test_policy.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from news_insight.content.policy import EXCERPT_MAX_CHARS, FULLTEXT_TTL, apply_storage_right
from news_insight.sources.enums import StorageRight

NOW = datetime(2026, 10, 3, tzinfo=UTC)
LONG = "가" * 800


@pytest.mark.parametrize("right", [None, StorageRight.METADATA_ONLY])
def test_metadata_only_keeps_no_text(right: StorageRight | None) -> None:
    stored = apply_storage_right(right, summary="s", body="b", now=NOW)

    assert (stored.summary, stored.body, stored.body_expires_at) == (None, None, None)


def test_excerpt_is_capped_at_500_chars() -> None:
    stored = apply_storage_right(StorageRight.EXCERPT_ALLOWED, summary=LONG, body="full", now=NOW)

    assert stored.summary is not None
    assert len(stored.summary) == EXCERPT_MAX_CHARS
    assert stored.body is None


def test_excerpt_falls_back_to_body() -> None:
    stored = apply_storage_right(
        StorageRight.EXCERPT_ALLOWED, summary=None, body="body text", now=NOW
    )

    assert stored.summary == "body text"


def test_fulltext_ttl_expires_after_30_days() -> None:
    stored = apply_storage_right(StorageRight.FULLTEXT_TTL, summary="s", body="full text", now=NOW)

    assert stored.body == "full text"
    assert stored.body_expires_at == NOW + FULLTEXT_TTL == NOW + timedelta(days=30)


def test_fulltext_permitted_keeps_body_without_expiry() -> None:
    stored = apply_storage_right(
        StorageRight.FULLTEXT_PERMITTED, summary=None, body="full", now=NOW
    )

    assert (stored.body, stored.body_expires_at) == ("full", None)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/content -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.content'`

- [ ] **Step 4: 구현**

`apps/api/src/news_insight/content/__init__.py`: 빈 파일

`apps/api/src/news_insight/content/normalize.py`:

```python
"""Text and URL normalization shared by the seen ledger and later phases."""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
        "cmpid",
        "spm",
    }
)
TRACKING_PREFIXES = ("utm_",)
DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_STABLE_ID = 500
_WHITESPACE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    """Lower-case scheme/host, drop default port, fragment and tracking params, sort query."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None or DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS and not key.lower().startswith(TRACKING_PREFIXES)
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def html_to_text(value: str | None) -> str:
    """Strip markup, scripts and entities, then collapse whitespace."""
    if not value:
        return ""
    if "<" in value or "&" in value:
        tree = HTMLParser(value)
        tree.strip_tags(["script", "style", "noscript"])
        value = tree.body.text(separator=" ") if tree.body is not None else ""
    return _WHITESPACE.sub(" ", value).strip()


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_text(value: str | None, *, limit: int | None = None) -> str | None:
    text = html_to_text(value)
    if not text:
        return None
    return truncate(text, limit) if limit is not None else text


def stable_key(stable_id: str) -> str:
    """Keep ids within the column limit; overlong ids become a deterministic digest."""
    stable_id = stable_id.strip()
    if len(stable_id) <= MAX_STABLE_ID:
        return stable_id
    return "sha256:" + hashlib.sha256(stable_id.encode("utf-8")).hexdigest()


def content_hash(*parts: str | None) -> str:
    """SHA-256 over normalized text, so markup or whitespace churn is not a change."""
    joined = "\x1f".join(html_to_text(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
```

`apps/api/src/news_insight/content/policy.py`:

```python
"""Storage-right policy (roadmap D9): what an item may keep, and for how long."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from news_insight.content.normalize import truncate
from news_insight.sources.enums import StorageRight

EXCERPT_MAX_CHARS = 500
FULLTEXT_TTL = timedelta(days=30)


@dataclass(frozen=True)
class StoredContent:
    summary: str | None
    body: str | None
    body_expires_at: datetime | None


def apply_storage_right(
    right: StorageRight | None, *, summary: str | None, body: str | None, now: datetime
) -> StoredContent:
    """`summary` and `body` must already be plain text."""
    if right is None or right is StorageRight.METADATA_ONLY:
        return StoredContent(summary=None, body=None, body_expires_at=None)
    excerpt_source = summary or body
    excerpt = truncate(excerpt_source, EXCERPT_MAX_CHARS) if excerpt_source else None
    if right is StorageRight.EXCERPT_ALLOWED:
        return StoredContent(summary=excerpt, body=None, body_expires_at=None)
    if right is StorageRight.FULLTEXT_TTL:
        expires = now + FULLTEXT_TTL if body else None
        return StoredContent(summary=excerpt, body=body, body_expires_at=expires)
    return StoredContent(summary=excerpt, body=body, body_expires_at=None)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/content -v`
Expected: `13 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(content): add URL/text normalization, content hash and storage policy"
```

---

### Task 2: 수집 계약 · 날짜 매크로 · HTTP 오류 매핑

**Files:**
- Create: `apps/api/src/news_insight/collect/__init__.py`, `collect/contracts.py`, `collect/macros.py`, `collect/http.py`
- Test: `apps/api/tests/helpers.py`, `apps/api/tests/collect/__init__.py`, `tests/collect/test_contracts.py`, `tests/collect/test_macros.py`, `tests/collect/test_http.py`

**Interfaces:**
- Consumes: `SafeFetcher`, `FetchResponse`, `FetchBlocked`, `FetchFailed` (Phase 1)
- Produces:
  - `RawItem(stable_id, url, title, published_at=None, author=None, summary=None, body=None)`
  - `CollectContext(endpoint_url, config, now, etag=None, last_modified=None, last_success_at=None)`와 `.item_limit` (기본 50, 1~200 범위로 제한)
  - `CollectResult(items, status_code, elapsed_ms, etag=None, last_modified=None, not_modified=False, incomplete=0)`
  - `CollectorError(code, message, *, retryable, status_code=None)`, `Collector` Protocol (`collect(context) -> CollectResult`), `majority_incomplete(incomplete, examined) -> bool`
  - `expand_macros(template, *, now) -> str` (KST 기준 날짜)
  - `conditional_headers(context) -> dict[str, str]`, `fetch_checked(fetcher, url, *, allowed_mime, headers=None) -> FetchResponse` (200/304만 반환, 429·5xx·타임아웃·전송 오류는 retryable, 그 외 4xx와 `blocked_<code>`는 final)
  - `tests/helpers.py`: `mock_fetcher(handler) -> SafeFetcher`, `serving(content, *, status=200, content_type="application/rss+xml", headers=None, seen=None) -> SafeFetcher`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/helpers.py`:

```python
from collections.abc import Callable

import httpx

from news_insight.net.safe_fetch import SafeFetcher

PUBLIC_IP = "93.184.216.34"


def mock_fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> SafeFetcher:
    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: [PUBLIC_IP],
        verify_peer=False,
    )


def serving(
    content: bytes,
    *,
    status: int = 200,
    content_type: str = "application/rss+xml",
    headers: dict[str, str] | None = None,
    seen: list[httpx.Request] | None = None,
) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(
            status, headers={"content-type": content_type, **(headers or {})}, content=content
        )

    return mock_fetcher(handler)
```

`apps/api/tests/collect/__init__.py`: 빈 파일

`apps/api/tests/collect/test_contracts.py`:

```python
from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext, majority_incomplete

NOW = datetime(2026, 10, 3, tzinfo=UTC)


@pytest.mark.parametrize(
    ("configured", "expected"), [(None, 50), (500, 200), (0, 1), ("many", 50)]
)
def test_item_limit_is_clamped(configured: Any, expected: int) -> None:
    config = {} if configured is None else {"item_limit": configured}
    context = CollectContext(endpoint_url="https://example.com/feed", config=config, now=NOW)

    assert context.item_limit == expected


def test_majority_incomplete_needs_more_than_half() -> None:
    assert majority_incomplete(2, 3) is True
    assert majority_incomplete(1, 2) is False
    assert majority_incomplete(0, 0) is False
```

`apps/api/tests/collect/test_macros.py`:

```python
from datetime import UTC, datetime

from news_insight.collect.macros import expand_macros

NOW = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)


def test_today_offsets_use_kst_dates() -> None:
    template = "pushed:>{today-30d} created:>{today-180d} on {today}"

    assert expand_macros(template, now=NOW) == (
        "pushed:>2026-09-03 created:>2026-04-06 on 2026-10-03"
    )


def test_kst_day_boundary() -> None:
    assert expand_macros("{today}", now=datetime(2026, 10, 2, 16, 0, tzinfo=UTC)) == "2026-10-03"


def test_other_braces_are_untouched() -> None:
    assert expand_macros("{yesterday} {today-x}", now=NOW) == "{yesterday} {today-x}"
```

`apps/api/tests/collect/test_http.py`:

```python
from datetime import UTC, datetime

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.http import conditional_headers, fetch_checked
from tests.helpers import mock_fetcher, serving

URL = "https://www.example.com/feed.xml"
MIME = frozenset({"application/rss+xml"})


@pytest.mark.parametrize("status", [200, 304])
def test_success_statuses_are_returned(status: int) -> None:
    response = fetch_checked(serving(b"<rss/>", status=status), URL, allowed_mime=MIME)

    assert response.status_code == status


@pytest.mark.parametrize(("status", "code"), [(429, "rate_limited"), (503, "server_error")])
def test_transient_statuses_are_retryable(status: int, code: str) -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b"", status=status), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable, error.value.status_code) == (
        code,
        True,
        status,
    )


def test_client_errors_are_final() -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b"", status=404), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("http_404", False)


def test_timeouts_are_retryable() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(CollectorError) as error:
        fetch_checked(mock_fetcher(slow), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("timeout", True)


def test_blocked_targets_are_final() -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b""), "http://www.example.com/feed.xml", allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("blocked_scheme", False)


def test_conditional_headers_follow_context() -> None:
    context = CollectContext(
        endpoint_url=URL,
        config={},
        now=datetime(2026, 10, 3, tzinfo=UTC),
        etag='"v1"',
        last_modified="Thu, 01 Oct 2026 09:00:00 GMT",
    )

    assert conditional_headers(context) == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Thu, 01 Oct 2026 09:00:00 GMT",
    }
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/collect/__init__.py`: 빈 파일

`apps/api/src/news_insight/collect/contracts.py`:

```python
"""Collector contract shared by every access-method adapter."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

DEFAULT_ITEM_LIMIT = 50
MAX_ITEM_LIMIT = 200


@dataclass(frozen=True)
class RawItem:
    stable_id: str
    url: str
    title: str
    published_at: datetime | None = None
    author: str | None = None
    summary: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class CollectContext:
    endpoint_url: str
    config: dict[str, Any]
    now: datetime
    etag: str | None = None
    last_modified: str | None = None
    last_success_at: datetime | None = None

    @property
    def item_limit(self) -> int:
        try:
            value = int(self.config.get("item_limit", DEFAULT_ITEM_LIMIT))
        except (TypeError, ValueError):
            value = DEFAULT_ITEM_LIMIT
        return max(1, min(value, MAX_ITEM_LIMIT))


@dataclass(frozen=True)
class CollectResult:
    items: list[RawItem]
    status_code: int
    elapsed_ms: int
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    incomplete: int = 0


class CollectorError(Exception):
    """A collection attempt failed; `retryable` chooses backoff over dead letter."""

    def __init__(
        self, code: str, message: str, *, retryable: bool, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


class Collector(Protocol):
    def collect(self, context: CollectContext) -> CollectResult: ...


def majority_incomplete(incomplete: int, examined: int) -> bool:
    """Drift signal: more than half of the examined records lost a required field."""
    return examined > 0 and incomplete * 2 > examined
```

`apps/api/src/news_insight/collect/macros.py`:

```python
"""Date macros in endpoint URLs and queries: {today}, {today-30d}, {today-180d} (KST dates)."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MACRO = re.compile(r"\{today(?:-(\d{1,4})d)?\}")
KST = ZoneInfo("Asia/Seoul")


def expand_macros(template: str, *, now: datetime) -> str:
    today = now.astimezone(KST).date()

    def replace(match: re.Match[str]) -> str:
        return (today - timedelta(days=int(match.group(1) or 0))).isoformat()

    return MACRO.sub(replace, template)
```

`apps/api/src/news_insight/collect/http.py`:

```python
"""Map SafeFetcher outcomes onto collector errors, and build conditional-request headers."""

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.net.safe_fetch import FetchBlocked, FetchFailed, FetchResponse, SafeFetcher


def conditional_headers(context: CollectContext) -> dict[str, str]:
    headers: dict[str, str] = {}
    if context.etag:
        headers["If-None-Match"] = context.etag
    if context.last_modified:
        headers["If-Modified-Since"] = context.last_modified
    return headers


def fetch_checked(
    fetcher: SafeFetcher,
    url: str,
    *,
    allowed_mime: frozenset[str],
    headers: dict[str, str] | None = None,
) -> FetchResponse:
    """Return 200/304 responses; raise CollectorError for everything else."""
    try:
        response = fetcher.fetch(url, allowed_mime=allowed_mime, headers=headers)
    except FetchFailed as exc:
        raise CollectorError(exc.code, str(exc), retryable=True) from exc
    except FetchBlocked as exc:
        raise CollectorError(f"blocked_{exc.code}", str(exc), retryable=False) from exc
    status = response.status_code
    if status in (200, 304):
        return response
    message = f"HTTP {status} from {url}"
    if status == 429:
        raise CollectorError("rate_limited", message, retryable=True, status_code=status)
    if status >= 500:
        raise CollectorError("server_error", message, retryable=True, status_code=status)
    raise CollectorError(f"http_{status}", message, retryable=False, status_code=status)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect -v`
Expected: `16 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add collector contract, date macros and HTTP error mapping"
```

---

### Task 3: 수집 런타임 스키마 (runtime · fetch run · dead letter)

**Files:**
- Modify: `apps/api/src/news_insight/db.py` (`str_enum` 추가), `apps/api/src/news_insight/sources/models.py` (`_enum` → `str_enum`), `apps/api/src/news_insight/model_registry.py`
- Create: `apps/api/src/news_insight/collect/models.py`, `apps/api/migrations/versions/0003_collection_runtime.py`
- Test: `apps/api/tests/collect/test_runtime_models.py`

**Interfaces:**
- Consumes: `Base`, `Source`
- Produces: `db.str_enum(enum_cls) -> sqlalchemy.Enum`; `FetchOutcome` (`SUCCESS`, `NOT_MODIFIED`, `FAILED`, `DEAD_LETTERED`, `SKIPPED`); `SourceRuntime` (`source_id` PK, `next_due_at`, `interval_seconds`, `consecutive_failures`, `consecutive_idle`, `etag`, `last_modified`, `last_attempt_at`, `last_success_at`, `lease_until`); `FetchRun` (`id, source_id, started_at, finished_at, outcome, attempt, canary, http_status, elapsed_ms, items_seen, items_new, items_updated, items_unchanged, items_incomplete, duplicate_urls, error_code, error_message`); `DeadLetter` (`id, source_id, fetch_run_id, error_code, error_message, attempts, created_at, resolved_at, resolution`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_runtime_models.py`:

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def persisted_source(session: Session) -> Source:
    source = build_source()
    session.add(source)
    session.flush()
    return source


def test_runtime_defaults(db_session: Session) -> None:
    source = persisted_source(db_session)
    runtime = SourceRuntime(source_id=source.id, next_due_at=NOW, interval_seconds=900)
    db_session.add(runtime)
    db_session.flush()
    db_session.refresh(runtime)

    assert (runtime.consecutive_failures, runtime.consecutive_idle) == (0, 0)
    assert (runtime.etag, runtime.lease_until) == (None, None)


def test_fetch_run_stores_plain_outcome_value(db_session: Session) -> None:
    source = persisted_source(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.NOT_MODIFIED)
    db_session.add(run)
    db_session.flush()

    row = db_session.execute(
        text("SELECT outcome, attempt, canary, items_new FROM fetch_runs WHERE id = :id"),
        {"id": run.id},
    ).one()

    assert tuple(row) == ("not_modified", 1, False, 0)


def test_dead_letters_start_unresolved(db_session: Session) -> None:
    source = persisted_source(db_session)
    letter = DeadLetter(
        source_id=source.id, error_code="timeout", error_message="timed out", attempts=4
    )
    db_session.add(letter)
    db_session.flush()
    db_session.refresh(letter)

    assert letter.resolved_at is None
    assert letter.created_at is not None


def test_deleting_a_source_cascades_runtime_state(db_session: Session) -> None:
    source = persisted_source(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.FAILED)
    db_session.add_all(
        [SourceRuntime(source_id=source.id, next_due_at=NOW, interval_seconds=900), run]
    )
    db_session.flush()
    db_session.add(
        DeadLetter(
            source_id=source.id, fetch_run_id=run.id, error_code="x", error_message="x", attempts=1
        )
    )
    db_session.flush()

    db_session.execute(delete(Source).where(Source.id == source.id))

    for model in (SourceRuntime, FetchRun, DeadLetter):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_runtime_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.models'`

- [ ] **Step 3: `str_enum` 공용화**

`apps/api/src/news_insight/db.py`의 import 블록을 다음으로 교체:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from news_insight.config import get_settings
```

`class Base` 정의 바로 아래에 추가:

```python
def str_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """Store a StrEnum as its plain value in VARCHAR(32) (no native PG enum)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
```

`apps/api/src/news_insight/sources/models.py`에서 `_enum` 함수 정의와 그 함수만 쓰던 import(`from enum import StrEnum`, `from sqlalchemy import Enum as SAEnum`)를 지우고, `from news_insight.db import Base`를 `from news_insight.db import Base, str_enum`으로 바꾼 다음 아래 명령으로 호출부를 교체:

Run: `cd apps/api && sed -i '' 's/_enum(/str_enum(/g' src/news_insight/sources/models.py && grep -c "str_enum(" src/news_insight/sources/models.py`
Expected: `9` (enum 컬럼 9개: Source 7 + SourceValidationEvent 2). `def _enum`이 남아 있지 않은지도 확인

- [ ] **Step 4: 모델과 마이그레이션 구현**

`apps/api/src/news_insight/collect/models.py`:

```python
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class FetchOutcome(StrEnum):
    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"  # will be retried with backoff
    DEAD_LETTERED = "dead_lettered"
    SKIPPED = "skipped"  # not attempted: local rate budget or not collectable


class SourceRuntime(Base):
    """Mutable scheduling state, kept apart from the governed source registry."""

    __tablename__ = "source_runtimes"

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval_seconds: Mapped[int]
    consecutive_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    consecutive_idle: Mapped[int] = mapped_column(default=0, server_default="0")
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FetchRun(Base):
    """One collection attempt; the V4 canary aggregates these."""

    __tablename__ = "fetch_runs"
    __table_args__ = (Index("ix_fetch_runs_source_started", "source_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[FetchOutcome] = mapped_column(str_enum(FetchOutcome))
    attempt: Mapped[int] = mapped_column(default=1, server_default="1")
    canary: Mapped[bool] = mapped_column(default=False, server_default=false())
    http_status: Mapped[int | None]
    elapsed_ms: Mapped[int | None]
    items_seen: Mapped[int] = mapped_column(default=0, server_default="0")
    items_new: Mapped[int] = mapped_column(default=0, server_default="0")
    items_updated: Mapped[int] = mapped_column(default=0, server_default="0")
    items_unchanged: Mapped[int] = mapped_column(default=0, server_default="0")
    items_incomplete: Mapped[int] = mapped_column(default=0, server_default="0")
    duplicate_urls: Mapped[int] = mapped_column(default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    fetch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL")
    )
    error_code: Mapped[str] = mapped_column(String(80))
    error_message: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(20))
```

`apps/api/src/news_insight/model_registry.py` (전체 교체):

```python
"""Import every ORM module here so Alembic sees the complete metadata."""

import news_insight.collect.models  # noqa: F401
import news_insight.sources.models  # noqa: F401
```

`apps/api/migrations/versions/0003_collection_runtime.py`:

```python
"""Collection runtime: scheduling state, fetch runs, dead letters.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), server_default="0", nullable=False)


def upgrade() -> None:
    op.create_table(
        "source_runtimes",
        sa.Column("source_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        _counter("consecutive_failures"),
        _counter("consecutive_idle"),
        sa.Column("etag", sa.String(500), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_runtimes_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", name="pk_source_runtimes"),
    )
    op.create_index("ix_source_runtimes_next_due_at", "source_runtimes", ["next_due_at"])

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("canary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        _counter("items_seen"),
        _counter("items_new"),
        _counter("items_updated"),
        _counter("items_unchanged"),
        _counter("items_incomplete"),
        _counter("duplicate_urls"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_fetch_runs_source_id_sources", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fetch_runs"),
    )
    op.create_index("ix_fetch_runs_source_started", "fetch_runs", ["source_id", "started_at"])

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_dead_letters_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fetch_run_id"],
            ["fetch_runs.id"],
            name="fk_dead_letters_fetch_run_id_fetch_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letters"),
    )
    op.create_index("ix_dead_letters_source_id", "dead_letters", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_dead_letters_source_id", table_name="dead_letters")
    op.drop_table("dead_letters")
    op.drop_index("ix_fetch_runs_source_started", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("ix_source_runtimes_next_due_at", table_name="source_runtimes")
    op.drop_table("source_runtimes")
```

- [ ] **Step 5: 테스트 통과와 마이그레이션 일치 확인**

Run: `cd apps/api && uv run pytest -q && uv run alembic upgrade head && uv run alembic check && uv run alembic downgrade 0002 && uv run alembic upgrade head`
Expected: 전체 통과 (`145 passed`), `No new upgrade operations detected.`, 다운그레이드·업그레이드 왕복 오류 없음

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add source runtime, fetch run and dead letter schema"
```

---

### Task 4: 항목 스키마와 Seen Ledger 반영

**Files:**
- Create: `apps/api/src/news_insight/content/models.py`, `apps/api/src/news_insight/content/ingest.py`, `apps/api/migrations/versions/0004_items.py`
- Modify: `apps/api/src/news_insight/model_registry.py`
- Test: `apps/api/tests/content/test_ingest.py`

**Interfaces:**
- Consumes: `RawItem` (Task 2), `FetchRun` (Task 3), `canonical_url`, `clean_text`, `content_hash`, `stable_key`, `apply_storage_right` (Task 1), `Source`
- Produces: `Item` (`id, source_id, track, stable_id, url, canonical_url, title, summary, body, body_expires_at, author, published_at, content_hash, revision, canary, first_seen_at, last_changed_at`, 관계 `revisions`), `ItemRevision` (`id, item_id, revision, content_hash, title, fetch_run_id, recorded_at`, 관계 `item`); `IngestStats(seen=0, new=0, updated=0, unchanged=0, duplicate_urls=0, rejected=0)`; `ingest_items(session, source, items, *, fetch_run: FetchRun | None, now, canary: bool) -> IngestStats`. P4·P5는 `Item.last_changed_at`과 `revision`으로 재처리 대상을 고름

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/content/test_ingest.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.content.ingest import IngestStats, ingest_items
from news_insight.content.models import Item, ItemRevision
from news_insight.sources.enums import StorageRight
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def raw(n: int, *, title: str | None = None, body: str | None = None) -> RawItem:
    return RawItem(
        stable_id=f"id-{n}",
        url=f"https://www.example.com/{n}?utm_source=rss",
        title=title or f"Title {n}",
        summary="<p>요약 텍스트</p>",
        body=body,
        published_at=NOW,
    )


def persisted(session: Session, **overrides: Any) -> Source:
    source = build_source(**overrides)
    session.add(source)
    session.flush()
    return source


def ingest(session: Session, source: Source, items: list[RawItem], **kwargs: Any) -> IngestStats:
    options: dict[str, Any] = {"fetch_run": None, "now": NOW, "canary": True, **kwargs}
    return ingest_items(session, source, items, **options)


def revision_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ItemRevision)) or 0


def test_new_items_follow_storage_policy(db_session: Session) -> None:
    source = persisted(db_session, storage_right=StorageRight.METADATA_ONLY)

    stats = ingest(db_session, source, [raw(1)])

    item = db_session.scalars(select(Item)).one()
    assert stats == IngestStats(seen=1, new=1)
    assert item.canonical_url == "https://www.example.com/1"
    assert item.summary is None
    assert (item.revision, item.canary) == (1, True)
    assert [revision.revision for revision in item.revisions] == [1]


def test_unchanged_items_write_nothing(db_session: Session) -> None:
    source = persisted(db_session)
    ingest(db_session, source, [raw(1)])

    stats = ingest(db_session, source, [raw(1)], now=LATER)

    assert stats == IngestStats(seen=1, unchanged=1)
    assert revision_count(db_session) == 1


def test_changed_items_get_a_new_revision(db_session: Session) -> None:
    source = persisted(db_session)
    ingest(db_session, source, [raw(1)])

    stats = ingest(db_session, source, [raw(1, title="Title 1 (updated)")], now=LATER)

    item = db_session.scalars(select(Item)).one()
    assert stats.updated == 1
    assert (item.revision, item.title, item.last_changed_at) == (2, "Title 1 (updated)", LATER)
    assert revision_count(db_session) == 2


def test_batch_duplicates_are_collapsed(db_session: Session) -> None:
    stats = ingest(db_session, persisted(db_session), [raw(1), raw(1)])

    assert (stats.seen, stats.new) == (2, 1)


def test_same_url_under_a_new_id_counts_as_duplicate(db_session: Session) -> None:
    copy = RawItem(stable_id="other-guid", url="https://www.example.com/1", title="Title 1 copy")

    stats = ingest(db_session, persisted(db_session), [raw(1), copy])

    assert (stats.new, stats.duplicate_urls) == (2, 1)


def test_fulltext_ttl_items_expire(db_session: Session) -> None:
    source = persisted(db_session, storage_right=StorageRight.FULLTEXT_TTL)

    ingest(db_session, source, [raw(1, body="<p>Full body</p>")])

    item = db_session.scalars(select(Item)).one()
    assert item.body == "Full body"
    assert item.body_expires_at == NOW + timedelta(days=30)


def test_overlong_ids_are_hashed_and_bad_records_rejected(db_session: Session) -> None:
    long_id = RawItem(stable_id="x" * 600, url="https://www.example.com/long", title="Long id")
    long_url = RawItem(stable_id="bad", url="https://www.example.com/" + "a" * 2100, title="Bad")
    blank = RawItem(stable_id="blank", url="https://www.example.com/blank", title="<p> </p>")

    stats = ingest(db_session, persisted(db_session), [long_id, long_url, blank])

    item = db_session.scalars(select(Item)).one()
    assert (stats.new, stats.rejected) == (1, 2)
    assert item.stable_id.startswith("sha256:")


def test_revisions_link_to_the_fetch_run(db_session: Session) -> None:
    source = persisted(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.SUCCESS)
    db_session.add(run)
    db_session.flush()

    ingest(db_session, source, [raw(1)], fetch_run=run)

    revision = db_session.scalars(select(ItemRevision)).one()
    assert revision.fetch_run_id == run.id
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/content/test_ingest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.content.ingest'`

- [ ] **Step 3: 모델과 마이그레이션 구현**

`apps/api/src/news_insight/content/models.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_insight.db import Base, str_enum
from news_insight.sources.enums import Track


class Item(Base):
    """Latest stored state of one source item (seen-ledger key: source_id + stable_id)."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "stable_id", name="uq_items_source_stable"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    track: Mapped[Track] = mapped_column(str_enum(Track))
    stable_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    body_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    canary: Mapped[bool] = mapped_column(default=False, server_default=false())
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    revisions: Mapped[list["ItemRevision"]] = relationship(
        back_populates="item", order_by="ItemRevision.revision"
    )


class ItemRevision(Base):
    """Append-only provenance: every real content change and the run that observed it."""

    __tablename__ = "item_revisions"
    __table_args__ = (
        UniqueConstraint("item_id", "revision", name="uq_item_revisions_item_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    fetch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL")
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    item: Mapped[Item] = relationship(back_populates="revisions")
```

`apps/api/src/news_insight/model_registry.py` (전체 교체):

```python
"""Import every ORM module here so Alembic sees the complete metadata."""

import news_insight.collect.models  # noqa: F401
import news_insight.content.models  # noqa: F401
import news_insight.sources.models  # noqa: F401
```

`apps/api/migrations/versions/0004_items.py`:

```python
"""Items and append-only item revisions (seen ledger).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("track", sa.String(32), nullable=False),
        sa.Column("stable_id", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("canary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_items_source_id_sources", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_items"),
        sa.UniqueConstraint("source_id", "stable_id", name="uq_items_source_stable"),
    )
    op.create_index("ix_items_canonical_url", "items", ["canonical_url"])
    op.create_index("ix_items_published_at", "items", ["published_at"])

    op.create_table(
        "item_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name="fk_item_revisions_item_id_items", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["fetch_run_id"],
            ["fetch_runs.id"],
            name="fk_item_revisions_fetch_run_id_fetch_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_item_revisions"),
        sa.UniqueConstraint("item_id", "revision", name="uq_item_revisions_item_revision"),
    )
    op.create_index("ix_item_revisions_item_id", "item_revisions", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_item_revisions_item_id", table_name="item_revisions")
    op.drop_table("item_revisions")
    op.drop_index("ix_items_published_at", table_name="items")
    op.drop_index("ix_items_canonical_url", table_name="items")
    op.drop_table("items")
```

- [ ] **Step 4: Seen Ledger 구현**

`apps/api/src/news_insight/content/ingest.py`:

```python
"""Seen ledger: store new items, record real changes as revisions, skip unchanged ones."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.collect.models import FetchRun
from news_insight.content.models import Item, ItemRevision
from news_insight.content.normalize import canonical_url, clean_text, content_hash, stable_key
from news_insight.content.policy import apply_storage_right
from news_insight.sources.models import Source

MAX_URL = 2048
TITLE_LIMIT = 1000
AUTHOR_LIMIT = 300


@dataclass(frozen=True)
class IngestStats:
    seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_urls: int = 0
    rejected: int = 0


@dataclass(frozen=True)
class _Prepared:
    stable_id: str
    url: str
    canonical: str
    title: str
    summary: str | None
    body: str | None
    author: str | None
    published_at: datetime | None
    digest: str


def _prepare(raw: RawItem) -> _Prepared | None:
    title = clean_text(raw.title, limit=TITLE_LIMIT)
    url = raw.url.strip()
    canonical = canonical_url(url) if url else ""
    if not title or not canonical or len(url) > MAX_URL or len(canonical) > MAX_URL:
        return None
    summary = clean_text(raw.summary)
    body = clean_text(raw.body)
    return _Prepared(
        stable_id=stable_key(raw.stable_id or canonical),
        url=url,
        canonical=canonical,
        title=title,
        summary=summary,
        body=body,
        author=clean_text(raw.author, limit=AUTHOR_LIMIT),
        published_at=raw.published_at,
        digest=content_hash(title, summary, body),
    )


def _apply(item: Item, candidate: _Prepared, source: Source, now: datetime) -> None:
    stored = apply_storage_right(
        source.storage_right, summary=candidate.summary, body=candidate.body, now=now
    )
    item.url = candidate.url
    item.canonical_url = candidate.canonical
    item.title = candidate.title
    item.summary = stored.summary
    item.body = stored.body
    item.body_expires_at = stored.body_expires_at
    item.author = candidate.author
    item.published_at = candidate.published_at
    item.content_hash = candidate.digest


def ingest_items(
    session: Session,
    source: Source,
    items: Sequence[RawItem],
    *,
    fetch_run: FetchRun | None,
    now: datetime,
    canary: bool,
) -> IngestStats:
    prepared: dict[str, _Prepared] = {}
    rejected = 0
    for raw in items:
        candidate = _prepare(raw)
        if candidate is None:
            rejected += 1
            continue
        prepared.setdefault(candidate.stable_id, candidate)
    if not prepared:
        return IngestStats(seen=len(items), rejected=rejected)

    existing = {
        item.stable_id: item
        for item in session.scalars(
            select(Item).where(Item.source_id == source.id, Item.stable_id.in_(list(prepared)))
        )
    }
    url_owners = dict(
        session.execute(
            select(Item.canonical_url, Item.stable_id).where(
                Item.source_id == source.id,
                Item.canonical_url.in_({candidate.canonical for candidate in prepared.values()}),
            )
        )
        .tuples()
        .all()
    )
    run_id = fetch_run.id if fetch_run is not None else None
    new = updated = unchanged = duplicates = 0
    for candidate in prepared.values():
        item = existing.get(candidate.stable_id)
        if item is None:
            owner = url_owners.setdefault(candidate.canonical, candidate.stable_id)
            if owner != candidate.stable_id:
                duplicates += 1
            item = Item(
                source_id=source.id,
                track=source.track,
                stable_id=candidate.stable_id,
                revision=1,
                canary=canary,
                first_seen_at=now,
                last_changed_at=now,
            )
            _apply(item, candidate, source, now)
            session.add(item)
            new += 1
        elif item.content_hash == candidate.digest:
            unchanged += 1  # seen-ledger hit: no write, nothing to reprocess downstream
            continue
        else:
            item.revision += 1
            item.canary = canary
            item.last_changed_at = now
            _apply(item, candidate, source, now)
            updated += 1
        session.add(
            ItemRevision(
                item=item,
                revision=item.revision,
                content_hash=candidate.digest,
                title=candidate.title,
                fetch_run_id=run_id,
                recorded_at=now,
            )
        )
    session.flush()
    return IngestStats(
        seen=len(items),
        new=new,
        updated=updated,
        unchanged=unchanged,
        duplicate_urls=duplicates,
        rejected=rejected,
    )
```

- [ ] **Step 5: 테스트 통과와 마이그레이션 일치 확인**

Run: `cd apps/api && uv run pytest -q && uv run alembic upgrade head && uv run alembic check`
Expected: `153 passed`, `No new upgrade operations detected.`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(content): add items, revisions and seen-ledger ingestion"
```

---

### Task 5: Feed Collector (조건부 GET)

**Files:**
- Modify: `apps/api/src/news_insight/parsers/feed_probe.py` (`struct_to_datetime` 공용화)
- Create: `apps/api/src/news_insight/collect/feed.py`
- Test: `apps/api/tests/collect/test_feed.py`

**Interfaces:**
- Consumes: `fetch_checked`, `conditional_headers`, `expand_macros`, contracts (Task 2), `FEED_MIME` (Phase 1)
- Produces: `feed_probe.struct_to_datetime(value) -> datetime | None`; `FeedCollector(fetcher).collect(context) -> CollectResult` (304 → `not_modified=True`, 응답의 `etag`·`last-modified` 반환, 빈 피드는 정상, 항목의 절반 넘게 불완전하면 `selector_drift`, 파싱 불가는 `parse_error`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_feed.py`:

```python
from datetime import UTC, datetime

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.feed import FeedCollector
from tests.helpers import serving
from tests.parsers.test_feed_probe import RECENT, item, rss

NOW = datetime(2026, 10, 3, tzinfo=UTC)
RICH = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<title>t</title><link>https://www.example.com</link><description>d</description>
<item><guid>g-1</guid><link>https://www.example.com/a</link><title>Galaxy S30</title>
<description>&lt;p&gt;Short&lt;/p&gt;</description>
<content:encoded><![CDATA[<p>Full body</p>]]></content:encoded>
<pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def context(**overrides: object) -> CollectContext:
    values: dict[str, object] = {
        "endpoint_url": "https://www.example.com/feed.xml",
        "config": {},
        "now": NOW,
        **overrides,
    }
    return CollectContext(**values)  # type: ignore[arg-type]


def test_parses_entries_into_raw_items() -> None:
    fetcher = serving(RICH, headers={"etag": '"v1"', "last-modified": "Thu, 01 Oct 2026"})

    result = FeedCollector(fetcher).collect(context())

    [first] = result.items
    assert (first.stable_id, first.url, first.title) == (
        "g-1",
        "https://www.example.com/a",
        "Galaxy S30",
    )
    assert first.summary is not None and "Short" in first.summary
    assert first.body == "<p>Full body</p>"
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert (result.etag, result.last_modified) == ('"v1"', "Thu, 01 Oct 2026")


def test_sends_conditional_headers() -> None:
    seen: list[httpx.Request] = []

    FeedCollector(serving(rss(item(1)), seen=seen)).collect(
        context(etag='"v1"', last_modified="Thu, 01 Oct 2026 09:00:00 GMT")
    )

    assert seen[0].headers["if-none-match"] == '"v1"'
    assert seen[0].headers["if-modified-since"] == "Thu, 01 Oct 2026 09:00:00 GMT"


def test_not_modified_keeps_validators() -> None:
    result = FeedCollector(serving(b"", status=304)).collect(context(etag='"v1"'))

    assert (result.not_modified, result.items, result.status_code, result.etag) == (
        True,
        [],
        304,
        '"v1"',
    )


def test_empty_feed_is_not_drift() -> None:
    result = FeedCollector(serving(rss())).collect(context())

    assert (result.items, result.incomplete) == ([], 0)


def test_majority_incomplete_entries_signal_drift() -> None:
    untitled = [
        {"guid": f"g-{n}", "link": f"https://www.example.com/{n}", "title": "", "date": RECENT}
        for n in (2, 3)
    ]

    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(rss(item(1), *untitled))).collect(context())

    assert (error.value.code, error.value.retryable) == ("selector_drift", False)


def test_garbage_is_a_parse_error() -> None:
    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(b"definitely not a feed")).collect(context())

    assert error.value.code == "parse_error"


def test_endpoint_macros_are_expanded() -> None:
    seen: list[httpx.Request] = []

    FeedCollector(serving(rss(item(1)), seen=seen)).collect(
        context(endpoint_url="https://www.example.com/feed?since={today-1d}")
    )

    assert seen[0].url.params["since"] == "2026-10-02"


def test_rate_limit_is_retryable() -> None:
    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(b"", status=429)).collect(context())

    assert (error.value.code, error.value.retryable) == ("rate_limited", True)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_feed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.feed'`

- [ ] **Step 3: `struct_to_datetime` 공용화**

`apps/api/src/news_insight/parsers/feed_probe.py`의 import 블록에 `from typing import Any`를 추가하고, `ProbedItem` 정의 아래에 다음 함수를 추가:

```python
def struct_to_datetime(value: Any) -> datetime | None:
    """feedparser time.struct_time (always UTC) → aware datetime."""
    if not value:
        return None
    year, month, day, hour, minute, second = (int(part) for part in value[:6])
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
```

`extract_items`의 반복문 본문을 다음으로 교체:

```python
    for entry in parsed.entries:
        url = str(entry.get("link") or "").strip()
        stable_id = str(entry.get("id") or url).strip()
        title = str(entry.get("title") or "").strip()
        published = struct_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))
        if published is None or not (stable_id and url and title):
            continue
        items.append(ProbedItem(stable_id=stable_id, url=url, title=title, published_at=published))
```

- [ ] **Step 4: Feed Collector 구현**

`apps/api/src/news_insight/collect/feed.py`:

```python
"""RSS/Atom collector with conditional GET (ETag / Last-Modified)."""

from typing import Any

import feedparser

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.http import conditional_headers, fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.parsers.feed_probe import struct_to_datetime
from news_insight.sources.checks import FEED_MIME


class FeedCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(context.endpoint_url, now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=FEED_MIME, headers=conditional_headers(context)
        )
        if response.status_code == 304:
            return CollectResult(
                items=[],
                status_code=304,
                elapsed_ms=response.elapsed_ms,
                etag=context.etag,
                last_modified=context.last_modified,
                not_modified=True,
            )
        parsed = feedparser.parse(response.content)
        if not parsed.entries and parsed.get("bozo"):
            detail = parsed.get("bozo_exception")
            raise CollectorError("parse_error", f"unparseable feed: {detail}", retryable=False)
        window = parsed.entries[: context.item_limit]
        items = [raw for entry in window if (raw := _to_item(entry)) is not None]
        incomplete = len(window) - len(items)
        if majority_incomplete(incomplete, len(window)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(window)} feed entries lack id, link or title",
                retryable=False,
            )
        return CollectResult(
            items=items,
            status_code=200,
            elapsed_ms=response.elapsed_ms,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            incomplete=incomplete,
        )


def _to_item(entry: Any) -> RawItem | None:
    url = str(entry.get("link") or "").strip()
    stable_id = str(entry.get("id") or url).strip()
    title = str(entry.get("title") or "").strip()
    if not (url and stable_id and title):
        return None
    contents = entry.get("content") or []
    body = str(contents[0].get("value") or "") if contents else ""
    return RawItem(
        stable_id=stable_id,
        url=url,
        title=title,
        published_at=struct_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed")),
        author=str(entry.get("author") or "") or None,
        summary=str(entry.get("summary") or "") or None,
        body=body or None,
    )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_feed.py tests/parsers -v`
Expected: `14 passed` (Feed 8 + 기존 probe 6)

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add RSS/Atom collector with conditional GET and drift detection"
```

---

### Task 6: JSON API Collector와 필드 헬퍼

**Files:**
- Create: `apps/api/src/news_insight/collect/fields.py`, `apps/api/src/news_insight/collect/json_api.py`
- Test: `apps/api/tests/collect/test_fields.py`, `apps/api/tests/collect/test_json_api.py`

**Interfaces:**
- Consumes: Task 2 계약·HTTP, `JSON_MIME` (Phase 1)
- Produces: `dotted_get(value, path) -> Any` (`"a.b.0.c"`, 빈 경로는 원본 그대로), `parse_datetime(value, *, assume_tz=UTC) -> datetime | None` (ISO 8601, `YYYY.MM.DD`, `YYYY/MM/DD`, epoch 초·밀리초, RFC 2822), `text_or_none(value) -> str | None`; `DEFAULT_FIELDS`; `JsonApiCollector(fetcher).collect(context)`. 설정 키는 `url`(생략 시 endpoint, 매크로 지원), `list_path`, `fields`(`id`, `url`, `title`, `summary`, `published_at`, `author` → dotted path), `item_limit`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_fields.py`:

```python
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none

OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-01T09:00:00Z", OCT_1_0900),
        ("2026-10-01", datetime(2026, 10, 1, tzinfo=UTC)),
        ("2026.10.01", datetime(2026, 10, 1, tzinfo=UTC)),
        (1790845200, OCT_1_0900),
        (1790845200000, OCT_1_0900),
        ("Thu, 01 Oct 2026 09:00:00 GMT", OCT_1_0900),
        ("not a date", None),
    ],
)
def test_parse_datetime_formats(value: Any, expected: datetime | None) -> None:
    assert parse_datetime(value) == expected


def test_naive_values_use_the_assumed_timezone() -> None:
    assert parse_datetime("2026.10.01 18:00", assume_tz=ZoneInfo("Asia/Seoul")) == OCT_1_0900


def test_dotted_get_walks_dicts_and_lists() -> None:
    payload = {"data": {"items": [{"owner": {"login": "kim"}}]}}

    assert dotted_get(payload, "data.items.0.owner.login") == "kim"
    assert dotted_get(payload, "data.missing.x") is None
    assert dotted_get(payload, "") is payload
    assert text_or_none({"nested": True}) is None
    assert text_or_none("  ") is None
```

`apps/api/tests/collect/test_json_api.py`:

```python
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.json_api import JsonApiCollector
from tests.helpers import serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
CONFIG: dict[str, Any] = {
    "list_path": "data.items",
    "fields": {
        "url": "html_url",
        "title": "name",
        "summary": "description",
        "published_at": "created_at",
        "author": "owner.login",
    },
}
RECORDS = [
    {
        "id": 101,
        "html_url": "/r/101",
        "name": "On-device LLM runtime",
        "description": "fast",
        "created_at": "2026-10-01T09:00:00Z",
        "owner": {"login": "kim"},
    },
    {"id": 102, "html_url": "https://www.example.com/r/102", "name": "NPU kernels",
     "created_at": 1790845200},
]


def payload(records: list[dict[str, Any]]) -> bytes:
    return json.dumps({"data": {"items": records}}).encode()


def collect(content: bytes, *, status: int = 200, **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.com/api/repos", config={**CONFIG, **config}, now=NOW
    )
    fetcher = serving(content, status=status, content_type="application/json")
    return JsonApiCollector(fetcher).collect(context)


def test_maps_records_with_nested_fields_and_relative_urls() -> None:
    first, second = collect(payload(RECORDS)).items

    assert (first.stable_id, first.url, first.author) == (
        "101",
        "https://www.example.com/r/101",
        "kim",
    )
    assert (first.summary, first.published_at) == ("fast", OCT_1_0900)
    assert (second.stable_id, second.published_at) == ("102", OCT_1_0900)


def test_missing_list_is_drift() -> None:
    with pytest.raises(CollectorError) as error:
        collect(payload(RECORDS), list_path="data.missing")

    assert error.value.code == "selector_drift"


def test_majority_incomplete_records_signal_drift() -> None:
    broken = [{"id": n, "html_url": f"/r/{n}"} for n in (2, 3)]

    with pytest.raises(CollectorError) as error:
        collect(payload(RECORDS[:1] + broken))

    assert error.value.code == "selector_drift"


def test_invalid_json_is_a_parse_error() -> None:
    with pytest.raises(CollectorError) as error:
        collect(b"{oops")

    assert (error.value.code, error.value.retryable) == ("parse_error", False)


def test_not_modified() -> None:
    assert collect(b"", status=304).not_modified is True


def test_item_limit_caps_records() -> None:
    assert len(collect(payload(RECORDS), item_limit=1).items) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_fields.py tests/collect/test_json_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.fields'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/collect/fields.py`:

```python
"""Field helpers for mapped records (JSON APIs and declarative HTML)."""

from datetime import UTC, datetime, tzinfo
from email.utils import parsedate_to_datetime
from typing import Any

DATE_FORMATS = ("%Y.%m.%d", "%Y/%m/%d", "%Y.%m.%d %H:%M", "%Y/%m/%d %H:%M")
EPOCH_MS_THRESHOLD = 10**11


def dotted_get(value: Any, path: str) -> Any:
    if not path:
        return value
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def parse_datetime(value: Any, *, assume_tz: tzinfo = UTC) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > EPOCH_MS_THRESHOLD else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    text = str(value).strip()
    parsed = _parse_text(text) if text else None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=assume_tz)
    return parsed.astimezone(UTC)


def _parse_text(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None


def text_or_none(value: Any) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None
    text = str(value).strip()
    return text or None
```

`apps/api/src/news_insight/collect/json_api.py`:

```python
"""Generic JSON API collector driven by a declarative field mapping."""

import json
from typing import Any
from urllib.parse import urljoin

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none
from news_insight.collect.http import conditional_headers, fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import JSON_MIME

DEFAULT_FIELDS = {
    "id": "id",
    "url": "url",
    "title": "title",
    "summary": "summary",
    "published_at": "published_at",
    "author": "author",
}


class JsonApiCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(str(context.config.get("url") or context.endpoint_url), now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=JSON_MIME, headers=conditional_headers(context)
        )
        if response.status_code == 304:
            return CollectResult(
                items=[],
                status_code=304,
                elapsed_ms=response.elapsed_ms,
                etag=context.etag,
                last_modified=context.last_modified,
                not_modified=True,
            )
        try:
            payload = json.loads(response.content)
        except ValueError as exc:
            raise CollectorError("parse_error", "response is not valid JSON", retryable=False) from exc
        list_path = str(context.config.get("list_path", ""))
        records = dotted_get(payload, list_path)
        if not isinstance(records, list):
            raise CollectorError(
                "selector_drift", f"list_path '{list_path}' is not a list", retryable=False
            )
        fields = {**DEFAULT_FIELDS, **dict(context.config.get("fields") or {})}
        window = records[: context.item_limit]
        items = [
            raw
            for record in window
            if (raw := _to_item(record, fields, base_url=response.url)) is not None
        ]
        incomplete = len(window) - len(items)
        if majority_incomplete(incomplete, len(window)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(window)} records lack url or title",
                retryable=False,
            )
        return CollectResult(
            items=items,
            status_code=200,
            elapsed_ms=response.elapsed_ms,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            incomplete=incomplete,
        )


def _to_item(record: Any, fields: dict[str, str], *, base_url: str) -> RawItem | None:
    if not isinstance(record, dict):
        return None
    link = text_or_none(dotted_get(record, fields["url"]))
    title = text_or_none(dotted_get(record, fields["title"]))
    if not (link and title):
        return None
    url = urljoin(base_url, link)
    return RawItem(
        stable_id=text_or_none(dotted_get(record, fields["id"])) or url,
        url=url,
        title=title,
        published_at=parse_datetime(dotted_get(record, fields["published_at"])),
        author=text_or_none(dotted_get(record, fields["author"])),
        summary=text_or_none(dotted_get(record, fields["summary"])),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_fields.py tests/collect/test_json_api.py -v`
Expected: `15 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add declarative JSON API collector and field helpers"
```

---

### Task 7: 선언형 크롤러와 Collector 레지스트리

**Files:**
- Create: `apps/api/src/news_insight/collect/crawler.py`, `apps/api/src/news_insight/collect/registry.py`
- Test: `apps/api/tests/collect/test_crawler.py`, `apps/api/tests/collect/test_registry.py`

**Interfaces:**
- Consumes: Task 2·6 헬퍼, `canonical_url`, `clean_text` (Task 1), `EXPECTED_MIME` (Phase 1)
- Produces: `CrawlerCollector(fetcher).collect(context)`. 설정 키는 `list_url`(생략 시 endpoint), `selectors.item|title|link`(필수), `selectors.date|summary`(선택), `timezone`(날짜에 시간대가 없을 때 적용, 기본 UTC). `stable_id`는 정규화된 링크 URL. `SUPPORTED_METHODS: frozenset[AccessMethod]` (`feed`, `json_api`, `crawler`), `collector_for(method, fetcher) -> Collector` (그 밖의 방식은 `ValueError`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_crawler.py`:

```python
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.crawler import CrawlerCollector
from tests.helpers import mock_fetcher, serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
PAGE = """<html><body><ul class="news">
<li class="row"><a class="t" href="/news/1">과기정통부, 6G 로드맵 발표</a>
  <time class="d" datetime="2026-10-01T18:00:00">10.01</time><p class="s">요약 1</p></li>
<li class="row"><a class="t" href="https://www.example.go.kr/news/2">디지털 헬스 가이드라인</a>
  <span class="d">2026.10.02</span></li>
</ul></body></html>""".encode()
SELECTORS = {"item": "li.row", "title": "a.t", "link": "a.t", "date": ".d", "summary": "p.s"}


def collect(content: bytes, *, status: int = 200, **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list",
        config={"selectors": SELECTORS, "timezone": "Asia/Seoul", **config},
        now=NOW,
    )
    return CrawlerCollector(serving(content, status=status, content_type="text/html")).collect(
        context
    )


def test_extracts_items_with_absolute_links_and_local_dates() -> None:
    first, second = collect(PAGE).items

    assert first.url == "https://www.example.go.kr/news/1"
    assert first.stable_id == "https://www.example.go.kr/news/1"
    assert (first.title, first.summary) == ("과기정통부, 6G 로드맵 발표", "요약 1")
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert second.published_at == datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def test_item_selector_without_matches_is_drift() -> None:
    with pytest.raises(CollectorError) as error:
        collect(PAGE, selectors={**SELECTORS, "item": "li.missing"})

    assert (error.value.code, error.value.retryable) == ("selector_drift", False)


def test_majority_incomplete_rows_signal_drift() -> None:
    page = b'<ul><li class="row"><a class="t" href="/1">A</a></li>' + (
        b'<li class="row"><span class="t">no link</span></li>' * 2
    ) + b"</ul>"

    with pytest.raises(CollectorError) as error:
        collect(page)

    assert error.value.code == "selector_drift"


def test_missing_required_selectors_fail_before_fetching() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list",
        config={"selectors": {"item": "li"}},
        now=NOW,
    )

    with pytest.raises(CollectorError) as error:
        CrawlerCollector(mock_fetcher(explode)).collect(context)

    assert error.value.code == "config_error"
    assert "title, link" in str(error.value)


def test_not_modified() -> None:
    assert collect(b"", status=304).not_modified is True


def test_decodes_the_declared_charset() -> None:
    page = '<ul><li class="row"><a class="t" href="/k">전자정부 공지</a></li></ul>'.encode("euc-kr")
    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list", config={"selectors": SELECTORS}, now=NOW
    )
    fetcher = serving(page, content_type="text/html; charset=EUC-KR")

    [only] = CrawlerCollector(fetcher).collect(context).items

    assert only.title == "전자정부 공지"
```

`apps/api/tests/collect/test_registry.py`:

```python
import pytest

from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod


def test_supported_methods_map_to_collectors() -> None:
    with SafeFetcher() as fetcher:
        assert isinstance(collector_for(AccessMethod.FEED, fetcher), FeedCollector)
        assert isinstance(collector_for(AccessMethod.JSON_API, fetcher), JsonApiCollector)
        assert isinstance(collector_for(AccessMethod.CRAWLER, fetcher), CrawlerCollector)
    assert SUPPORTED_METHODS == {AccessMethod.FEED, AccessMethod.JSON_API, AccessMethod.CRAWLER}


def test_unsupported_methods_are_rejected() -> None:
    with SafeFetcher() as fetcher, pytest.raises(ValueError, match="Phase 3"):
        collector_for(AccessMethod.GITHUB, fetcher)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_crawler.py tests/collect/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.crawler'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/collect/crawler.py`:

```python
"""Declarative HTML list crawler. V1 already requires terms review, robots check and selectors."""

from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser, Node

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import parse_datetime
from news_insight.collect.http import conditional_headers, fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.content.normalize import canonical_url, clean_text
from news_insight.net.safe_fetch import FetchResponse, SafeFetcher
from news_insight.sources.checks import EXPECTED_MIME
from news_insight.sources.enums import AccessMethod

HTML_MIME = EXPECTED_MIME[AccessMethod.CRAWLER]
REQUIRED_SELECTORS = ("item", "title", "link")


class CrawlerCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        selectors: dict[str, Any] = dict(context.config.get("selectors") or {})
        missing = [name for name in REQUIRED_SELECTORS if not selectors.get(name)]
        if missing:
            raise CollectorError(
                "config_error", f"missing selectors: {', '.join(missing)}", retryable=False
            )
        url = expand_macros(
            str(context.config.get("list_url") or context.endpoint_url), now=context.now
        )
        response = fetch_checked(
            self._fetcher, url, allowed_mime=HTML_MIME, headers=conditional_headers(context)
        )
        if response.status_code == 304:
            return CollectResult(
                items=[],
                status_code=304,
                elapsed_ms=response.elapsed_ms,
                etag=context.etag,
                last_modified=context.last_modified,
                not_modified=True,
            )
        nodes = HTMLParser(_decode(response)).css(str(selectors["item"]))[: context.item_limit]
        if not nodes:
            raise CollectorError(
                "selector_drift",
                f"item selector '{selectors['item']}' matched nothing",
                retryable=False,
            )
        tz = ZoneInfo(str(context.config.get("timezone", "UTC")))
        items = [
            raw
            for node in nodes
            if (raw := _to_item(node, selectors, base_url=response.url, tz=tz)) is not None
        ]
        incomplete = len(nodes) - len(items)
        if majority_incomplete(incomplete, len(nodes)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(nodes)} rows lack a title or link",
                retryable=False,
            )
        return CollectResult(
            items=items,
            status_code=200,
            elapsed_ms=response.elapsed_ms,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            incomplete=incomplete,
        )


def _decode(response: FetchResponse) -> str:
    """Decode with the declared charset (e.g. EUC-KR portals); never guess from bytes."""
    content_type = response.headers.get("content-type", "")
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip().strip('"') or charset
    try:
        return response.content.decode(charset, errors="replace")
    except LookupError:
        return response.content.decode("utf-8", errors="replace")


def _text(node: Node | None) -> str | None:
    return clean_text(node.text(separator=" ")) if node is not None else None


def _to_item(node: Node, selectors: dict[str, Any], *, base_url: str, tz: ZoneInfo) -> RawItem | None:
    title = _text(node.css_first(str(selectors["title"])))
    link_node = node.css_first(str(selectors["link"]))
    href = link_node.attributes.get("href") if link_node is not None else None
    if not (title and href):
        return None
    url = urljoin(base_url, href)
    published = None
    if selectors.get("date"):
        date_node = node.css_first(str(selectors["date"]))
        if date_node is not None:
            raw_date = date_node.attributes.get("datetime") or date_node.text()
            published = parse_datetime(raw_date, assume_tz=tz)
    summary = _text(node.css_first(str(selectors["summary"]))) if selectors.get("summary") else None
    return RawItem(
        stable_id=canonical_url(url), url=url, title=title, published_at=published, summary=summary
    )
```

`apps/api/src/news_insight/collect/registry.py`:

```python
"""Access method → collector. GitHub, AT Protocol, ActivityPub and research APIs arrive in P3."""

from news_insight.collect.contracts import Collector
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

SUPPORTED_METHODS = frozenset({AccessMethod.FEED, AccessMethod.JSON_API, AccessMethod.CRAWLER})


def collector_for(method: AccessMethod, fetcher: SafeFetcher) -> Collector:
    if method is AccessMethod.FEED:
        return FeedCollector(fetcher)
    if method is AccessMethod.JSON_API:
        return JsonApiCollector(fetcher)
    if method is AccessMethod.CRAWLER:
        return CrawlerCollector(fetcher)
    raise ValueError(f"no collector for access method '{method.value}' yet (Phase 3)")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_crawler.py tests/collect/test_registry.py -v`
Expected: `8 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add declarative HTML crawler and collector registry"
```

---

### Task 8: 적응형 주기 정책

**Files:**
- Create: `apps/api/src/news_insight/scheduling/__init__.py`, `apps/api/src/news_insight/scheduling/policy.py`
- Test: `apps/api/tests/scheduling/__init__.py`, `apps/api/tests/scheduling/test_policy.py`

**Interfaces:**
- Consumes: `PollClass`
- Produces: `POLL_RANGES: dict[PollClass, tuple[int, int]]` (초), `IDLE_GROWTH = 1.5`, `BURST_THRESHOLD = 5`, `MAX_RETRIES = 3`, `RETRY_BASE_SECONDS = 60`, `initial_interval(poll_class) -> int`, `is_idle(*, not_modified, new_items, updated_items) -> bool`, `next_interval(poll_class, current, *, idle, new_items) -> int`, `retry_delay(attempt) -> int` (1~3회차 각각 60·120·240초, 범위 밖이면 `ValueError`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/scheduling/__init__.py`: 빈 파일

`apps/api/tests/scheduling/test_policy.py`:

```python
import pytest

from news_insight.scheduling.policy import (
    POLL_RANGES,
    initial_interval,
    is_idle,
    next_interval,
    retry_delay,
)
from news_insight.sources.enums import PollClass

MIN = 60
HOUR = 3600


def test_ranges_match_requirements() -> None:
    assert POLL_RANGES == {
        PollClass.BREAKING: (5 * MIN, 15 * MIN),
        PollClass.NEWS: (15 * MIN, 60 * MIN),
        PollClass.COMMUNITY: (10 * MIN, 30 * MIN),
        PollClass.RESEARCH: (2 * HOUR, 2 * HOUR),
        PollClass.SLOW: (6 * HOUR, 24 * HOUR),
    }
    assert initial_interval(PollClass.NEWS) == 15 * MIN


def test_idle_polls_back_off_by_half_and_cap() -> None:
    assert next_interval(PollClass.NEWS, 900, idle=True, new_items=0) == 1350
    assert next_interval(PollClass.NEWS, 3000, idle=True, new_items=0) == 3600


def test_bursts_reset_to_the_fastest_interval() -> None:
    assert next_interval(PollClass.NEWS, 3600, idle=False, new_items=5) == 900


def test_some_new_items_shrink_towards_the_floor() -> None:
    assert next_interval(PollClass.NEWS, 3600, idle=False, new_items=2) == 2400
    assert next_interval(PollClass.NEWS, 1000, idle=False, new_items=1) == 900


def test_research_interval_is_fixed() -> None:
    assert next_interval(PollClass.RESEARCH, 7200, idle=True, new_items=0) == 7200
    assert next_interval(PollClass.RESEARCH, 7200, idle=False, new_items=9) == 7200


def test_idle_means_not_modified_or_nothing_new() -> None:
    assert is_idle(not_modified=True, new_items=3, updated_items=0) is True
    assert is_idle(not_modified=False, new_items=0, updated_items=0) is True
    assert is_idle(not_modified=False, new_items=0, updated_items=1) is False


def test_retry_delays_double_up_to_three_retries() -> None:
    assert [retry_delay(attempt) for attempt in (1, 2, 3)] == [60, 120, 240]
    with pytest.raises(ValueError):
        retry_delay(4)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/scheduling -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.scheduling'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/scheduling/__init__.py`: 빈 파일

`apps/api/src/news_insight/scheduling/policy.py`:

```python
"""Adaptive polling (requirements §4): health-driven intervals within per-class bounds."""

import math

from news_insight.sources.enums import PollClass

MINUTE = 60
HOUR = 3600
POLL_RANGES: dict[PollClass, tuple[int, int]] = {
    PollClass.BREAKING: (5 * MINUTE, 15 * MINUTE),
    PollClass.NEWS: (15 * MINUTE, 60 * MINUTE),
    PollClass.COMMUNITY: (10 * MINUTE, 30 * MINUTE),
    PollClass.RESEARCH: (2 * HOUR, 2 * HOUR),
    PollClass.SLOW: (6 * HOUR, 24 * HOUR),
}
IDLE_GROWTH = 1.5
BURST_THRESHOLD = 5
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 60


def initial_interval(poll_class: PollClass) -> int:
    return POLL_RANGES[poll_class][0]


def is_idle(*, not_modified: bool, new_items: int, updated_items: int) -> bool:
    return not_modified or new_items + updated_items == 0


def next_interval(poll_class: PollClass, current: int, *, idle: bool, new_items: int) -> int:
    low, high = POLL_RANGES[poll_class]
    if new_items >= BURST_THRESHOLD:
        return low
    if idle:
        candidate = math.ceil(current * IDLE_GROWTH)
    elif new_items > 0:
        candidate = math.floor(current / IDLE_GROWTH)
    else:
        candidate = current
    return max(low, min(high, candidate))


def retry_delay(attempt: int) -> int:
    """Delay before retry number `attempt` (1-based): 60 s, 120 s, 240 s."""
    if not 1 <= attempt <= MAX_RETRIES:
        raise ValueError(f"retry attempt must be 1..{MAX_RETRIES}, got {attempt}")
    return RETRY_BASE_SECONDS * 2 ** (attempt - 1)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/scheduling -v`
Expected: `7 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(scheduling): add adaptive polling and retry backoff policy"
```

---

### Task 9: Redis 도메인 예산과 소스 락

**Files:**
- Modify: `apps/api/pyproject.toml` (pytest marker `redis`), `apps/api/src/news_insight/config.py`, `apps/api/tests/conftest.py`, `apps/api/tests/test_config.py`
- Create: `apps/api/src/news_insight/scheduling/redis_guards.py`
- Test: `apps/api/tests/scheduling/test_redis_guards.py`

**Interfaces:**
- Consumes: `Settings.redis_url`
- Produces: `Settings.domain_rate_per_minute: int = 30`; `RateLimiter` Protocol (`try_acquire(domain, *, per_minute=None) -> bool`); `DomainRateLimiter(client, *, per_minute, clock=time.time, prefix="ratelimit:domain:")` (Lua 토큰 버킷, 용량 = 분당 예산); `SourceLock(client, *, ttl_seconds=900, prefix="lock:source:")`와 `.hold(source_id)` 컨텍스트 매니저 (`bool` 반환, 소유 토큰을 비교한 뒤에만 해제); `get_redis() -> redis.Redis`; pytest fixture `redis_client` (DB 15만 허용)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/pyproject.toml`의 `markers`를 다음으로 교체:

```toml
markers = [
  "db: requires the PostgreSQL test database",
  "redis: requires the Redis test database (db 15)",
]
```

`apps/api/tests/conftest.py`의 import 블록에 `import redis`를 추가하고, `TEST_DATABASE_URL` 정의 아래에 추가:

```python
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:8721/15")
```

파일 끝에 추가:

```python
@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    if not TEST_REDIS_URL.rstrip("/").endswith("/15"):
        raise RuntimeError("Refusing to flush a non-test Redis database (use db 15)")
    client = redis.Redis.from_url(TEST_REDIS_URL)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
```

`apps/api/tests/test_config.py` 끝에 추가:

```python
def test_collection_defaults() -> None:
    assert Settings(_env_file=None).domain_rate_per_minute == 30
```

`apps/api/tests/scheduling/test_redis_guards.py`:

```python
import redis
import pytest

from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock

pytestmark = pytest.mark.redis


def test_allows_the_budget_then_denies(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=3, clock=lambda: 1000.0)

    assert [limiter.try_acquire("example.com") for _ in range(4)] == [True, True, True, False]


def test_budget_refills_over_time(redis_client: redis.Redis) -> None:
    now = [1000.0]
    limiter = DomainRateLimiter(redis_client, per_minute=60, clock=lambda: now[0])
    for _ in range(60):
        assert limiter.try_acquire("example.com")
    assert limiter.try_acquire("example.com") is False

    now[0] += 1.0

    assert limiter.try_acquire("example.com") is True


def test_domains_have_independent_budgets(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=1, clock=lambda: 1000.0)

    assert limiter.try_acquire("a.example.com") is True
    assert limiter.try_acquire("a.example.com") is False
    assert limiter.try_acquire("b.example.com") is True


def test_per_call_budget_override(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=1, clock=lambda: 1000.0)

    assert limiter.try_acquire("example.com", per_minute=2) is True
    assert limiter.try_acquire("example.com", per_minute=2) is True
    assert limiter.try_acquire("example.com", per_minute=2) is False


def test_source_lock_is_exclusive(redis_client: redis.Redis) -> None:
    lock = SourceLock(redis_client)

    with lock.hold(1) as first, lock.hold(1) as second, lock.hold(2) as other:
        assert (first, second, other) == (True, False, True)


def test_source_lock_is_released_after_use(redis_client: redis.Redis) -> None:
    lock = SourceLock(redis_client)
    with lock.hold(1) as acquired:
        assert acquired

    with lock.hold(1) as again:
        assert again
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/scheduling/test_redis_guards.py tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.scheduling.redis_guards'`, `AttributeError: ... domain_rate_per_minute`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/config.py`의 `fetch_max_bytes` 줄 아래에 추가:

```python
    domain_rate_per_minute: int = 30
```

`apps/api/src/news_insight/scheduling/redis_guards.py`:

```python
"""Redis-backed guards: per-domain token-bucket budgets and per-source collection locks."""

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Protocol

import redis

from news_insight.config import get_settings

_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + math.max(0, now - ts) * refill)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 60)
return allowed
"""

_RELEASE_IF_OWNER = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class RateLimiter(Protocol):
    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool: ...


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


class DomainRateLimiter:
    def __init__(
        self,
        client: redis.Redis,
        *,
        per_minute: int,
        clock: Callable[[], float] = time.time,
        prefix: str = "ratelimit:domain:",
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._prefix = prefix
        self._script = client.register_script(_TOKEN_BUCKET)

    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        budget = per_minute or self._per_minute
        allowed = self._script(
            keys=[self._prefix + domain.lower()], args=[budget, budget / 60, self._clock()]
        )
        return allowed == 1


class SourceLock:
    def __init__(
        self, client: redis.Redis, *, ttl_seconds: int = 900, prefix: str = "lock:source:"
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._prefix = prefix
        self._release = client.register_script(_RELEASE_IF_OWNER)

    @contextmanager
    def hold(self, source_id: int) -> Iterator[bool]:
        key = f"{self._prefix}{source_id}"
        token = uuid.uuid4().hex
        acquired = bool(self._client.set(key, token, nx=True, ex=self._ttl))
        try:
            yield acquired
        finally:
            if acquired:
                self._release(keys=[key], args=[token])
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/scheduling tests/test_config.py -v`
Expected: `17 passed` (redis 6 + policy 7 + config 4)

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(scheduling): add Redis domain token bucket and source lock"
```

---

### Task 10: 수집 서비스 (1회 수집의 전체 흐름)

**Files:**
- Create: `apps/api/src/news_insight/collect/service.py`
- Test: `apps/api/tests/collect/test_service.py`

**Interfaces:**
- Consumes: Task 2~9 전체, `is_schedulable`, `pause_source` (Phase 1)
- Produces: `COLLECTABLE_STAGES`, `LOCAL_RATE_LIMIT_DELAY = timedelta(seconds=60)`, `CollectorFactory = Callable[[AccessMethod, SafeFetcher], Collector]`, `is_collectable(source) -> bool`, `ensure_runtime(session, source, now) -> SourceRuntime`, `collect_source(session, source, *, fetcher, limiter, now, collector_factory=collector_for) -> FetchRun`. 모든 경로에서 `FetchRun`이 하나 남고, `runtime.lease_until`은 해제됨

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_service.py`:

```python
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.collect.service import collect_source
from news_insight.content.models import Item, ItemRevision
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


class StubCollector:
    def __init__(self, *outcomes: CollectResult | CollectorError) -> None:
        self._outcomes = list(outcomes)
        self.contexts: list[CollectContext] = []

    def collect(self, context: CollectContext) -> CollectResult:
        self.contexts.append(context)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, CollectorError):
            raise outcome
        return outcome


class Budget:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, int | None]] = []

    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        self.calls.append((domain, per_minute))
        return self.allow


def raw(n: int) -> RawItem:
    return RawItem(stable_id=f"id-{n}", url=f"https://www.example.com/{n}", title=f"Title {n}")


def ok(*items: RawItem, etag: str | None = None) -> CollectResult:
    return CollectResult(items=list(items), status_code=200, elapsed_ms=120, etag=etag)


NOT_MODIFIED = CollectResult(items=[], status_code=304, elapsed_ms=40, not_modified=True)


def transient() -> CollectorError:
    return CollectorError("timeout", "timed out", retryable=True)


@pytest.fixture
def fetcher() -> Iterator[SafeFetcher]:
    with SafeFetcher() as instance:
        yield instance


def collectable(session: Session, **overrides: Any) -> Source:
    source = build_source(validation_stage=ValidationStage.V3, **overrides)
    session.add(source)
    session.flush()
    return source


def collect(
    session: Session,
    source: Source,
    stub: StubCollector,
    fetcher: SafeFetcher,
    *,
    budget: Budget | None = None,
    now: datetime = NOW,
) -> FetchRun:
    return collect_source(
        session,
        source,
        fetcher=fetcher,
        limiter=budget or Budget(),
        now=now,
        collector_factory=lambda method, _fetcher: stub,
    )


def runtime_of(session: Session, source: Source) -> SourceRuntime:
    runtime = session.get(SourceRuntime, source.id)
    assert runtime is not None
    return runtime


def count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_success_stores_items_and_schedules_the_next_poll(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)

    run = collect(db_session, source, StubCollector(ok(raw(1), raw(2))), fetcher)

    runtime = runtime_of(db_session, source)
    assert (run.outcome, run.http_status, run.items_new, run.canary) == (
        FetchOutcome.SUCCESS,
        200,
        2,
        True,
    )
    assert run.finished_at == NOW + timedelta(milliseconds=120)
    assert (runtime.interval_seconds, runtime.next_due_at) == (900, NOW + timedelta(seconds=900))
    assert runtime.lease_until is None
    assert count(db_session, Item) == 2


def test_identical_recollection_writes_nothing_and_backs_off(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(ok(raw(1)), ok(raw(1)))
    collect(db_session, source, stub, fetcher)

    run = collect(db_session, source, stub, fetcher, now=NOW + timedelta(minutes=15))

    runtime = runtime_of(db_session, source)
    assert (run.items_new, run.items_unchanged) == (0, 1)
    assert (runtime.interval_seconds, runtime.consecutive_idle) == (1350, 1)
    assert count(db_session, ItemRevision) == 1


def test_not_modified_reuses_validators_and_backs_off(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(ok(raw(1), etag='"v1"'), NOT_MODIFIED)
    collect(db_session, source, stub, fetcher)

    run = collect(db_session, source, stub, fetcher, now=NOW + timedelta(minutes=15))

    assert stub.contexts[1].etag == '"v1"'
    assert run.outcome is FetchOutcome.NOT_MODIFIED
    assert runtime_of(db_session, source).etag == '"v1"'
    assert runtime_of(db_session, source).interval_seconds == 1350


def test_transient_failure_schedules_a_backoff_retry(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)

    run = collect(db_session, source, StubCollector(transient()), fetcher)

    runtime = runtime_of(db_session, source)
    assert (run.outcome, run.attempt, run.error_code) == (FetchOutcome.FAILED, 1, "timeout")
    assert (runtime.consecutive_failures, runtime.next_due_at) == (
        1,
        NOW + timedelta(seconds=60),
    )
    assert count(db_session, DeadLetter) == 0


def test_fourth_consecutive_failure_is_dead_lettered(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(transient(), transient(), transient(), transient())
    now = NOW
    delays = []
    for _ in range(3):
        collect(db_session, source, stub, fetcher, now=now)
        due = runtime_of(db_session, source).next_due_at
        delays.append(int((due - now).total_seconds()))
        now = due

    run = collect(db_session, source, stub, fetcher, now=now)

    letter = db_session.scalars(select(DeadLetter)).one()
    runtime = runtime_of(db_session, source)
    assert delays == [60, 120, 240]
    assert (run.outcome, run.attempt) == (FetchOutcome.DEAD_LETTERED, 4)
    assert (letter.attempts, letter.error_code, letter.fetch_run_id) == (4, "timeout", run.id)
    assert runtime.consecutive_failures == 0
    assert runtime.next_due_at == now + timedelta(seconds=runtime.interval_seconds)


@pytest.mark.parametrize("code", ["selector_drift", "blocked_private_address"])
def test_drift_and_blocked_targets_pause_the_source(
    db_session: Session, fetcher: SafeFetcher, code: str
) -> None:
    source = collectable(db_session)
    error = CollectorError(code, "structure changed", retryable=False)

    run = collect(db_session, source, StubCollector(error), fetcher)

    assert run.outcome is FetchOutcome.DEAD_LETTERED
    assert source.status is SourceStatus.PAUSED
    assert source.paused_reason is not None and source.paused_reason.startswith(code)
    assert count(db_session, DeadLetter) == 1


def test_final_http_error_dead_letters_without_pausing(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    error = CollectorError("http_404", "HTTP 404", retryable=False, status_code=404)

    run = collect(db_session, source, StubCollector(error), fetcher)

    assert (run.outcome, run.http_status) == (FetchOutcome.DEAD_LETTERED, 404)
    assert source.status is SourceStatus.CANDIDATE


def test_local_rate_limit_defers_by_a_minute(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session, config={"rate_per_minute": 10})
    stub = StubCollector()
    budget = Budget(allow=False)

    run = collect(db_session, source, stub, fetcher, budget=budget)

    assert (run.outcome, run.error_code) == (FetchOutcome.SKIPPED, "local_rate_limit")
    assert runtime_of(db_session, source).next_due_at == NOW + timedelta(seconds=60)
    assert budget.calls == [("www.example.com", 10)]
    assert stub.contexts == []


def test_unvalidated_sources_are_not_collected(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session, validation_stage=ValidationStage.V2)
    stub = StubCollector()

    run = collect(db_session, source, stub, fetcher)

    assert (run.outcome, run.error_code) == (FetchOutcome.SKIPPED, "not_collectable")
    assert stub.contexts == []


def test_active_source_items_are_not_canary(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(
        db_session, validation_stage=ValidationStage.V6, status=SourceStatus.ACTIVE
    )

    run = collect(db_session, source, StubCollector(ok(raw(1))), fetcher)

    assert run.canary is False
    assert db_session.scalars(select(Item)).one().canary is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.service'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/collect/service.py`:

```python
"""Collect one source: rate budget → collector → seen-ledger ingest → schedule / retry / DLQ."""

from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from news_insight.collect.contracts import CollectContext, Collector, CollectorError
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.content.ingest import IngestStats, ingest_items
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.policy import (
    MAX_RETRIES,
    initial_interval,
    is_idle,
    next_interval,
    retry_delay,
)
from news_insight.scheduling.redis_guards import RateLimiter
from news_insight.sources.enums import STAGE_ORDER, AccessMethod, SourceStatus, ValidationStage
from news_insight.sources.ladder import is_schedulable, pause_source
from news_insight.sources.models import Source

CollectorFactory = Callable[[AccessMethod, SafeFetcher], Collector]
COLLECTABLE_STAGES = frozenset(STAGE_ORDER[STAGE_ORDER.index(ValidationStage.V3) :])
LOCAL_RATE_LIMIT_DELAY = timedelta(seconds=60)
MESSAGE_LIMIT = 2000


def is_collectable(source: Source) -> bool:
    """V3+ candidates collect in canary mode; active sources must be V6."""
    if source.access_method not in SUPPORTED_METHODS:
        return False
    if source.validation_stage not in COLLECTABLE_STAGES:
        return False
    if source.status is SourceStatus.ACTIVE:
        return source.validation_stage is ValidationStage.V6
    return source.status is SourceStatus.CANDIDATE


def ensure_runtime(session: Session, source: Source, now: datetime) -> SourceRuntime:
    runtime = session.get(SourceRuntime, source.id)
    if runtime is None:
        runtime = SourceRuntime(
            source_id=source.id,
            next_due_at=now,
            interval_seconds=initial_interval(source.poll_class),
            consecutive_failures=0,
            consecutive_idle=0,
        )
        session.add(runtime)
        session.flush()
    return runtime


def collect_source(
    session: Session,
    source: Source,
    *,
    fetcher: SafeFetcher,
    limiter: RateLimiter,
    now: datetime,
    collector_factory: CollectorFactory = collector_for,
) -> FetchRun:
    runtime = ensure_runtime(session, source, now)
    run = FetchRun(
        source_id=source.id,
        started_at=now,
        attempt=runtime.consecutive_failures + 1,
        canary=not is_schedulable(source),
        outcome=FetchOutcome.SKIPPED,
    )
    session.add(run)
    session.flush()
    runtime.last_attempt_at = now
    runtime.lease_until = None

    if not is_collectable(source):
        return _finish(session, run, now, error_code="not_collectable")
    domain = urlsplit(source.endpoint_url).hostname or ""
    override = source.config.get("rate_per_minute")
    if not limiter.try_acquire(domain, per_minute=int(override) if override else None):
        runtime.next_due_at = now + LOCAL_RATE_LIMIT_DELAY
        return _finish(session, run, now, error_code="local_rate_limit")

    context = CollectContext(
        endpoint_url=source.endpoint_url,
        config=dict(source.config),
        now=now,
        etag=runtime.etag,
        last_modified=runtime.last_modified,
        last_success_at=runtime.last_success_at,
    )
    try:
        result = collector_factory(source.access_method, fetcher).collect(context)
    except CollectorError as exc:
        return _handle_failure(session, source, runtime, run, exc, now)

    stats = (
        IngestStats()
        if result.not_modified
        else ingest_items(session, source, result.items, fetch_run=run, now=now, canary=run.canary)
    )
    run.outcome = FetchOutcome.NOT_MODIFIED if result.not_modified else FetchOutcome.SUCCESS
    run.http_status = result.status_code
    run.elapsed_ms = result.elapsed_ms
    run.items_seen = stats.seen
    run.items_new = stats.new
    run.items_updated = stats.updated
    run.items_unchanged = stats.unchanged
    run.items_incomplete = result.incomplete + stats.rejected
    run.duplicate_urls = stats.duplicate_urls

    idle = is_idle(
        not_modified=result.not_modified, new_items=stats.new, updated_items=stats.updated
    )
    runtime.interval_seconds = next_interval(
        source.poll_class, runtime.interval_seconds, idle=idle, new_items=stats.new
    )
    runtime.consecutive_failures = 0
    runtime.consecutive_idle = runtime.consecutive_idle + 1 if idle else 0
    runtime.etag = result.etag or runtime.etag
    runtime.last_modified = result.last_modified or runtime.last_modified
    runtime.last_success_at = now
    runtime.next_due_at = now + timedelta(seconds=runtime.interval_seconds)
    return _finish(session, run, now + timedelta(milliseconds=result.elapsed_ms))


def _handle_failure(
    session: Session,
    source: Source,
    runtime: SourceRuntime,
    run: FetchRun,
    exc: CollectorError,
    now: datetime,
) -> FetchRun:
    message = str(exc)[:MESSAGE_LIMIT]
    run.outcome = FetchOutcome.FAILED
    run.http_status = exc.status_code
    run.error_message = message
    pauses = exc.code == "selector_drift" or exc.code.startswith("blocked_")
    if exc.retryable and not pauses and run.attempt <= MAX_RETRIES:
        runtime.consecutive_failures = run.attempt
        runtime.next_due_at = now + timedelta(seconds=retry_delay(run.attempt))
        return _finish(session, run, now, error_code=exc.code)

    session.add(
        DeadLetter(
            source_id=source.id,
            fetch_run_id=run.id,
            error_code=exc.code,
            error_message=message,
            attempts=run.attempt,
        )
    )
    run.outcome = FetchOutcome.DEAD_LETTERED
    runtime.consecutive_failures = 0
    runtime.next_due_at = now + timedelta(seconds=runtime.interval_seconds)
    if pauses:
        pause_source(session, source, reason=f"{exc.code}: {message}"[:500])
    return _finish(session, run, now, error_code=exc.code)


def _finish(
    session: Session, run: FetchRun, finished_at: datetime, *, error_code: str | None = None
) -> FetchRun:
    run.finished_at = finished_at
    if error_code is not None:
        run.error_code = error_code
    session.flush()
    return run
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_service.py -v`
Expected: `11 passed` (일시정지 파라미터 2건 포함)

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): orchestrate collection with backoff, dead letters and drift pause"
```

---

### Task 11: 디스패처와 Celery 작업

**Files:**
- Create: `apps/api/src/news_insight/collect/dispatch.py`, `apps/api/src/news_insight/jobs/tasks.py`
- Modify: `apps/api/src/news_insight/jobs/celery_app.py`
- Test: `apps/api/tests/collect/test_dispatch.py`, `apps/api/tests/jobs/test_tasks.py`, `apps/api/tests/jobs/test_celery_app.py`

**Interfaces:**
- Consumes: `ensure_runtime`, `is_collectable`, `COLLECTABLE_STAGES`, `collect_source` (Task 10), `SUPPORTED_METHODS`, `DomainRateLimiter`, `SourceLock`, `get_redis` (Task 9)
- Produces: `DISPATCH_LEASE = timedelta(minutes=15)`, `bootstrap_runtimes(session, now) -> int`, `claim_due_sources(session, now, *, limit=50) -> list[int]` (`next_due_at <= now`이고 임대가 없거나 만료된 수집 가능 소스를 `FOR UPDATE SKIP LOCKED`로 잡고 `lease_until = now + 15분` 설정); Celery 작업 `collect.dispatch_due() -> int`, `collect.source(source_id) -> str` (`"locked"` / `"missing"` / outcome 값); `celery_app.BEAT_SCHEDULE`에 `collect-dispatch-due`(60초) 추가

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_dispatch.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.dispatch import DISPATCH_LEASE, bootstrap_runtimes, claim_due_sources
from news_insight.collect.models import SourceRuntime
from news_insight.sources.enums import AccessMethod, SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def add(session: Session, key: str, **overrides: Any) -> Source:
    values: dict[str, Any] = {"key": key, "validation_stage": ValidationStage.V3, **overrides}
    source = build_source(**values)
    session.add(source)
    session.flush()
    return source


def schedule(session: Session, source: Source, *, due: datetime, lease: datetime | None = None) -> None:
    session.add(
        SourceRuntime(source_id=source.id, next_due_at=due, interval_seconds=900, lease_until=lease)
    )
    session.flush()


def test_bootstrap_creates_runtimes_for_collectable_sources_only(db_session: Session) -> None:
    feed = add(db_session, "feed")
    active = add(
        db_session, "active", validation_stage=ValidationStage.V6, status=SourceStatus.ACTIVE
    )
    add(db_session, "early", validation_stage=ValidationStage.V2)
    add(db_session, "github", access_method=AccessMethod.GITHUB)
    add(db_session, "paused", status=SourceStatus.PAUSED)

    created = bootstrap_runtimes(db_session, NOW)

    ids = set(db_session.scalars(select(SourceRuntime.source_id)))
    assert created == 2
    assert ids == {feed.id, active.id}


def test_claims_due_sources_and_sets_a_lease(db_session: Session) -> None:
    source = add(db_session, "due")
    schedule(db_session, source, due=NOW - timedelta(minutes=1))

    assert claim_due_sources(db_session, NOW) == [source.id]
    runtime = db_session.get(SourceRuntime, source.id)
    assert runtime is not None and runtime.lease_until == NOW + DISPATCH_LEASE


def test_skips_future_and_leased_sources(db_session: Session) -> None:
    schedule(db_session, add(db_session, "future"), due=NOW + timedelta(minutes=5))
    schedule(
        db_session,
        add(db_session, "leased"),
        due=NOW - timedelta(minutes=5),
        lease=NOW + timedelta(minutes=5),
    )

    assert claim_due_sources(db_session, NOW) == []


def test_expired_leases_are_reclaimed(db_session: Session) -> None:
    source = add(db_session, "stale")
    schedule(
        db_session, source, due=NOW - timedelta(minutes=30), lease=NOW - timedelta(minutes=1)
    )

    assert claim_due_sources(db_session, NOW) == [source.id]


def test_claims_respect_the_limit_in_due_order(db_session: Session) -> None:
    sources = [add(db_session, f"s{n}") for n in range(3)]
    for offset, source in enumerate(sources):
        schedule(db_session, source, due=NOW - timedelta(minutes=10 - offset))

    assert claim_due_sources(db_session, NOW, limit=2) == [sources[0].id, sources[1].id]
```

`apps/api/tests/jobs/test_tasks.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import pytest

from news_insight.jobs import tasks


def test_dispatch_due_enqueues_each_claimed_source(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[object]:
        yield object()

    def claim(session: object, now: datetime) -> list[int]:
        return [3, 7]

    queued: list[int] = []
    monkeypatch.setattr(tasks, "session_scope", scope)
    monkeypatch.setattr(tasks, "claim_due_sources", claim)
    monkeypatch.setattr(tasks.collect_source_task, "delay", queued.append)

    assert tasks.dispatch_due() == 2
    assert queued == [3, 7]
```

`apps/api/tests/jobs/test_celery_app.py` 끝에 추가:

```python
def test_beat_dispatches_due_sources_every_minute() -> None:
    assert celery_app.conf.beat_schedule["collect-dispatch-due"] == {
        "task": "collect.dispatch_due",
        "schedule": 60.0,
    }
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_dispatch.py tests/jobs -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.dispatch'`, `KeyError: 'collect-dispatch-due'`

- [ ] **Step 3: 디스패처 구현**

`apps/api/src/news_insight/collect/dispatch.py`:

```python
"""Pick sources whose next poll is due and lease them so they are dispatched once."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from news_insight.collect.models import SourceRuntime
from news_insight.collect.registry import SUPPORTED_METHODS
from news_insight.collect.service import COLLECTABLE_STAGES, ensure_runtime, is_collectable
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source

DISPATCH_LEASE = timedelta(minutes=15)


def _collectable_filters() -> tuple[Any, ...]:
    return (
        Source.access_method.in_(list(SUPPORTED_METHODS)),
        Source.validation_stage.in_(list(COLLECTABLE_STAGES)),
        Source.status.in_([SourceStatus.CANDIDATE, SourceStatus.ACTIVE]),
    )


def bootstrap_runtimes(session: Session, now: datetime) -> int:
    """Give newly collectable sources a runtime row that is due immediately."""
    missing = session.scalars(
        select(Source)
        .outerjoin(SourceRuntime, SourceRuntime.source_id == Source.id)
        .where(SourceRuntime.source_id.is_(None), *_collectable_filters())
    )
    created = 0
    for source in missing:
        if is_collectable(source):
            ensure_runtime(session, source, now)
            created += 1
    return created


def claim_due_sources(session: Session, now: datetime, *, limit: int = 50) -> list[int]:
    bootstrap_runtimes(session, now)
    statement = (
        select(SourceRuntime)
        .join(Source, Source.id == SourceRuntime.source_id)
        .where(
            SourceRuntime.next_due_at <= now,
            or_(SourceRuntime.lease_until.is_(None), SourceRuntime.lease_until < now),
            *_collectable_filters(),
        )
        .order_by(SourceRuntime.next_due_at)
        .limit(limit)
        .with_for_update(of=SourceRuntime, skip_locked=True)
    )
    runtimes = list(session.scalars(statement))
    for runtime in runtimes:
        runtime.lease_until = now + DISPATCH_LEASE
    session.flush()
    return [runtime.source_id for runtime in runtimes]
```

- [ ] **Step 4: Celery 연결**

`apps/api/src/news_insight/jobs/celery_app.py` (전체 교체):

```python
from typing import Any

from celery import Celery

from news_insight.config import get_settings

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "collect-dispatch-due": {"task": "collect.dispatch_due", "schedule": 60.0},
}


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "news_insight",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["news_insight.jobs.tasks"],
    )
    app.conf.update(
        timezone=settings.timezone,
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_default_queue="default",
        beat_schedule=BEAT_SCHEDULE,
    )
    return app


celery_app = create_celery()


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
```

`apps/api/src/news_insight/jobs/tasks.py`:

```python
"""Celery entry points. They wire sessions, locks and fetchers; logic lives in services."""

from datetime import UTC, datetime

from news_insight.collect.dispatch import claim_due_sources
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.jobs.celery_app import celery_app
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock, get_redis
from news_insight.sources.models import Source


@celery_app.task(name="collect.dispatch_due")
def dispatch_due() -> int:
    with session_scope() as session:
        source_ids = claim_due_sources(session, datetime.now(UTC))
    for source_id in source_ids:
        collect_source_task.delay(source_id)
    return len(source_ids)


@celery_app.task(name="collect.source")
def collect_source_task(source_id: int) -> str:
    settings = get_settings()
    client = get_redis()
    with SourceLock(client).hold(source_id) as acquired:
        if not acquired:
            return "locked"
        with session_scope() as session, SafeFetcher.from_settings(settings) as fetcher:
            source = session.get(Source, source_id)
            if source is None:
                return "missing"
            run = collect_source(
                session,
                source,
                fetcher=fetcher,
                limiter=DomainRateLimiter(client, per_minute=settings.domain_rate_per_minute),
                now=datetime.now(UTC),
            )
            return run.outcome.value
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_dispatch.py tests/jobs -v`
Expected: `9 passed` (dispatch 5 + tasks 1 + celery 3)

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): dispatch due sources every minute via Celery beat"
```

---

### Task 12: V4 Canary 판정

**Files:**
- Create: `apps/api/src/news_insight/sources/canary.py`
- Modify: `apps/api/src/news_insight/sources/service.py` (V4 안내 문구), `apps/api/src/news_insight/jobs/tasks.py`, `apps/api/src/news_insight/jobs/celery_app.py`
- Test: `apps/api/tests/sources/test_canary.py`

**Interfaces:**
- Consumes: `FetchRun`, `FetchOutcome` (Task 3), `record_check`, `CheckResult` (Phase 1)
- Produces: 임계값 `CANARY_WINDOW_HOURS = 24`, `MIN_RUNS = 4`, `MAX_ERROR_RATE = 0.10`, `MAX_RATE_LIMITED_RATE = 0.05`, `MAX_P95_LATENCY_MS = 10_000`, `MAX_DUPLICATE_RATE = 0.20`; `CanaryMetrics(runs, window_hours, not_modified_rate, rate_limited_rate, error_rate, latency_p95_ms, duplicate_rate, items_new)`; `canary_metrics(runs, *, now) -> CanaryMetrics` (`SKIPPED` 제외); `evaluate_canary(runs, *, now) -> CheckResult | None` (관찰이 부족하면 `None`); `observation_start(session, source) -> datetime | None` (가장 최근의 V3 통과 또는 V4 실패 시각); `run_canaries(session, now) -> list[SourceValidationEvent]`; Celery 작업 `sources.run_canaries` (1시간 주기)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_canary.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.sources.canary import canary_metrics, evaluate_canary, run_canaries
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source
from tests.factories import build_source

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def run(
    hours_ago: float,
    *,
    outcome: FetchOutcome = FetchOutcome.SUCCESS,
    status: int | None = 200,
    elapsed: int | None = 300,
    new: int = 5,
    duplicates: int = 0,
    source_id: int = 1,
) -> FetchRun:
    return FetchRun(
        source_id=source_id,
        started_at=NOW - timedelta(hours=hours_ago),
        outcome=outcome,
        http_status=status,
        elapsed_ms=elapsed,
        items_new=new,
        duplicate_urls=duplicates,
    )


def healthy(hours: float = 30, count: int = 6, source_id: int = 1) -> list[FetchRun]:
    step = hours / (count - 1)
    return [run(hours - n * step, source_id=source_id) for n in range(count)]


def test_metrics_summarise_runs() -> None:
    runs = [
        run(30, elapsed=100, new=4, duplicates=1),
        run(20, outcome=FetchOutcome.NOT_MODIFIED, status=304, elapsed=200, new=0),
        run(10, outcome=FetchOutcome.FAILED, status=429, elapsed=None, new=0),
        run(1, elapsed=4000, new=4, duplicates=1),
    ]

    metrics = canary_metrics(runs, now=NOW)

    assert (metrics.runs, metrics.window_hours) == (4, 30.0)
    assert (metrics.not_modified_rate, metrics.rate_limited_rate, metrics.error_rate) == (
        0.25,
        0.25,
        0.25,
    )
    assert (metrics.latency_p95_ms, metrics.duplicate_rate, metrics.items_new) == (4000, 0.25, 8)


def test_not_ready_before_24_hours() -> None:
    assert evaluate_canary(healthy(hours=20), now=NOW) is None


def test_not_ready_with_too_few_runs() -> None:
    assert evaluate_canary(healthy(hours=30, count=3), now=NOW) is None


def test_healthy_canary_passes_with_metrics() -> None:
    result = evaluate_canary(healthy(), now=NOW)

    assert result is not None and result.passed
    assert result.metrics["runs"] == 6


def test_unhealthy_canary_lists_every_reason() -> None:
    runs = healthy()[:4] + [
        run(2, outcome=FetchOutcome.FAILED, status=429, elapsed=None),
        run(1, elapsed=12_000, new=5, duplicates=5),
    ]

    result = evaluate_canary(runs, now=NOW)

    assert result is not None and not result.passed
    assert any("error rate" in reason for reason in result.reasons)
    assert any("429" in reason for reason in result.reasons)
    assert any("p95" in reason for reason in result.reasons)


def test_skipped_runs_are_ignored() -> None:
    runs = healthy() + [run(0.5, outcome=FetchOutcome.SKIPPED, status=None, elapsed=None)]

    assert canary_metrics(runs, now=NOW).runs == 6


def at_v3(session: Session, *, passed_hours_ago: float) -> Source:
    source = build_source()
    session.add(source)
    session.flush()
    for stage in STAGE_ORDER[1 : STAGE_ORDER.index(ValidationStage.V3) + 1]:
        record_check(session, source, stage, CheckResult(passed=True))
    for event in source.validation_events:
        event.created_at = NOW - timedelta(hours=passed_hours_ago)
    session.flush()
    return source


@pytest.mark.db
def test_run_canaries_promotes_ready_candidates(db_session: Session) -> None:
    source = at_v3(db_session, passed_hours_ago=30)
    stale_failure = run(40, outcome=FetchOutcome.FAILED, status=503, source_id=source.id)
    db_session.add_all([stale_failure, *healthy(hours=29, source_id=source.id)])
    db_session.flush()

    events = run_canaries(db_session, NOW)

    assert [(event.stage, event.outcome) for event in events] == [
        (ValidationStage.V4, ValidationOutcome.PASSED)
    ]
    assert source.validation_stage is ValidationStage.V4


@pytest.mark.db
def test_failed_canary_restarts_the_window(db_session: Session) -> None:
    source = at_v3(db_session, passed_hours_ago=30)
    failure = record_check(
        db_session, source, ValidationStage.V4, CheckResult.from_reasons(["error rate 50%"])
    )
    failure.created_at = NOW - timedelta(hours=2)
    db_session.add_all(healthy(hours=29, source_id=source.id))
    db_session.flush()

    assert run_canaries(db_session, NOW) == []
    assert source.validation_stage is ValidationStage.V3
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_canary.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.sources.canary'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/sources/canary.py`:

```python
"""V4 canary: judge 24 h of real collection runs before a source may enter quality trials."""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.sources.enums import SourceStatus, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source, SourceValidationEvent

CANARY_WINDOW_HOURS = 24
MIN_RUNS = 4
MAX_ERROR_RATE = 0.10
MAX_RATE_LIMITED_RATE = 0.05
MAX_P95_LATENCY_MS = 10_000
MAX_DUPLICATE_RATE = 0.20
ERROR_OUTCOMES = frozenset({FetchOutcome.FAILED, FetchOutcome.DEAD_LETTERED})


@dataclass(frozen=True)
class CanaryMetrics:
    runs: int
    window_hours: float
    not_modified_rate: float
    rate_limited_rate: float
    error_rate: float
    latency_p95_ms: int
    duplicate_rate: float
    items_new: int


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(1, math.ceil(0.95 * len(ordered))) - 1]


def canary_metrics(runs: Sequence[FetchRun], *, now: datetime) -> CanaryMetrics:
    considered = [run for run in runs if run.outcome is not FetchOutcome.SKIPPED]
    total = len(considered)
    started = min((run.started_at for run in considered), default=now)
    items_new = sum(run.items_new for run in considered)
    return CanaryMetrics(
        runs=total,
        window_hours=round((now - started).total_seconds() / 3600, 2),
        not_modified_rate=_rate(
            sum(run.outcome is FetchOutcome.NOT_MODIFIED for run in considered), total
        ),
        rate_limited_rate=_rate(sum(run.http_status == 429 for run in considered), total),
        error_rate=_rate(sum(run.outcome in ERROR_OUTCOMES for run in considered), total),
        latency_p95_ms=_p95([run.elapsed_ms for run in considered if run.elapsed_ms is not None]),
        duplicate_rate=_rate(sum(run.duplicate_urls for run in considered), items_new),
        items_new=items_new,
    )


def evaluate_canary(runs: Sequence[FetchRun], *, now: datetime) -> CheckResult | None:
    metrics = canary_metrics(runs, now=now)
    if metrics.runs < MIN_RUNS or metrics.window_hours < CANARY_WINDOW_HOURS:
        return None
    reasons: list[str] = []
    if metrics.error_rate > MAX_ERROR_RATE:
        reasons.append(f"error rate {metrics.error_rate:.0%} exceeds {MAX_ERROR_RATE:.0%}")
    if metrics.rate_limited_rate > MAX_RATE_LIMITED_RATE:
        reasons.append(
            f"HTTP 429 rate {metrics.rate_limited_rate:.0%} exceeds {MAX_RATE_LIMITED_RATE:.0%}"
        )
    if metrics.latency_p95_ms > MAX_P95_LATENCY_MS:
        reasons.append(f"latency p95 {metrics.latency_p95_ms} ms exceeds {MAX_P95_LATENCY_MS} ms")
    if metrics.duplicate_rate > MAX_DUPLICATE_RATE:
        reasons.append(
            f"duplicate rate {metrics.duplicate_rate:.0%} exceeds {MAX_DUPLICATE_RATE:.0%}"
        )
    return CheckResult.from_reasons(reasons, asdict(metrics))


def observation_start(session: Session, source: Source) -> datetime | None:
    """The canary window restarts at the latest V3 pass or V4 failure."""
    event = SourceValidationEvent
    return session.scalar(
        select(func.max(event.created_at)).where(
            event.source_id == source.id,
            or_(
                and_(
                    event.stage == ValidationStage.V3,
                    event.outcome == ValidationOutcome.PASSED,
                ),
                and_(
                    event.stage == ValidationStage.V4,
                    event.outcome == ValidationOutcome.FAILED,
                ),
            ),
        )
    )


def run_canaries(session: Session, now: datetime) -> list[SourceValidationEvent]:
    candidates = session.scalars(
        select(Source)
        .where(
            Source.validation_stage == ValidationStage.V3,
            Source.status == SourceStatus.CANDIDATE,
        )
        .order_by(Source.key)
    )
    events: list[SourceValidationEvent] = []
    for source in list(candidates):
        since = observation_start(session, source)
        if since is None:
            continue
        runs = list(
            session.scalars(
                select(FetchRun)
                .where(FetchRun.source_id == source.id, FetchRun.started_at >= since)
                .order_by(FetchRun.started_at)
            )
        )
        result = evaluate_canary(runs, now=now)
        if result is not None:
            events.append(record_check(session, source, ValidationStage.V4, result))
    return events
```

`apps/api/src/news_insight/sources/service.py`의 `_evaluate` 마지막 `raise`와 `run_check`의 `raise`에 있는 메시지를 둘 다 다음으로 교체 (기존 테스트는 `"V4"` 포함 여부만 확인):

```python
        f"{stage.value} is judged from collection metrics "
        "(V4: `news-insight sources canary`; V5: Phase 5)"
```

`apps/api/src/news_insight/jobs/tasks.py`의 import 블록에 `from news_insight.sources.canary import run_canaries`를 추가하고 파일 끝에 추가:

```python
@celery_app.task(name="sources.run_canaries")
def run_canaries_task() -> int:
    with session_scope() as session:
        return len(run_canaries(session, datetime.now(UTC)))
```

`apps/api/src/news_insight/jobs/celery_app.py`의 `BEAT_SCHEDULE`을 다음으로 교체:

```python
BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "collect-dispatch-due": {"task": "collect.dispatch_due", "schedule": 60.0},
    "sources-run-canaries": {"task": "sources.run_canaries", "schedule": 3600.0},
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/sources -v`
Expected: 전체 통과 (canary 8건 포함). `test_v4_and_v5_are_not_automated_yet`도 계속 통과

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): judge V4 from a 24h canary window of fetch runs"
```

---

### Task 13: 전문 보존 기한과 Dead Letter 운영

**Files:**
- Create: `apps/api/src/news_insight/content/retention.py`, `apps/api/src/news_insight/collect/dead_letters.py`
- Modify: `apps/api/src/news_insight/jobs/tasks.py`, `apps/api/src/news_insight/jobs/celery_app.py`, `apps/api/tests/jobs/test_celery_app.py`
- Test: `apps/api/tests/content/test_retention.py`, `apps/api/tests/collect/test_dead_letters.py`

**Interfaces:**
- Consumes: `Item` (Task 4), `DeadLetter`, `SourceRuntime` (Task 3), `ensure_runtime` (Task 10)
- Produces: `purge_expired_bodies(session, now) -> int`; `DeadLetterError(Exception)`, `list_open(session, *, limit=50) -> list[DeadLetter]` (최신순), `dismiss(session, dead_letter_id, *, now) -> DeadLetter`, `retry(session, dead_letter_id, *, now) -> DeadLetter` (소스를 즉시 수집 대상으로 되돌림, `paused` 소스는 거부); Celery 작업 `content.purge_expired` (매일 03:15 KST)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/content/test_retention.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.content.retention import purge_expired_bodies
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def test_purge_clears_only_expired_bodies(db_session: Session) -> None:
    source = build_source()
    db_session.add(source)
    db_session.flush()
    expiries = {"expired": NOW - timedelta(minutes=1), "fresh": NOW + timedelta(days=1), "kept": None}
    for key, expires in expiries.items():
        db_session.add(
            Item(
                source_id=source.id,
                track=source.track,
                stable_id=key,
                url=f"https://www.example.com/{key}",
                canonical_url=f"https://www.example.com/{key}",
                title=key,
                body="full text",
                body_expires_at=expires,
                content_hash="0" * 64,
                first_seen_at=NOW,
                last_changed_at=NOW,
            )
        )
    db_session.flush()

    assert purge_expired_bodies(db_session, NOW) == 1
    bodies = {item.stable_id: item.body for item in db_session.scalars(select(Item))}
    assert bodies == {"expired": None, "fresh": "full text", "kept": "full text"}
```

`apps/api/tests/collect/test_dead_letters.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.dead_letters import DeadLetterError, dismiss, list_open, retry
from news_insight.collect.models import DeadLetter, SourceRuntime
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def source_with_letter(session: Session, **overrides: Any) -> tuple[Source, DeadLetter]:
    source = build_source(validation_stage=ValidationStage.V3, **overrides)
    session.add(source)
    session.flush()
    session.add(
        SourceRuntime(
            source_id=source.id,
            next_due_at=NOW + timedelta(hours=1),
            interval_seconds=900,
            consecutive_failures=2,
        )
    )
    letter = DeadLetter(source_id=source.id, error_code="timeout", error_message="t", attempts=4)
    session.add(letter)
    session.flush()
    return source, letter


def test_list_open_returns_unresolved_newest_first(db_session: Session) -> None:
    _, first = source_with_letter(db_session, key="a")
    _, second = source_with_letter(db_session, key="b")
    dismiss(db_session, first.id, now=NOW)

    assert list_open(db_session) == [second]


def test_dismiss_records_the_resolution(db_session: Session) -> None:
    _, letter = source_with_letter(db_session)

    dismiss(db_session, letter.id, now=NOW)

    assert (letter.resolved_at, letter.resolution) == (NOW, "dismissed")


def test_retry_makes_the_source_due_now(db_session: Session) -> None:
    source, letter = source_with_letter(db_session)

    retry(db_session, letter.id, now=NOW)

    runtime = db_session.get(SourceRuntime, source.id)
    assert runtime is not None
    assert (runtime.next_due_at, runtime.consecutive_failures, runtime.lease_until) == (
        NOW,
        0,
        None,
    )
    assert letter.resolution == "retried"


def test_retry_refuses_paused_sources(db_session: Session) -> None:
    _, letter = source_with_letter(
        db_session, status=SourceStatus.PAUSED, paused_reason="selector_drift: x"
    )

    with pytest.raises(DeadLetterError, match="resume it first"):
        retry(db_session, letter.id, now=NOW)


def test_resolved_letters_cannot_be_resolved_again(db_session: Session) -> None:
    _, letter = source_with_letter(db_session)
    dismiss(db_session, letter.id, now=NOW)

    with pytest.raises(DeadLetterError, match="already resolved"):
        dismiss(db_session, letter.id, now=NOW)
```

`apps/api/tests/jobs/test_celery_app.py`의 `test_beat_dispatches_due_sources_every_minute`를 다음으로 교체:

```python
def test_beat_schedule_covers_collection_canary_and_retention() -> None:
    schedule = celery_app.conf.beat_schedule

    assert schedule["collect-dispatch-due"] == {"task": "collect.dispatch_due", "schedule": 60.0}
    assert schedule["sources-run-canaries"]["task"] == "sources.run_canaries"
    assert schedule["content-purge-expired"]["task"] == "content.purge_expired"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/content/test_retention.py tests/collect/test_dead_letters.py tests/jobs -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.content.retention'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/content/retention.py`:

```python
"""Retention: drop `fulltext_ttl` bodies once their 30-day window has passed (D9)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item


def purge_expired_bodies(session: Session, now: datetime) -> int:
    expired = list(
        session.scalars(
            select(Item).where(Item.body_expires_at.is_not(None), Item.body_expires_at <= now)
        )
    )
    for item in expired:
        item.body = None
        item.body_expires_at = None
    session.flush()
    return len(expired)
```

`apps/api/src/news_insight/collect/dead_letters.py`:

```python
"""Dead-letter operations: inspect, dismiss, or send a source back for an immediate retry."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter
from news_insight.collect.service import ensure_runtime
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source


class DeadLetterError(Exception):
    """The dead letter cannot be resolved as requested."""


def list_open(session: Session, *, limit: int = 50) -> list[DeadLetter]:
    return list(
        session.scalars(
            select(DeadLetter)
            .where(DeadLetter.resolved_at.is_(None))
            .order_by(DeadLetter.id.desc())
            .limit(limit)
        )
    )


def _open_letter(session: Session, dead_letter_id: int) -> DeadLetter:
    letter = session.get(DeadLetter, dead_letter_id)
    if letter is None:
        raise DeadLetterError(f"dead letter #{dead_letter_id} does not exist")
    if letter.resolved_at is not None:
        raise DeadLetterError(f"dead letter #{dead_letter_id} is already resolved")
    return letter


def _resolve(session: Session, letter: DeadLetter, resolution: str, now: datetime) -> DeadLetter:
    letter.resolved_at = now
    letter.resolution = resolution
    session.flush()
    return letter


def dismiss(session: Session, dead_letter_id: int, *, now: datetime) -> DeadLetter:
    return _resolve(session, _open_letter(session, dead_letter_id), "dismissed", now)


def retry(session: Session, dead_letter_id: int, *, now: datetime) -> DeadLetter:
    letter = _open_letter(session, dead_letter_id)
    source = session.get(Source, letter.source_id)
    if source is None:
        raise DeadLetterError(f"source #{letter.source_id} no longer exists")
    if source.status is SourceStatus.PAUSED:
        raise DeadLetterError(
            f"{source.key} is paused ({source.paused_reason}); resume it first"
        )
    runtime = ensure_runtime(session, source, now)
    runtime.next_due_at = now
    runtime.lease_until = None
    runtime.consecutive_failures = 0
    return _resolve(session, letter, "retried", now)
```

`apps/api/src/news_insight/jobs/tasks.py`의 import 블록에 `from news_insight.content.retention import purge_expired_bodies`를 추가하고 파일 끝에 추가:

```python
@celery_app.task(name="content.purge_expired")
def purge_expired_task() -> int:
    with session_scope() as session:
        return purge_expired_bodies(session, datetime.now(UTC))
```

`apps/api/src/news_insight/jobs/celery_app.py`의 import 블록에 `from celery.schedules import crontab`를 추가하고 `BEAT_SCHEDULE`을 다음으로 교체:

```python
BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "collect-dispatch-due": {"task": "collect.dispatch_due", "schedule": 60.0},
    "sources-run-canaries": {"task": "sources.run_canaries", "schedule": 3600.0},
    "content-purge-expired": {
        "task": "content.purge_expired",
        "schedule": crontab(hour=3, minute=15),  # Asia/Seoul (celery timezone)
    },
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest tests/content/test_retention.py tests/collect/test_dead_letters.py tests/jobs -v`
Expected: `10 passed` (retention 1 + DLQ 5 + jobs 4)

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat: purge expired full text daily and add dead-letter operations"
```

---

### Task 14: 운영 CLI와 Phase 2 마무리

**Files:**
- Modify: `apps/api/src/news_insight/cli.py`, `README.md`
- Test: `apps/api/tests/test_cli_collect.py`

**Interfaces:**
- Consumes: `collect_source`, `SourceRuntime` (Task 3·10), `run_canaries` (Task 12), `list_open`, `dismiss`, `retry`, `DeadLetterError` (Task 13), `pause_source`, `resume_source` (Phase 1), `DomainRateLimiter`, `get_redis` (Task 9)
- Produces: CLI `collect run KEY` (실패·DLQ 시 종료 코드 1), `collect status`, `dlq list [--limit]`, `dlq retry ID`, `dlq dismiss ID`, `sources canary`, `sources pause KEY --reason TEXT`, `sources resume KEY`. 테스트에서 교체할 수 있도록 모듈 수준 이름 `session_scope`, `_fetcher()`, `_limiter()` 사용

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/test_cli_collect.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.collect.models import DeadLetter
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source
from tests.helpers import serving
from tests.parsers.test_feed_probe import item, rss

pytestmark = pytest.mark.db
runner = CliRunner()


class AllowAll:
    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        return True


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_fetcher", lambda: serving(rss(item(1), item(2), item(3))))
    monkeypatch.setattr(cli, "_limiter", AllowAll)


def add_source(session: Session, **overrides: Any) -> Source:
    source = build_source(validation_stage=ValidationStage.V3, **overrides)
    session.add(source)
    session.flush()
    return source


def invoke(*args: str) -> Any:
    return runner.invoke(cli.app, list(args))


def test_collect_run_reports_the_outcome(db_session: Session) -> None:
    add_source(db_session)

    result = invoke("collect", "run", "example-news")

    assert result.exit_code == 0, result.output
    assert "example-news: success http=200 new=3 updated=0 unchanged=0" in result.output


def test_collect_status_lists_the_schedule(db_session: Session) -> None:
    add_source(db_session)
    invoke("collect", "run", "example-news")

    result = invoke("collect", "status")

    assert result.exit_code == 0, result.output
    assert "example-news" in result.output and "every=15m" in result.output


def test_dlq_list_and_dismiss(db_session: Session) -> None:
    source = add_source(db_session)
    letter = DeadLetter(source_id=source.id, error_code="timeout", error_message="t", attempts=4)
    db_session.add(letter)
    db_session.flush()

    listed = invoke("dlq", "list")
    dismissed = invoke("dlq", "dismiss", str(letter.id))

    assert f"#{letter.id} example-news timeout attempts=4" in listed.output
    assert dismissed.exit_code == 0 and "dismissed" in dismissed.output


def test_dlq_retry_requires_a_resumed_source(db_session: Session) -> None:
    source = add_source(db_session, status=SourceStatus.PAUSED, paused_reason="selector_drift")
    letter = DeadLetter(
        source_id=source.id, error_code="selector_drift", error_message="x", attempts=1
    )
    db_session.add(letter)
    db_session.flush()

    blocked = invoke("dlq", "retry", str(letter.id))
    invoke("sources", "resume", "example-news")
    retried = invoke("dlq", "retry", str(letter.id))

    assert blocked.exit_code == 2 and "resume it first" in blocked.output
    assert retried.exit_code == 0 and "retried" in retried.output


def test_sources_canary_reports_when_nothing_is_ready(db_session: Session) -> None:
    add_source(db_session)

    result = invoke("sources", "canary")

    assert result.exit_code == 0
    assert "no sources ready for V4 yet" in result.output


def test_sources_pause_and_resume(db_session: Session) -> None:
    source = add_source(db_session)

    paused = invoke("sources", "pause", "example-news", "--reason", "maintenance")
    status_while_paused = source.status
    resumed = invoke("sources", "resume", "example-news")

    assert paused.exit_code == 0 and "paused (maintenance)" in paused.output
    assert status_while_paused is SourceStatus.PAUSED
    assert resumed.exit_code == 0 and source.status is SourceStatus.CANDIDATE
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_cli_collect.py -q`
Expected: FAIL — `AttributeError: <module 'news_insight.cli'> has no attribute '_limiter'`

- [ ] **Step 3: CLI 구현**

`apps/api/src/news_insight/cli.py`의 import 블록을 다음으로 교체:

```python
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from sqlalchemy import select

from news_insight.collect.dead_letters import DeadLetterError, dismiss, list_open, retry
from news_insight.collect.models import FetchOutcome, SourceRuntime
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.redis_guards import DomainRateLimiter, RateLimiter, get_redis
from news_insight.sources.canary import run_canaries
from news_insight.sources.catalog import DEFAULT_CATALOG_PATH, load_catalog, seed_catalog
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import LadderError, pause_source, resume_source
from news_insight.sources.models import Source
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
```

`app.add_typer(sources_app, name="sources")` 줄 아래에 추가:

```python
collect_app = typer.Typer(help="Collection runs and schedule", no_args_is_help=True)
dlq_app = typer.Typer(help="Dead-letter queue", no_args_is_help=True)
app.add_typer(collect_app, name="collect")
app.add_typer(dlq_app, name="dlq")

KST = ZoneInfo("Asia/Seoul")
FAILED_OUTCOMES = (FetchOutcome.FAILED, FetchOutcome.DEAD_LETTERED)
```

`_fetcher` 함수 아래에 추가:

```python
def _limiter() -> RateLimiter:
    return DomainRateLimiter(get_redis(), per_minute=get_settings().domain_rate_per_minute)


def _kst(moment: datetime | None) -> str:
    return moment.astimezone(KST).strftime("%m-%d %H:%M KST") if moment else "-"
```

파일 끝에 추가:

```python
@sources_app.command("canary")
def canary() -> None:
    """Judge V4 for V3 candidates whose 24 h observation window is complete."""
    with session_scope() as session:
        lines = [
            f"{event.source.key}: V4 {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
            for event in run_canaries(session, datetime.now(UTC))
        ]
    typer.echo("\n".join(lines) if lines else "no sources ready for V4 yet")


@sources_app.command("pause")
def pause(key: str, reason: Annotated[str, typer.Option(help="Why the source is paused")]) -> None:
    """Stop collecting a source until it is resumed."""
    try:
        with session_scope() as session:
            pause_source(session, get_source(session, key), reason=reason)
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{key}: paused ({reason})")


@sources_app.command("resume")
def resume(key: str) -> None:
    """Resume a paused source (active if it holds V6, otherwise candidate)."""
    try:
        with session_scope() as session:
            source = get_source(session, key)
            resume_source(session, source)
            status = source.status.value
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{key}: resumed as {status}")


@collect_app.command("run")
def collect_run(key: str) -> None:
    """Collect one source now (ignores the schedule, honours the domain budget)."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            run = collect_source(
                session, source, fetcher=fetcher, limiter=_limiter(), now=datetime.now(UTC)
            )
            line = (
                f"{key}: {run.outcome.value} http={run.http_status} new={run.items_new} "
                f"updated={run.items_updated} unchanged={run.items_unchanged}"
            )
            if run.error_code:
                line += f" error={run.error_code}"
            failed = run.outcome in FAILED_OUTCOMES
    except SourceNotFound as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)
    if failed:
        raise typer.Exit(code=1)


@collect_app.command("status")
def collect_status() -> None:
    """Show each scheduled source with its next poll, interval and failure streak."""
    with session_scope() as session:
        rows = session.execute(
            select(Source.key, SourceRuntime)
            .join(SourceRuntime, SourceRuntime.source_id == Source.id)
            .order_by(SourceRuntime.next_due_at)
        ).all()
        lines = [
            f"{key:<24} next={_kst(runtime.next_due_at)} every={runtime.interval_seconds // 60}m "
            f"failures={runtime.consecutive_failures} last_success={_kst(runtime.last_success_at)}"
            for key, runtime in rows
        ]
    typer.echo("\n".join(lines) if lines else "no sources scheduled yet")


@dlq_app.command("list")
def dlq_list(limit: Annotated[int, typer.Option(help="Maximum entries")] = 50) -> None:
    """List unresolved dead letters, newest first."""
    with session_scope() as session:
        lines = []
        for letter in list_open(session, limit=limit):
            source = session.get(Source, letter.source_id)
            key = source.key if source is not None else f"source#{letter.source_id}"
            lines.append(
                f"#{letter.id} {key} {letter.error_code} attempts={letter.attempts} "
                f"{_kst(letter.created_at)} {letter.error_message[:80]}"
            )
    typer.echo("\n".join(lines) if lines else "dead-letter queue is empty")


@dlq_app.command("retry")
def dlq_retry(dead_letter_id: int) -> None:
    """Resolve a dead letter and make its source due immediately."""
    try:
        with session_scope() as session:
            retry(session, dead_letter_id, now=datetime.now(UTC))
    except DeadLetterError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"#{dead_letter_id}: retried")


@dlq_app.command("dismiss")
def dlq_dismiss(dead_letter_id: int) -> None:
    """Resolve a dead letter without retrying."""
    try:
        with session_scope() as session:
            dismiss(session, dead_letter_id, now=datetime.now(UTC))
    except DeadLetterError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"#{dead_letter_id}: dismissed")
```

- [ ] **Step 4: README에 수집 운영 절 추가**

`README.md` 끝에 추가:

````markdown
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
````

- [ ] **Step 5: 전체 검증**

Run: `cd apps/api && uv run pytest tests/test_cli_collect.py -v`
Expected: `6 passed`

Run: `scripts/dev.sh verify`
Expected: 모든 단계 통과, pytest 약 `236 passed`, `No new upgrade operations detected.`

- [ ] **Step 6: Commit**

```bash
git add apps/api README.md
git commit -m "feat(cli): add collect, dead-letter and canary operations"
```

---

## Phase 2 완료 검증

1. `scripts/dev.sh verify` 전 항목 통과 (CI도 동일)
2. 통합 동작 시연 (개발 DB, 실제 네트워크):
   ```bash
   cd apps/api
   uv run alembic upgrade head
   uv run news-insight collect run hacker-news   # V3 이상이어야 수집됨. 아니면 not_collectable
   uv run news-insight collect run hacker-news   # 같은 내용이면 new=0, unchanged=N (Seen Ledger)
   uv run news-insight collect status
   ```
3. 전체 스택에서 자동 수집 확인: `scripts/dev.sh up` 후 `docker compose logs worker scheduler`에서 `collect.dispatch_due`와 `collect.source`가 실행되는지 확인
4. **실제 24시간 Canary (운영자 작업 필요):** 시드 Feed 소스의 `terms_url`·`storage_right`를 약관 검토 후 `catalog/sources.yaml`에 기록하고 `sources seed`·`sources validate`로 V3까지 올립니다. 스택을 24시간 이상 켜 둔 뒤 `sources canary`로 V4 판정이 기록되는지 확인합니다.

## Self-Review 결과

- **요구사항 대비 범위:** §4 적응형 주기 → Task 8·10·11, Rate-limit·타임아웃·리다이렉트 → Task 9 + Phase 1 SafeFetcher, 재시도·Dead Letter → Task 10·13, Selector Drift 자동 일시정지 → Task 5·6·7·10. §5 Seen Ledger → Task 1·4. §3 V4 → Task 12. V5·V6 자동 승격은 D8에 따라 P5로 이관. D9 저장 정책 → Task 1·4·13.
- **누락 표시 점검:** 미완성 표시나 "Task N과 같음" 같은 참조 없이, 모든 코드 단계에 전체 코드 또는 정확한 교체 지점을 넣었습니다.
- **이름 일관성:** `CollectContext(endpoint_url, config, now, …)`, `CollectorError(code, message, *, retryable, status_code)`, `ingest_items(…, fetch_run=, now=, canary=)`, `next_interval(…, idle=, new_items=)`, `RateLimiter.try_acquire(domain, *, per_minute=None)`, `collect_source(…, collector_factory=)`, `claim_due_sources(session, now, *, limit=50)`, `evaluate_canary(runs, *, now)`가 정의한 곳과 사용하는 곳에서 같은 시그니처로 쓰이는 것을 확인했습니다.
- **테스트 수 누계 (Python, Phase 1의 112개부터):** Task 1: 125 → 2: 141 → 3: 145 → 4: 153 → 5: 161 → 6: 176 → 7: 184 → 8: 191 → 9: 198 → 10: 209 → 11: 216 → 12: 224 → 13: 230 → 14: 236. 각 단계의 Expected와 다르면 누락되었거나 중복 수집된 테스트 파일이 있는지 먼저 확인합니다.
