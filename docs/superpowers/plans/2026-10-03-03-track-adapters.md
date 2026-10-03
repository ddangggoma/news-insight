# Phase 3 — Track Adapters & Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use dev_sp_subagent-driven-development (recommended) or dev_sp_executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 4개 트랙(뉴스·커뮤니티·연구/특허·OSS)의 모든 접근 방식을 수집할 수 있게 하고, 반응 지표(스타·좋아요·점수) 스냅샷과 변화량을 기록합니다. 그 위에 V0·V2·V3 사전 점검을 통과한 카탈로그 후보를 260개 규모로 확장합니다.

**Architecture:** 실제 API 응답을 확인한 결과, Bluesky·Mastodon·Stack Exchange·HN(Algolia)·DEV·OpenAlex·Crossref·Europe PMC·GitHub는 모두 "목록 경로 + 필드 매핑"으로 표현할 수 있었습니다. 그래서 전용 수집기를 따로 만들지 않고 P2의 `JsonApiCollector`를 확장합니다(대체 경로, URL 템플릿, 지표 매핑, 제목 길이 제한). API별 매핑은 `collect/presets.py`의 프리셋으로 묶고, 카탈로그는 `config.preset`으로 참조합니다. 자격 증명은 카탈로그에 이름만 적고 값은 `SOURCE_SECRET_<NAME>` 환경 변수에서 읽습니다(D11). V3는 접근 방식과 무관하게 "실제 수집기로 한 번 수집해서 최근 항목 3건 이상"으로 통일합니다. arXiv API와 YouTube 채널은 Atom/RSS라서 기존 `FeedCollector`를 그대로 씁니다.

**Tech Stack:** Phase 2 스택 그대로 (새 런타임 의존성 없음)

## Global Constraints

- 수집 대상 트랙 목표: 뉴스 100 / 커뮤니티 100 / 연구·특허 35 / OSS 25 (합계 260). 지역 용량 65/117/26/21/31 (D2)
- 자격 증명 (D11): 카탈로그에는 `config.auth.secret: NAME`만 기록하고, 값은 `SOURCE_SECRET_NAME` 환경 변수에서만 읽음. 이름은 `^[A-Z][A-Z0-9_]{1,62}$` 형식만 허용. 값은 로그·오류 메시지·DB에 남기지 않음. 리다이렉트로 호스트가 바뀌면 인증 헤더를 보내지 않음
- 키 정책 (D6): GitHub 토큰만 사용 (`SOURCE_SECRET_GITHUB_TOKEN`). YouTube는 채널 RSS, EPO OPS·KIPRIS·USPTO는 이번 Phase에서 제외
- OpenReview는 봇 검증을 요구하므로 제외 (D12). CAPTCHA나 봇 탐지 우회 금지
- 수집기가 실제로 요청하는 모든 URL(`endpoint_url`, `config.url`, `config.list_url`, `config.probe_url`)은 V0에서 공식 도메인 아래인지 확인
- V3 통일 기준: 수집기로 한 번 수집해서 발행일이 있는 최근 30일 이내 항목 3건 이상 (`config.probe_max_age_days`로 연장 가능, 최소 3건은 낮출 수 없음)
- 반응 지표 스냅샷은 값이 바뀌었고 마지막 기록에서 1시간 이상 지났을 때만 저장 (불필요한 쓰기 방지)
- 카탈로그 후보는 `terms_url` 없이 `storage_right: metadata_only`로 등록합니다. 약관 판단(V1)은 운영자가 런북에 따라 직접 함
- Stack Exchange API는 키 없이 IP당 하루 300회 제한이 있으므로, Stack Exchange 소스는 6개 이하 + `poll_class: slow`로 등록
- Phase 1·2의 제약(SafeFetcher, 포트, mypy strict, `scripts/dev.sh verify`)은 그대로 유지

---

## File Structure

```
apps/api/src/news_insight/
├── secrets.py                    # config.auth → 인증 헤더 (SOURCE_SECRET_* 환경 변수)
├── net/
│   ├── mime.py                   # 접근 방식별 허용 MIME (sources.checks에서 이동)
│   └── safe_fetch.py             # (수정) 교차 호스트 리다이렉트 시 민감 헤더 제거
├── collect/
│   ├── contracts.py              # (수정) RawItem.metrics, CollectContext.headers
│   ├── http.py                   # (수정) request_headers, GitHub식 403 rate limit
│   ├── json_api.py               # (수정) 대체 경로·URL 템플릿·지표·제목 제한
│   ├── presets.py                # API별 매핑 프리셋 + effective_config
│   ├── context.py                # Source → CollectContext (프리셋·자격 증명 반영)
│   ├── registry.py               # (수정) 모든 접근 방식 지원
│   └── service.py                # (수정) collect_context 사용, config_error 일시정지
├── content/
│   ├── models.py                 # (수정) ItemMetricSnapshot
│   ├── ingest.py                 # (수정) 지표 스냅샷 기록
│   └── trends.py                 # 지표 변화량(movers)
├── sources/
│   ├── checks.py                 # (수정) V0 URL 확장, V1 자격 증명, V2 매크로, V3 통일
│   ├── catalog.py                # (수정) 알 수 없는 프리셋 거부
│   └── service.py                # (수정) probe_source (DB 없이 사전 점검)
└── cli.py                        # (수정) sources probe / probe-catalog, trends movers
apps/api/migrations/versions/0005_item_metric_snapshots.py
apps/api/catalog/sources.yaml     # 260개 규모 후보
compose.yaml, .env.example        # SOURCE_SECRET_GITHUB_TOKEN 전달
```

---

### Task 1: 자격 증명 참조와 보안 강화

**Files:**
- Create: `apps/api/src/news_insight/secrets.py`
- Modify: `apps/api/src/news_insight/net/safe_fetch.py`, `apps/api/src/news_insight/sources/checks.py`, `compose.yaml`, `.env.example`
- Test: `apps/api/tests/test_secrets.py`, `apps/api/tests/net/test_safe_fetch.py`, `apps/api/tests/sources/test_checks_policy.py`

**Interfaces:**
- Consumes: Phase 1 `check_identity`, `check_policy`, `SafeFetcher`
- Produces: `SECRET_PREFIX = "SOURCE_SECRET_"`, `SecretError(Exception)`, `secret_env_name(name) -> str`, `resolve_auth_headers(config, *, environ=os.environ) -> dict[str, str]` (`config.auth = {"secret": NAME, "scheme": "bearer"|"header", "header": "X-Api-Key"}`); `safe_fetch.CROSS_HOST_SAFE_HEADERS`; V0는 `config.url`·`config.list_url` 호스트도 검사; V1은 선언된 자격 증명이 없으면 `credential SOURCE_SECRET_<NAME> is not configured`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/test_secrets.py`:

```python
import pytest

from news_insight.secrets import SecretError, resolve_auth_headers


def test_no_auth_means_no_headers() -> None:
    assert resolve_auth_headers({}, environ={}) == {}


def test_bearer_token_from_prefixed_variable() -> None:
    headers = resolve_auth_headers(
        {"auth": {"secret": "GITHUB_TOKEN"}}, environ={"SOURCE_SECRET_GITHUB_TOKEN": "t0k"}
    )

    assert headers == {"Authorization": "Bearer t0k"}


def test_custom_header_scheme() -> None:
    config = {"auth": {"scheme": "header", "header": "X-Api-Key", "secret": "YOUTUBE_KEY"}}

    assert resolve_auth_headers(config, environ={"SOURCE_SECRET_YOUTUBE_KEY": "k"}) == {
        "X-Api-Key": "k"
    }


def test_missing_secret_is_reported_without_a_value() -> None:
    with pytest.raises(SecretError, match="SOURCE_SECRET_GITHUB_TOKEN is not configured"):
        resolve_auth_headers({"auth": {"secret": "GITHUB_TOKEN"}}, environ={})


def test_secret_names_cannot_reach_other_variables() -> None:
    with pytest.raises(SecretError, match="invalid secret name"):
        resolve_auth_headers({"auth": {"secret": "postgres_password"}}, environ={})
    with pytest.raises(SecretError, match="not configured"):
        resolve_auth_headers(
            {"auth": {"secret": "POSTGRES_PASSWORD"}}, environ={"POSTGRES_PASSWORD": "db"}
        )


def test_unsupported_scheme_is_rejected() -> None:
    config = {"auth": {"scheme": "basic", "secret": "TOKEN"}}

    with pytest.raises(SecretError, match="unsupported auth scheme"):
        resolve_auth_headers(config, environ={"SOURCE_SECRET_TOKEN": "x"})
```

`apps/api/tests/net/test_safe_fetch.py` 끝에 추가:

```python
def recording_redirect(target: str, seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    return handler


def test_credentials_are_dropped_on_cross_host_redirect() -> None:
    seen: list[httpx.Request] = []
    fetcher = make_fetcher(recording_redirect("https://cdn.example.net/file", seen))

    fetcher.fetch("https://example.com/start", headers={"Authorization": "Bearer secret"})

    assert seen[0].headers["authorization"] == "Bearer secret"
    assert "authorization" not in seen[1].headers
    assert seen[1].headers["user-agent"].startswith("DailyITIntelligenceBot/")


def test_credentials_survive_same_host_redirect() -> None:
    seen: list[httpx.Request] = []
    fetcher = make_fetcher(recording_redirect("/next", seen))

    fetcher.fetch("https://example.com/start", headers={"Authorization": "Bearer secret"})

    assert seen[1].headers["authorization"] == "Bearer secret"
```

`apps/api/tests/sources/test_checks_policy.py`의 import 블록에 `import pytest`를 추가하고 끝에 추가:

```python
def test_identity_checks_collector_urls() -> None:
    result = check_identity(build_source(config={"url": "https://other.org/api"}))

    assert "url host 'other.org' is not under official domain 'example.com'" in result.reasons


def test_policy_requires_declared_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_SECRET_GITHUB_TOKEN", raising=False)
    source = build_source(config={"auth": {"secret": "GITHUB_TOKEN"}})

    assert "credential SOURCE_SECRET_GITHUB_TOKEN is not configured" in check_policy(source).reasons
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_secrets.py tests/net/test_safe_fetch.py tests/sources/test_checks_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.secrets'`, 교차 호스트 테스트와 V0·V1 테스트 assertion 실패

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/secrets.py`:

```python
"""Source credentials: the catalog references secrets by name; values live only in env vars.

`config.auth.secret: GITHUB_TOKEN` reads `SOURCE_SECRET_GITHUB_TOKEN`. The prefix keeps a
catalog entry from pointing at unrelated variables such as the database password.
"""

import os
import re
from collections.abc import Mapping
from typing import Any

SECRET_PREFIX = "SOURCE_SECRET_"
SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,62}$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class SecretError(Exception):
    """A referenced credential is malformed or not configured (never includes the value)."""


def secret_env_name(name: str) -> str:
    if not SECRET_NAME.fullmatch(name):
        raise SecretError(f"invalid secret name '{name}'")
    return SECRET_PREFIX + name


def resolve_auth_headers(
    config: Mapping[str, Any], *, environ: Mapping[str, str] = os.environ
) -> dict[str, str]:
    auth = config.get("auth")
    if auth is None:
        return {}
    if not isinstance(auth, Mapping):
        raise SecretError("config.auth must be a mapping")
    env_name = secret_env_name(str(auth.get("secret", "")))
    value = environ.get(env_name, "").strip()
    if not value:
        raise SecretError(f"credential {env_name} is not configured")
    scheme = str(auth.get("scheme", "bearer"))
    if scheme == "bearer":
        return {"Authorization": f"Bearer {value}"}
    if scheme == "header":
        header = str(auth.get("header", ""))
        if not HEADER_NAME.fullmatch(header):
            raise SecretError("config.auth.header is not a valid header name")
        return {header: value}
    raise SecretError(f"unsupported auth scheme '{scheme}'")
```

`apps/api/src/news_insight/net/safe_fetch.py`의 `REDIRECT_STATUSES` 정의 아래에 추가:

```python
CROSS_HOST_SAFE_HEADERS = frozenset({"user-agent", "accept", "if-none-match", "if-modified-since"})


def _cross_host_headers(headers: dict[str, str]) -> dict[str, str]:
    """Never forward credentials (or any non-essential header) to a different host."""
    return {name: value for name, value in headers.items() if name.lower() in CROSS_HOST_SAFE_HEADERS}
```

같은 파일의 `fetch`에서 `current = url` 줄 위에 `origin_host = httpx.URL(url).host`를 추가하고, 리다이렉트 처리부의 `redirects.append(current)` 다음 줄(그리고 `continue` 앞)에 추가:

```python
                        if httpx.URL(current).host != origin_host:
                            request_headers = _cross_host_headers(request_headers)
```

`apps/api/src/news_insight/sources/checks.py`의 import 블록에 `from news_insight.secrets import SecretError, resolve_auth_headers`를 추가합니다. `check_identity`의 반복 대상 튜플을 다음으로 교체:

```python
    for label, url in (
        ("endpoint", source.endpoint_url),
        ("probe", source.config.get("probe_url")),
        ("url", source.config.get("url")),
        ("list_url", source.config.get("list_url")),
    ):
```

`check_policy`의 `storage = ...` 줄 바로 위에 추가:

```python
    try:
        resolve_auth_headers(source.config)
    except SecretError as exc:
        reasons.append(str(exc))
```

`compose.yaml`의 `x-python-env`에서 `ADMIN_EMAIL` 줄 아래에 추가:

```yaml
  SOURCE_SECRET_GITHUB_TOKEN: ${SOURCE_SECRET_GITHUB_TOKEN:-}
```

`.env.example` 끝에 추가:

```dotenv
# Source credentials (roadmap D11): the catalog references them by name
# (config.auth.secret: GITHUB_TOKEN) and the value is read from SOURCE_SECRET_<NAME>.
# Local CLI runs: `uv run --env-file ../../.env news-insight ...`. Never commit real values.
SOURCE_SECRET_GITHUB_TOKEN=
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -q && cd ../.. && docker compose --env-file .env.example config --quiet`
Expected: `246 passed`, compose config 오류 없음

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api compose.yaml .env.example
git commit -m "feat: reference source credentials by name and drop them on cross-host redirects"
```

---

### Task 2: JSON 매핑 확장과 인증 헤더 전달

**Files:**
- Modify: `apps/api/src/news_insight/collect/contracts.py`, `collect/http.py`, `collect/feed.py`, `collect/crawler.py`, `collect/json_api.py`, `collect/registry.py`
- Test: `apps/api/tests/collect/test_json_api.py`, `tests/collect/test_http.py`, `tests/collect/test_registry.py`, `tests/collect/test_dispatch.py`

**Interfaces:**
- Consumes: Task 1 (헤더는 상위 계층에서 해석됨)
- Produces: `RawItem.metrics: dict[str, int]`, `CollectContext.headers: dict[str, str]`; `request_headers(context) -> dict[str, str]` (인증 헤더 + 조건부 요청 헤더); `fetch_checked`에서 `403` + `x-ratelimit-remaining: 0`을 `rate_limited`(retryable)로 처리; JSON 매핑 설정 확장 — `fields.<name>`에 문자열 또는 경로 목록(앞에서부터 첫 값), `url_template`(`{a.b}`, `{a.b|last}` 자리표시자, `fields.url`이 비면 사용), `title_limit`, `metrics: {name: path}` (정수만); `render_template(template, record) -> str | None`, `extract_metrics(record, mapping) -> dict[str, int]`; `SUPPORTED_METHODS == set(AccessMethod)` (`github`·`atproto`·`activitypub`·`research_api`는 `JsonApiCollector`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_json_api.py` 끝에 추가:

```python
def collect_records(records: list[dict[str, Any]], **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.com/api",
        config={"list_path": "data.items", **config},
        now=NOW,
    )
    fetcher = serving(payload(records), content_type="application/json")
    return JsonApiCollector(fetcher).collect(context)


def test_field_alternatives_take_the_first_non_empty_value() -> None:
    record = {"id": 1, "html_url": "https://www.example.com/r/1", "name": "", "tag_name": "v1.0"}

    [item] = collect_records(
        [record], fields={"url": "html_url", "title": ["name", "tag_name"]}
    ).items

    assert item.title == "v1.0"


def test_url_template_fills_missing_links() -> None:
    record = {
        "post": {
            "uri": "at://did:plc:abc/app.bsky.feed.post/3kq",
            "author": {"handle": "bsky.app"},
            "record": {"text": "hello world", "createdAt": "2026-10-01T09:00:00Z"},
        }
    }

    [item] = collect_records(
        [record],
        fields={
            "id": "post.uri",
            "url": [],
            "title": "post.record.text",
            "published_at": "post.record.createdAt",
        },
        url_template="https://bsky.app/profile/{post.author.handle}/post/{post.uri|last}",
    ).items

    assert item.url == "https://bsky.app/profile/bsky.app/post/3kq"
    assert item.stable_id == "at://did:plc:abc/app.bsky.feed.post/3kq"


def test_title_limit_shortens_html_posts() -> None:
    record = {"id": 1, "url": "https://www.example.com/p/1", "title": "<p>" + "가" * 200 + "</p>"}

    [item] = collect_records([record], title_limit=50).items

    assert len(item.title) == 50
    assert "<p>" not in item.title


def test_metrics_are_mapped_to_integers() -> None:
    record = {
        "id": 1,
        "url": "https://www.example.com/p/1",
        "title": "repo",
        "stargazers_count": 16168,
        "archived": False,
    }

    [item] = collect_records(
        [record], metrics={"stars": "stargazers_count", "flag": "archived", "gone": "missing"}
    ).items

    assert item.metrics == {"stars": 16168}


def test_credential_headers_are_sent() -> None:
    seen: list[httpx.Request] = []
    context = CollectContext(
        endpoint_url="https://www.example.com/api",
        config=CONFIG,
        now=NOW,
        headers={"Authorization": "Bearer t0k"},
    )

    JsonApiCollector(serving(payload(RECORDS), content_type="application/json", seen=seen)).collect(
        context
    )

    assert seen[0].headers["authorization"] == "Bearer t0k"
```

같은 파일 import 블록에 `import httpx`를 추가합니다.

`apps/api/tests/collect/test_http.py` import에 `request_headers`를 추가(`from news_insight.collect.http import conditional_headers, fetch_checked, request_headers`)하고 끝에 추가:

```python
def test_github_style_403_rate_limit_is_retryable() -> None:
    fetcher = serving(b"", status=403, headers={"x-ratelimit-remaining": "0"})

    with pytest.raises(CollectorError) as error:
        fetch_checked(fetcher, URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("rate_limited", True)


def test_request_headers_merge_credentials_and_validators() -> None:
    context = CollectContext(
        endpoint_url=URL,
        config={},
        now=datetime(2026, 10, 3, tzinfo=UTC),
        etag='"v1"',
        headers={"Authorization": "Bearer t"},
    )

    assert request_headers(context) == {"Authorization": "Bearer t", "If-None-Match": '"v1"'}
```

`apps/api/tests/collect/test_registry.py` (전체 교체):

```python
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

JSON_METHODS = (
    AccessMethod.JSON_API,
    AccessMethod.GITHUB,
    AccessMethod.ATPROTO,
    AccessMethod.ACTIVITYPUB,
    AccessMethod.RESEARCH_API,
)


def test_every_access_method_has_a_collector() -> None:
    with SafeFetcher() as fetcher:
        assert isinstance(collector_for(AccessMethod.FEED, fetcher), FeedCollector)
        assert isinstance(collector_for(AccessMethod.CRAWLER, fetcher), CrawlerCollector)
        for method in JSON_METHODS:
            assert isinstance(collector_for(method, fetcher), JsonApiCollector)
    assert set(SUPPORTED_METHODS) == set(AccessMethod)
```

`apps/api/tests/collect/test_dispatch.py`에서 `add(db_session, "github", access_method=AccessMethod.GITHUB)`를 `add(db_session, "retired", status=SourceStatus.RETIRED)`로 바꾸고, import 줄의 `AccessMethod, `를 지웁니다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect -q`
Expected: FAIL — `TypeError: CollectContext.__init__() got an unexpected keyword argument 'headers'`, `ImportError: cannot import name 'request_headers'`

- [ ] **Step 3: 계약과 HTTP 헬퍼 확장**

`apps/api/src/news_insight/collect/contracts.py`에서 `from dataclasses import dataclass`를 `from dataclasses import dataclass, field`로 바꾸고, `RawItem`의 `body` 필드 아래와 `CollectContext`의 `last_success_at` 필드 아래에 각각 추가:

```python
    metrics: dict[str, int] = field(default_factory=dict)
```

```python
    headers: dict[str, str] = field(default_factory=dict)
```

`apps/api/src/news_insight/collect/http.py`의 `conditional_headers` 아래에 추가:

```python
def request_headers(context: CollectContext) -> dict[str, str]:
    """Credential headers resolved for the source, plus conditional-request validators."""
    return {**context.headers, **conditional_headers(context)}
```

같은 파일 `fetch_checked`의 `if status == 429:` 줄 바로 위에 추가:

```python
    if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise CollectorError("rate_limited", message, retryable=True, status_code=status)
```

Run: `cd apps/api && sed -i '' 's/conditional_headers(context)/request_headers(context)/; s/import conditional_headers, fetch_checked/import fetch_checked, request_headers/' src/news_insight/collect/feed.py src/news_insight/collect/crawler.py src/news_insight/collect/json_api.py && grep -n "request_headers" src/news_insight/collect/feed.py src/news_insight/collect/crawler.py src/news_insight/collect/json_api.py`
Expected: 세 파일 각각 import 1줄 + 호출 1줄

- [ ] **Step 4: JSON 매핑 확장**

`apps/api/src/news_insight/collect/json_api.py` (전체 교체):

```python
"""Generic JSON collector driven by a declarative mapping.

Mapping keys: `list_path`, `fields` (each a dotted path or a list of fallbacks),
`url_template` (`{a.b}` / `{a.b|last}`, used when no `fields.url` path yields a link),
`title_limit`, and `metrics` ({name: dotted path} of integer signals).
"""

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.collect.macros import expand_macros
from news_insight.content.normalize import clean_text
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import JSON_MIME

DEFAULT_FIELDS: dict[str, Any] = {
    "id": "id",
    "url": "url",
    "title": "title",
    "summary": "summary",
    "published_at": "published_at",
    "author": "author",
}
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.\-]+)(\|last)?\}")


@dataclass(frozen=True)
class _Mapping:
    fields: dict[str, Any]
    url_template: str | None
    title_limit: int | None
    metrics: dict[str, Any]


class JsonApiCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(str(context.config.get("url") or context.endpoint_url), now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=JSON_MIME, headers=request_headers(context)
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
        mapping = _Mapping(
            fields={**DEFAULT_FIELDS, **dict(context.config.get("fields") or {})},
            url_template=str(context.config.get("url_template") or "") or None,
            title_limit=_int_or_none(context.config.get("title_limit")),
            metrics=dict(context.config.get("metrics") or {}),
        )
        window = records[: context.item_limit]
        items = [
            raw
            for record in window
            if (raw := _to_item(record, mapping, base_url=response.url)) is not None
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _paths(spec: Any) -> list[str]:
    return [str(path) for path in spec] if isinstance(spec, list) else [str(spec)]


def first_value(record: Any, spec: Any) -> Any:
    for path in _paths(spec):
        value = dotted_get(record, path)
        if value not in (None, "", []):
            return value
    return None


def first_text(record: Any, spec: Any) -> str | None:
    for path in _paths(spec):
        value = text_or_none(dotted_get(record, path))
        if value:
            return value
    return None


def render_template(template: str, record: Any) -> str | None:
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        value = text_or_none(dotted_get(record, match.group(1)))
        if value is None:
            missing = True
            return ""
        if match.group(2):
            value = value.rstrip("/").rsplit("/", 1)[-1]
        return quote(value, safe="@.-_~")

    rendered = PLACEHOLDER.sub(replace, template)
    return None if missing else rendered


def extract_metrics(record: Any, mapping: dict[str, Any]) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for name, path in mapping.items():
        value = dotted_get(record, str(path))
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            metrics[str(name)] = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            metrics[str(name)] = int(value.strip())
    return metrics


def _to_item(record: Any, mapping: _Mapping, *, base_url: str) -> RawItem | None:
    if not isinstance(record, dict):
        return None
    link = first_text(record, mapping.fields["url"])
    if link is None and mapping.url_template:
        link = render_template(mapping.url_template, record)
    title = first_text(record, mapping.fields["title"])
    if title and mapping.title_limit:
        title = clean_text(title, limit=mapping.title_limit)
    if not (link and title):
        return None
    url = urljoin(base_url, link)
    return RawItem(
        stable_id=first_text(record, mapping.fields["id"]) or url,
        url=url,
        title=title,
        published_at=parse_datetime(first_value(record, mapping.fields["published_at"])),
        author=first_text(record, mapping.fields["author"]),
        summary=first_text(record, mapping.fields["summary"]),
        metrics=extract_metrics(record, mapping.metrics),
    )
```

`apps/api/src/news_insight/collect/registry.py` (전체 교체):

```python
"""Access method → collector. JSON-shaped APIs share JsonApiCollector via presets."""

from news_insight.collect.contracts import Collector
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

JSON_METHODS = frozenset(
    {
        AccessMethod.JSON_API,
        AccessMethod.GITHUB,
        AccessMethod.ATPROTO,
        AccessMethod.ACTIVITYPUB,
        AccessMethod.RESEARCH_API,
    }
)
SUPPORTED_METHODS = frozenset({AccessMethod.FEED, AccessMethod.CRAWLER} | JSON_METHODS)


def collector_for(method: AccessMethod, fetcher: SafeFetcher) -> Collector:
    if method is AccessMethod.FEED:
        return FeedCollector(fetcher)
    if method is AccessMethod.CRAWLER:
        return CrawlerCollector(fetcher)
    if method in JSON_METHODS:
        return JsonApiCollector(fetcher)
    raise ValueError(f"no collector for access method '{method.value}'")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -q`
Expected: `252 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): extend JSON mapping with fallbacks, URL templates, metrics and auth headers"
```

---

### Task 3: API 프리셋

**Files:**
- Create: `apps/api/src/news_insight/collect/presets.py`
- Modify: `apps/api/src/news_insight/sources/catalog.py` (알 수 없는 프리셋 거부)
- Test: `apps/api/tests/collect/test_presets.py`, `apps/api/tests/sources/test_catalog.py`

**Interfaces:**
- Consumes: Task 2 매핑 키
- Produces: `PRESETS: dict[str, dict[str, Any]]` — `github_search`, `github_releases`, `github_advisories`, `bluesky_author_feed`, `mastodon_timeline`, `stackexchange_questions`, `hn_algolia`, `devto_articles`, `openalex_works`, `crossref_works`, `europepmc_search`; `effective_config(config) -> dict[str, Any]` (프리셋 위에 소스 설정을 덮고, `fields`·`metrics`는 키 단위로 병합, 알 수 없으면 `ValueError`); 카탈로그 로드 시 알 수 없는 프리셋은 검증 오류

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/collect/test_presets.py`:

```python
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.presets import PRESETS, effective_config
from tests.helpers import serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

CASES: list[tuple[str, dict[str, Any], tuple[str, str, str, datetime, dict[str, int]]]] = [
    (
        "github_search",
        {
            "full_name": "alibaba/MNN",
            "html_url": "https://github.com/alibaba/MNN",
            "description": "MNN engine",
            "pushed_at": "2026-10-01T09:00:00Z",
            "owner": {"login": "alibaba"},
            "stargazers_count": 16168,
            "forks_count": 2463,
            "open_issues_count": 12,
        },
        (
            "alibaba/MNN",
            "https://github.com/alibaba/MNN",
            "alibaba/MNN",
            OCT_1_0900,
            {"stars": 16168, "forks": 2463, "open_issues": 12},
        ),
    ),
    (
        "github_releases",
        {
            "id": 7,
            "html_url": "https://github.com/o/r/releases/tag/v1.0",
            "name": "",
            "tag_name": "v1.0",
            "published_at": "2026-10-01T09:00:00Z",
        },
        ("7", "https://github.com/o/r/releases/tag/v1.0", "v1.0", OCT_1_0900, {}),
    ),
    (
        "github_advisories",
        {
            "ghsa_id": "GHSA-h46j-26q3-rggf",
            "html_url": "https://github.com/advisories/GHSA-h46j-26q3-rggf",
            "summary": "Headroom vulnerable to CSWSH",
            "published_at": "2026-10-01T09:00:00Z",
        },
        (
            "GHSA-h46j-26q3-rggf",
            "https://github.com/advisories/GHSA-h46j-26q3-rggf",
            "Headroom vulnerable to CSWSH",
            OCT_1_0900,
            {},
        ),
    ),
    (
        "bluesky_author_feed",
        {
            "post": {
                "uri": "at://did:plc:ifn/app.bsky.feed.post/3mwq",
                "author": {"handle": "aster.id"},
                "record": {"text": "The modern research ecosystem", "createdAt": "2026-10-01T09:00:00Z"},
                "likeCount": 717,
                "repostCount": 143,
                "replyCount": 16,
            }
        },
        (
            "at://did:plc:ifn/app.bsky.feed.post/3mwq",
            "https://bsky.app/profile/aster.id/post/3mwq",
            "The modern research ecosystem",
            OCT_1_0900,
            {"likes": 717, "reposts": 143, "replies": 16},
        ),
    ),
    (
        "mastodon_timeline",
        {
            "id": "117",
            "uri": "https://mastodon.social/users/m/statuses/117",
            "url": "https://mastodon.social/@m/117",
            "content": "<p>Ghost Trail feature</p>",
            "created_at": "2026-10-01T09:00:00Z",
            "account": {"acct": "m"},
            "favourites_count": 3,
            "reblogs_count": 1,
            "replies_count": 0,
        },
        (
            "https://mastodon.social/users/m/statuses/117",
            "https://mastodon.social/@m/117",
            "Ghost Trail feature",
            OCT_1_0900,
            {"favourites": 3, "reblogs": 1, "replies": 0},
        ),
    ),
    (
        "stackexchange_questions",
        {
            "question_id": 80007455,
            "link": "https://stackoverflow.com/questions/80007455/aab-size",
            "title": "Why is my AAB file 85 MB?",
            "creation_date": 1790845200,
            "owner": {"display_name": "Dawood"},
            "score": 1,
            "answer_count": 1,
            "view_count": 71,
        },
        (
            "80007455",
            "https://stackoverflow.com/questions/80007455/aab-size",
            "Why is my AAB file 85 MB?",
            OCT_1_0900,
            {"score": 1, "answers": 1, "views": 71},
        ),
    ),
    (
        "hn_algolia",
        {
            "objectID": "49941447",
            "url": None,
            "title": "Ask HN: on-device AI?",
            "created_at": "2026-10-01T09:00:00Z",
            "author": "p",
            "points": 63,
            "num_comments": 29,
        },
        (
            "49941447",
            "https://news.ycombinator.com/item?id=49941447",
            "Ask HN: on-device AI?",
            OCT_1_0900,
            {"points": 63, "comments": 29},
        ),
    ),
    (
        "devto_articles",
        {
            "id": 4786527,
            "url": "https://dev.to/dj29/hacktoberfest",
            "title": "Hacktoberfest",
            "description": "d",
            "published_at": "2026-10-01T09:00:00Z",
            "user": {"username": "dj29"},
            "positive_reactions_count": 54,
            "comments_count": 15,
        },
        (
            "4786527",
            "https://dev.to/dj29/hacktoberfest",
            "Hacktoberfest",
            OCT_1_0900,
            {"reactions": 54, "comments": 15},
        ),
    ),
    (
        "openalex_works",
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1/x",
            "display_name": "On-device inference",
            "publication_date": "2026-10-01",
            "primary_location": {"landing_page_url": "https://zenodo.org/record/1"},
            "authorships": [{"author": {"display_name": "Azuaje"}}],
            "cited_by_count": 4,
        },
        (
            "https://openalex.org/W1",
            "https://zenodo.org/record/1",
            "On-device inference",
            datetime(2026, 10, 1, tzinfo=UTC),
            {"citations": 4},
        ),
    ),
    (
        "crossref_works",
        {
            "DOI": "10.1111/sms.70378",
            "URL": "https://doi.org/10.1111/sms.70378",
            "title": ["Wearable sensing"],
            "created": {"date-time": "2026-10-01T09:00:00Z"},
            "author": [{"family": "Sprouse"}],
            "is-referenced-by-count": 0,
        },
        (
            "10.1111/sms.70378",
            "https://doi.org/10.1111/sms.70378",
            "Wearable sensing",
            OCT_1_0900,
            {"citations": 0},
        ),
    ),
    (
        "europepmc_search",
        {
            "id": "42741683",
            "source": "MED",
            "title": "AI-guided nanozyme",
            "firstPublicationDate": "2026-10-01",
            "authorString": "Yang D",
            "citedByCount": 2,
        },
        (
            "42741683",
            "https://europepmc.org/article/MED/42741683",
            "AI-guided nanozyme",
            datetime(2026, 10, 1, tzinfo=UTC),
            {"citations": 2},
        ),
    ),
]


def wrap(list_path: str, records: list[dict[str, Any]]) -> Any:
    payload: Any = records
    for part in reversed([part for part in list_path.split(".") if part]):
        payload = {part: payload}
    return payload


@pytest.mark.parametrize(("preset", "record", "expected"), CASES, ids=[case[0] for case in CASES])
def test_presets_map_real_response_shapes(
    preset: str,
    record: dict[str, Any],
    expected: tuple[str, str, str, datetime, dict[str, int]],
) -> None:
    config = effective_config({"preset": preset})
    body = json.dumps(wrap(str(config.get("list_path", "")), [record])).encode()
    context = CollectContext(endpoint_url="https://api.example.com/x", config=config, now=NOW)

    [item] = JsonApiCollector(serving(body, content_type="application/json")).collect(context).items

    assert (item.stable_id, item.url, item.title, item.published_at, item.metrics) == expected


def test_every_preset_is_covered() -> None:
    assert {case[0] for case in CASES} == set(PRESETS)


def test_source_config_overrides_and_merges_the_preset() -> None:
    config = effective_config(
        {"preset": "github_search", "item_limit": 10, "fields": {"summary": "topics.0"}}
    )

    assert config["item_limit"] == 10
    assert config["fields"]["summary"] == "topics.0"
    assert config["fields"]["url"] == "html_url"
    assert "preset" not in config


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="unknown preset 'nope'"):
        effective_config({"preset": "nope"})
```

`apps/api/tests/sources/test_catalog.py` 끝에 추가:

```python
def test_unknown_preset_is_rejected(tmp_path: Path) -> None:
    body = ENTRY + "    config:\n      preset: nope\n"

    with pytest.raises(ValidationError, match="unknown preset 'nope'"):
        load_catalog(write_catalog(tmp_path, body))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/collect/test_presets.py tests/sources/test_catalog.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_insight.collect.presets'`

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/collect/presets.py`:

```python
"""Field mappings for JSON-shaped APIs, verified against live responses (2026-10-03).

A catalog entry picks one with `config.preset`; its own keys override the preset, and
`fields` / `metrics` merge key by key.
"""

from collections.abc import Mapping
from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "github_search": {
        "list_path": "items",
        "fields": {
            "id": "full_name",
            "url": "html_url",
            "title": "full_name",
            "summary": "description",
            "published_at": "pushed_at",
            "author": "owner.login",
        },
        "metrics": {
            "stars": "stargazers_count",
            "forks": "forks_count",
            "open_issues": "open_issues_count",
        },
    },
    "github_releases": {
        "list_path": "",
        "fields": {
            "id": "id",
            "url": "html_url",
            "title": ["name", "tag_name"],
            "summary": "body",
            "published_at": "published_at",
            "author": "author.login",
        },
    },
    "github_advisories": {
        "list_path": "",
        "fields": {
            "id": "ghsa_id",
            "url": "html_url",
            "title": "summary",
            "summary": "description",
            "published_at": "published_at",
            "author": "cve_id",
        },
    },
    "bluesky_author_feed": {
        "list_path": "feed",
        "fields": {
            "id": "post.uri",
            "url": [],
            "title": "post.record.text",
            "summary": "post.record.text",
            "published_at": "post.record.createdAt",
            "author": "post.author.handle",
        },
        "url_template": "https://bsky.app/profile/{post.author.handle}/post/{post.uri|last}",
        "title_limit": 120,
        "metrics": {
            "likes": "post.likeCount",
            "reposts": "post.repostCount",
            "replies": "post.replyCount",
        },
    },
    "mastodon_timeline": {
        "list_path": "",
        "fields": {
            "id": "uri",
            "url": ["url", "uri"],
            "title": "content",
            "summary": "content",
            "published_at": "created_at",
            "author": "account.acct",
        },
        "title_limit": 120,
        "metrics": {
            "favourites": "favourites_count",
            "reblogs": "reblogs_count",
            "replies": "replies_count",
        },
    },
    "stackexchange_questions": {
        "list_path": "items",
        "fields": {
            "id": "question_id",
            "url": "link",
            "title": "title",
            "published_at": "creation_date",
            "author": "owner.display_name",
        },
        "metrics": {"score": "score", "answers": "answer_count", "views": "view_count"},
    },
    "hn_algolia": {
        "list_path": "hits",
        "fields": {
            "id": "objectID",
            "url": "url",
            "title": "title",
            "published_at": "created_at",
            "author": "author",
        },
        "url_template": "https://news.ycombinator.com/item?id={objectID}",
        "metrics": {"points": "points", "comments": "num_comments"},
    },
    "devto_articles": {
        "list_path": "",
        "fields": {
            "id": "id",
            "url": "url",
            "title": "title",
            "summary": "description",
            "published_at": "published_at",
            "author": "user.username",
        },
        "metrics": {"reactions": "positive_reactions_count", "comments": "comments_count"},
    },
    "openalex_works": {
        "list_path": "results",
        "fields": {
            "id": "id",
            "url": ["primary_location.landing_page_url", "doi", "id"],
            "title": "display_name",
            "published_at": "publication_date",
            "author": "authorships.0.author.display_name",
        },
        "metrics": {"citations": "cited_by_count"},
    },
    "crossref_works": {
        "list_path": "message.items",
        "fields": {
            "id": "DOI",
            "url": "URL",
            "title": "title.0",
            "published_at": "created.date-time",
            "author": "author.0.family",
        },
        "metrics": {"citations": "is-referenced-by-count"},
    },
    "europepmc_search": {
        "list_path": "resultList.result",
        "fields": {
            "id": "id",
            "url": [],
            "title": "title",
            "published_at": "firstPublicationDate",
            "author": "authorString",
        },
        "url_template": "https://europepmc.org/article/{source}/{id}",
        "metrics": {"citations": "citedByCount"},
    },
}


def effective_config(config: Mapping[str, Any]) -> dict[str, Any]:
    name = config.get("preset")
    if not name:
        return dict(config)
    if name not in PRESETS:
        raise ValueError(f"unknown preset '{name}'")
    base = PRESETS[str(name)]
    merged: dict[str, Any] = {**base, **{key: value for key, value in config.items() if key != "preset"}}
    merged["fields"] = {**base.get("fields", {}), **dict(config.get("fields") or {})}
    merged["metrics"] = {**base.get("metrics", {}), **dict(config.get("metrics") or {})}
    return merged
```

`apps/api/src/news_insight/sources/catalog.py`의 import 블록에 `from news_insight.collect.presets import PRESETS`를 추가하고, `CatalogEntry`의 `_absolute_http_url` 메서드 아래에 추가:

```python
    @field_validator("config")
    @classmethod
    def _known_preset(cls, value: dict[str, Any]) -> dict[str, Any]:
        preset = value.get("preset")
        if preset is not None and preset not in PRESETS:
            raise ValueError(f"unknown preset '{preset}'")
        return value
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -q`
Expected: `267 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(collect): add verified API presets for community, research and GitHub sources"
```

---

### Task 4: 반응 지표 스냅샷과 변화량

**Files:**
- Modify: `apps/api/src/news_insight/content/models.py`, `apps/api/src/news_insight/content/ingest.py`
- Create: `apps/api/migrations/versions/0005_item_metric_snapshots.py`, `apps/api/src/news_insight/content/trends.py`
- Test: `apps/api/tests/content/test_metric_snapshots.py`

**Interfaces:**
- Consumes: `RawItem.metrics` (Task 2), `Item` (Phase 2)
- Produces: `ItemMetricSnapshot(id, item_id, captured_at, metrics: dict[str, int])`; `ingest.METRIC_SNAPSHOT_INTERVAL = timedelta(hours=1)`, `IngestStats.snapshots`; `trends.Mover(item, current, baseline, delta)`, `metric_movers(session, *, metric, window, now, track=None, limit=20) -> list[Mover]` (기준값은 `now - window` 이전 마지막 스냅샷, 없으면 관측된 첫 스냅샷)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/content/test_metric_snapshots.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import ItemMetricSnapshot
from news_insight.content.trends import metric_movers
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def repo(name: str, stars: int) -> RawItem:
    return RawItem(
        stable_id=name, url=f"https://github.com/{name}", title=name, metrics={"stars": stars}
    )


def source(session: Session, **overrides: Any) -> Source:
    created = build_source(**{"key": "oss", "track": Track.OSS, **overrides})
    session.add(created)
    session.flush()
    return created


def ingest(session: Session, src: Source, items: list[RawItem], at: datetime) -> int:
    return ingest_items(session, src, items, fetch_run=None, now=at, canary=True).snapshots


def snapshots(session: Session) -> list[dict[str, int]]:
    rows = session.scalars(select(ItemMetricSnapshot).order_by(ItemMetricSnapshot.id))
    return [row.metrics for row in rows]


def test_first_sighting_records_a_snapshot(db_session: Session) -> None:
    assert ingest(db_session, source(db_session), [repo("a/b", 10)], NOW) == 1
    assert snapshots(db_session) == [{"stars": 10}]


def test_changes_within_an_hour_are_not_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 12)], NOW + timedelta(minutes=30)) == 0


def test_changes_after_an_hour_are_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 12)], NOW + timedelta(hours=2)) == 1
    assert snapshots(db_session) == [{"stars": 10}, {"stars": 12}]


def test_unchanged_values_are_not_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 10)], NOW + timedelta(hours=2)) == 0


def test_movers_rank_by_delta_over_the_window(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("fast/one", 100), repo("slow/two", 100)], NOW - timedelta(days=2))
    ingest(db_session, src, [repo("fast/one", 150), repo("slow/two", 110)], NOW - timedelta(days=1, hours=1))
    ingest(db_session, src, [repo("fast/one", 400), repo("slow/two", 120)], NOW)

    movers = metric_movers(db_session, metric="stars", window=timedelta(days=1), now=NOW)

    assert [(m.item.title, m.baseline, m.current, m.delta) for m in movers] == [
        ("fast/one", 150, 400, 250),
        ("slow/two", 110, 120, 10),
    ]


def test_movers_need_two_points_and_respect_the_track(db_session: Session) -> None:
    oss = source(db_session)
    news = source(db_session, key="news", track=Track.NEWS)
    ingest(db_session, oss, [repo("only/once", 5)], NOW)
    ingest(db_session, news, [repo("n/1", 1)], NOW - timedelta(days=2))
    ingest(db_session, news, [repo("n/1", 9)], NOW)

    assert metric_movers(db_session, metric="stars", window=timedelta(days=1), now=NOW, track=Track.OSS) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/content/test_metric_snapshots.py -q`
Expected: FAIL — `ImportError: cannot import name 'ItemMetricSnapshot'`

- [ ] **Step 3: 모델·마이그레이션 구현**

`apps/api/src/news_insight/content/models.py`의 import를 다음처럼 바꿉니다: `from typing import Any`를 추가하고, `from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, false`, `from sqlalchemy.dialects.postgresql import JSONB`. 파일 끝에 추가:

```python
class ItemMetricSnapshot(Base):
    """Engagement signals over time (stars, likes, points); deltas feed trend detection."""

    __tablename__ = "item_metric_snapshots"
    __table_args__ = (Index("ix_item_metric_snapshots_item_captured", "item_id", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
```

`apps/api/migrations/versions/0005_item_metric_snapshots.py`:

```python
"""Item metric snapshots (engagement signals over time).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_item_metric_snapshots_item_id_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_item_metric_snapshots"),
    )
    op.create_index(
        "ix_item_metric_snapshots_item_captured",
        "item_metric_snapshots",
        ["item_id", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_item_metric_snapshots_item_captured", table_name="item_metric_snapshots")
    op.drop_table("item_metric_snapshots")
```

- [ ] **Step 4: 스냅샷 기록과 변화량 구현**

`apps/api/src/news_insight/content/ingest.py`를 다음과 같이 수정합니다.

import 블록: `from datetime import datetime`를 `from datetime import datetime, timedelta`로, `from news_insight.content.models import Item, ItemRevision`를 `from news_insight.content.models import Item, ItemMetricSnapshot, ItemRevision`로 바꿉니다.

`AUTHOR_LIMIT = 300` 아래에 추가:

```python
METRIC_SNAPSHOT_INTERVAL = timedelta(hours=1)
```

`IngestStats`의 `rejected: int = 0` 아래에 `snapshots: int = 0`을, `_Prepared`의 `digest: str` 아래에 `metrics: dict[str, int]`을 추가하고, `_prepare`의 반환 생성자 마지막 인자로 `metrics=dict(raw.metrics),`를 추가합니다.

`ingest_items`의 반복문 직전에 `touched: dict[str, Item] = {}`를 추가하고, 반복문 안의 세 분기 각각에서 `item`이 확정된 직후 `touched[candidate.stable_id] = item`을 넣습니다 (새 항목은 `session.add(item)` 다음, unchanged는 `unchanged += 1` 앞, updated는 `updated += 1` 앞). 반복문 뒤의 `session.flush()` 바로 다음에 `snapshots = _record_snapshots(session, touched, prepared, now)`를 넣고, 반환하는 `IngestStats(...)`에 `snapshots=snapshots`를 추가합니다.

파일 끝에 추가:

```python
def _record_snapshots(
    session: Session, touched: dict[str, Item], prepared: dict[str, _Prepared], now: datetime
) -> int:
    """Record changed metrics at most once per METRIC_SNAPSHOT_INTERVAL per item."""
    observed = {
        touched[stable_id].id: candidate.metrics
        for stable_id, candidate in prepared.items()
        if candidate.metrics and stable_id in touched
    }
    if not observed:
        return 0
    latest = {
        snapshot.item_id: snapshot
        for snapshot in session.scalars(
            select(ItemMetricSnapshot)
            .where(ItemMetricSnapshot.item_id.in_(list(observed)))
            .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at.desc())
            .distinct(ItemMetricSnapshot.item_id)
        )
    }
    recorded = 0
    for item_id, metrics in observed.items():
        last = latest.get(item_id)
        if last is not None and (
            last.metrics == metrics or now - last.captured_at < METRIC_SNAPSHOT_INTERVAL
        ):
            continue
        session.add(ItemMetricSnapshot(item_id=item_id, captured_at=now, metrics=metrics))
        recorded += 1
    session.flush()
    return recorded
```

`apps/api/src/news_insight/content/trends.py`:

```python
"""Signal trends from metric snapshots: which items gained the most over a window."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.sources.enums import Track


@dataclass(frozen=True)
class Mover:
    item: Item
    current: int
    baseline: int
    delta: int


def metric_movers(
    session: Session,
    *,
    metric: str,
    window: timedelta,
    now: datetime,
    track: Track | None = None,
    limit: int = 20,
) -> list[Mover]:
    statement = (
        select(ItemMetricSnapshot, Item)
        .join(Item, Item.id == ItemMetricSnapshot.item_id)
        .where(ItemMetricSnapshot.captured_at <= now)
        .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at)
    )
    if track is not None:
        statement = statement.where(Item.track == track)
    series: dict[int, tuple[Item, list[tuple[datetime, int]]]] = {}
    for snapshot, item in session.execute(statement).tuples():
        value = snapshot.metrics.get(metric)
        if isinstance(value, int) and not isinstance(value, bool):
            series.setdefault(item.id, (item, []))[1].append((snapshot.captured_at, value))
    cutoff = now - window
    movers: list[Mover] = []
    for item, points in series.values():
        if len(points) < 2:
            continue
        before = [value for captured, value in points if captured <= cutoff]
        baseline = before[-1] if before else points[0][1]
        current = points[-1][1]
        movers.append(Mover(item=item, current=current, baseline=baseline, delta=current - baseline))
    movers.sort(key=lambda mover: mover.delta, reverse=True)
    return movers[:limit]
```

- [ ] **Step 5: 테스트 통과와 마이그레이션 확인**

Run: `cd apps/api && uv run pytest -q && uv run alembic upgrade head && uv run alembic check && uv run alembic downgrade 0004 && uv run alembic upgrade head`
Expected: `273 passed`, `No new upgrade operations detected.`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(content): snapshot engagement metrics and compute movers"
```

---

### Task 5: 통일된 V3 사전 점검과 수집 컨텍스트

**Files:**
- Create: `apps/api/src/news_insight/net/mime.py`, `apps/api/src/news_insight/collect/context.py`
- Modify: `apps/api/src/news_insight/sources/checks.py`, `collect/feed.py`, `collect/json_api.py`, `collect/crawler.py`, `collect/service.py`
- Test: `apps/api/tests/sources/test_checks_parser.py`, `apps/api/tests/collect/test_service.py`

**Interfaces:**
- Consumes: Task 1~3
- Produces: `net.mime.FEED_MIME`, `JSON_MIME`, `HTML_MIME`, `EXPECTED_MIME` (기존 `sources.checks` 이름은 `EXPECTED_MIME`·`FEED_MIME`만 유지); `collect_context(source, *, now, etag=None, last_modified=None, last_success_at=None) -> CollectContext` (프리셋 반영 + 인증 헤더, 실패 시 `SecretError`/`ValueError`); `checks.probe_items(items, *, now, min_items=3, max_age_days=30) -> CheckResult`; V2는 URL의 날짜 매크로를 전개한 뒤 요청; V3는 Feed는 기존 방식, 나머지는 실제 수집기로 판정; `collect_source`는 자격 증명·프리셋 오류를 `config_error`로 기록하고 소스를 일시정지

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_checks_parser.py`에서 `test_non_feed_access_methods_fail_closed`를 지우고, import 블록에 `import json`, `import pytest`, `from typing import Any`, `from tests.helpers import serving`을 추가한 뒤 끝에 추가:

```python
def json_source(**config: Any) -> Any:
    return build_source(
        access_method=AccessMethod.JSON_API,
        endpoint_url="https://www.example.com/api",
        config={"list_path": "items", **config},
    )


def json_fetcher(*dates: str | None) -> SafeFetcher:
    records = [
        {"id": n, "url": f"https://www.example.com/{n}", "title": f"T{n}", "published_at": date}
        for n, date in enumerate(dates)
    ]
    return serving(json.dumps({"items": records}).encode(), content_type="application/json")


def test_json_sources_are_probed_through_their_collector() -> None:
    fetcher = json_fetcher(*["2026-10-01T09:00:00Z"] * 3)

    result = check_parser(json_source(), fetcher, now=NOW)

    assert result.passed, result.reasons
    assert result.metrics == {"items": 3, "dated": 3, "recent": 3}


def test_json_probe_requires_recent_dated_items() -> None:
    fetcher = json_fetcher("2026-10-01T09:00:00Z", None, "2026-01-01T00:00:00Z")

    result = check_parser(json_source(), fetcher, now=NOW)

    assert result.reasons == ["only 1 recent complete items (need 3)"]


def test_probe_reports_collector_errors() -> None:
    result = check_parser(json_source(list_path="missing"), json_fetcher("x"), now=NOW)

    assert result.reasons[0].startswith("selector_drift")


def test_probe_reports_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_SECRET_GITHUB_TOKEN", raising=False)
    source = json_source(auth={"secret": "GITHUB_TOKEN"})

    result = check_parser(source, json_fetcher(), now=NOW)

    assert "credential SOURCE_SECRET_GITHUB_TOKEN is not configured" in result.reasons
```

`apps/api/tests/collect/test_service.py` 끝에 추가:

```python
def test_missing_credentials_pause_the_source(
    db_session: Session, fetcher: SafeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE_SECRET_GITHUB_TOKEN", raising=False)
    source = collectable(db_session, config={"auth": {"secret": "GITHUB_TOKEN"}})
    stub = StubCollector()

    run = collect(db_session, source, stub, fetcher)

    assert (run.outcome, run.error_code) == (FetchOutcome.DEAD_LETTERED, "config_error")
    assert source.status is SourceStatus.PAUSED
    assert stub.contexts == []


def test_collectors_receive_preset_config_and_credentials(
    db_session: Session, fetcher: SafeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_SECRET_GITHUB_TOKEN", "t0k")
    source = collectable(
        db_session, config={"preset": "github_search", "auth": {"secret": "GITHUB_TOKEN"}}
    )
    stub = StubCollector(ok(raw(1)))

    collect(db_session, source, stub, fetcher)

    assert stub.contexts[0].config["list_path"] == "items"
    assert stub.contexts[0].headers == {"Authorization": "Bearer t0k"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_checks_parser.py tests/collect/test_service.py -q`
Expected: FAIL — JSON 소스 V3가 `no V3 parser probe` 사유로 실패, 서비스 테스트 assertion 실패

- [ ] **Step 3: MIME 상수 이동 (순환 import 방지)**

`apps/api/src/news_insight/net/mime.py`:

```python
"""Content types each access method may return; shared by V2 checks and collectors."""

from news_insight.sources.enums import AccessMethod

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
HTML_MIME = frozenset({"text/html", "application/xhtml+xml"})
EXPECTED_MIME: dict[AccessMethod, frozenset[str]] = {
    AccessMethod.FEED: FEED_MIME,
    AccessMethod.JSON_API: JSON_MIME,
    AccessMethod.CRAWLER: HTML_MIME,
    AccessMethod.GITHUB: JSON_MIME,
    AccessMethod.ATPROTO: JSON_MIME,
    AccessMethod.ACTIVITYPUB: JSON_MIME,
    AccessMethod.RESEARCH_API: JSON_MIME | FEED_MIME,
}
```

`apps/api/src/news_insight/sources/checks.py`에서 `FEED_MIME`, `JSON_MIME`, `EXPECTED_MIME` 정의 블록을 지우고 import 블록에 `from news_insight.net.mime import EXPECTED_MIME, FEED_MIME`를 추가합니다.

Run: `cd apps/api && sed -i '' 's/from news_insight.sources.checks import FEED_MIME/from news_insight.net.mime import FEED_MIME/' src/news_insight/collect/feed.py && sed -i '' 's/from news_insight.sources.checks import JSON_MIME/from news_insight.net.mime import JSON_MIME/' src/news_insight/collect/json_api.py && grep -n "net.mime" src/news_insight/collect/feed.py src/news_insight/collect/json_api.py`
Expected: 각 파일에 1줄

`apps/api/src/news_insight/collect/crawler.py`에서 `from news_insight.sources.checks import EXPECTED_MIME`, `from news_insight.sources.enums import AccessMethod`, `HTML_MIME = EXPECTED_MIME[AccessMethod.CRAWLER]` 세 줄을 지우고 `from news_insight.net.mime import HTML_MIME`를 import 블록에 추가합니다.

- [ ] **Step 4: 수집 컨텍스트와 통일 V3 구현**

`apps/api/src/news_insight/collect/context.py`:

```python
"""Build the collector input for a source: preset-resolved config plus credential headers."""

from datetime import datetime

from news_insight.collect.contracts import CollectContext
from news_insight.collect.presets import effective_config
from news_insight.secrets import resolve_auth_headers
from news_insight.sources.models import Source


def collect_context(
    source: Source,
    *,
    now: datetime,
    etag: str | None = None,
    last_modified: str | None = None,
    last_success_at: datetime | None = None,
) -> CollectContext:
    """Raises SecretError (credential) or ValueError (unknown preset)."""
    return CollectContext(
        endpoint_url=source.endpoint_url,
        config=effective_config(source.config),
        now=now,
        etag=etag,
        last_modified=last_modified,
        last_success_at=last_success_at,
        headers=resolve_auth_headers(source.config),
    )
```

`apps/api/src/news_insight/sources/checks.py`의 import 블록에 다음을 추가합니다 (`collect.*`는 `sources.checks`를 import하지 않으므로 순환이 없음):

```python
from collections.abc import Sequence
from datetime import UTC, timedelta

from news_insight.collect.context import collect_context
from news_insight.collect.contracts import CollectorError, RawItem
from news_insight.collect.macros import expand_macros
from news_insight.collect.registry import collector_for
```

`check_network`의 `fetcher.fetch(probe_url(source), ...)` 호출을 다음으로 교체:

```python
        response = fetcher.fetch(
            expand_macros(probe_url(source), now=datetime.now(UTC)),
            allowed_mime=EXPECTED_MIME[source.access_method],
        )
```

`check_parser`를 다음으로 교체하고, 그 위에 `probe_items`를 추가:

```python
def probe_items(
    items: Sequence[RawItem],
    *,
    now: datetime,
    min_items: int = MIN_PROBE_ITEMS,
    max_age_days: int = 30,
) -> CheckResult:
    cutoff = now - timedelta(days=max_age_days)
    dated = [item for item in items if item.published_at is not None]
    recent = [item for item in dated if item.published_at is not None and item.published_at >= cutoff]
    reasons: list[str] = []
    if len(recent) < min_items:
        reasons.append(f"only {len(recent)} recent complete items (need {min_items})")
    return CheckResult.from_reasons(
        reasons, {"items": len(items), "dated": len(dated), "recent": len(recent)}
    )


def check_parser(source: Source, fetcher: SafeFetcher, *, now: datetime) -> CheckResult:
    """V3: one real collection must yield at least three recent, complete, dated items."""
    min_items = max(MIN_PROBE_ITEMS, int(source.config.get("probe_min_items", MIN_PROBE_ITEMS)))
    max_age_days = int(source.config.get("probe_max_age_days", 30))
    if source.access_method is AccessMethod.FEED:
        try:
            url = expand_macros(probe_url(source), now=now)
            response = fetcher.fetch(url, allowed_mime=FEED_MIME)
        except FetchError as exc:
            return CheckResult.from_reasons([str(exc)], {"error": exc.code})
        if response.status_code != 200:
            return CheckResult.from_reasons([f"unexpected HTTP status {response.status_code}"])
        return probe_feed(
            response.content, now=now, min_items=min_items, max_age_days=max_age_days
        )
    try:
        context = collect_context(source, now=now)
    except (SecretError, ValueError) as exc:
        return CheckResult.from_reasons([str(exc)], {"error": "config"})
    try:
        result = collector_for(source.access_method, fetcher).collect(context)
    except CollectorError as exc:
        return CheckResult.from_reasons([f"{exc.code}: {exc}"], {"error": exc.code})
    return probe_items(result.items, now=now, min_items=min_items, max_age_days=max_age_days)
```

`apps/api/src/news_insight/collect/service.py`를 수정합니다.
- import 블록: `from news_insight.collect.contracts import CollectContext, Collector, CollectorError`를 `from news_insight.collect.contracts import Collector, CollectorError`로 바꾸고, `from news_insight.collect.context import collect_context`와 `from news_insight.secrets import SecretError`를 추가합니다.
- `MESSAGE_LIMIT = 2000` 아래에 `PAUSING_CODES = frozenset({"selector_drift", "config_error"})`를 추가합니다.
- `context = CollectContext(...)` 블록 전체를 다음으로 교체:

```python
    try:
        context = collect_context(
            source,
            now=now,
            etag=runtime.etag,
            last_modified=runtime.last_modified,
            last_success_at=runtime.last_success_at,
        )
    except (SecretError, ValueError) as exc:
        error = CollectorError("config_error", str(exc), retryable=False)
        return _handle_failure(session, source, runtime, run, error, now)
```

- `_handle_failure`의 `pauses = ...` 줄을 다음으로 교체:

```python
    pauses = exc.code in PAUSING_CODES or exc.code.startswith("blocked_")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -q`
Expected: `278 passed`

- [ ] **Step 6: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(sources): unify V3 through real collectors and apply presets with credentials"
```

---

### Task 6: 사전 점검 · 변화량 CLI

**Files:**
- Modify: `apps/api/src/news_insight/sources/service.py`, `apps/api/src/news_insight/cli.py`
- Test: `apps/api/tests/test_cli_probe.py`

**Interfaces:**
- Consumes: `check_identity`, `check_policy`, `check_network`, `check_parser` (Task 5), `metric_movers` (Task 4), `load_catalog`
- Produces: `sources.service.probe_source(source, *, fetcher, now) -> list[tuple[ValidationStage, CheckResult]]` (V0·V1·V2·V3, DB 사용 안 함); CLI `sources probe KEY`, `sources probe-catalog [--catalog PATH] [--track TRACK]` (V1을 뺀 V0·V2·V3이 모두 통과한 수를 트랙·지역별로 요약, 하나라도 실패하면 종료 코드 1), `trends movers [--metric stars] [--days 1] [--track oss] [--limit 20]`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/test_cli_probe.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.sources.enums import Track
from tests.factories import build_source
from tests.helpers import serving
from tests.parsers.test_feed_probe import item, rss
from tests.sources.test_catalog import ENTRY, write_catalog

pytestmark = pytest.mark.db
runner = CliRunner()


def fresh_feed() -> bytes:
    now = datetime.now(UTC)
    dated = [format_datetime(now - timedelta(hours=n), usegmt=True) for n in (1, 2, 3)]
    return rss(*(item(n, date=date) for n, date in enumerate(dated, start=1)))


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_fetcher", lambda: serving(fresh_feed()))


def test_probe_catalog_reports_ready_sources(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app, ["sources", "probe-catalog", "--catalog", str(write_catalog(tmp_path, ENTRY))]
    )

    assert result.exit_code == 0, result.output
    assert "example-news" in result.output and "V0:ok V1:ok V2:ok V3:ok" in result.output
    assert "news 1/1" in result.output


def test_probe_reports_a_registered_source(db_session: Session) -> None:
    db_session.add(build_source(terms_url=None))
    db_session.flush()

    result = runner.invoke(cli.app, ["sources", "probe", "example-news"])

    assert result.exit_code == 0, result.output
    assert "V1:FAIL" in result.output and "V3:ok" in result.output


def test_trends_movers_lists_the_biggest_gains(db_session: Session) -> None:
    source = build_source(track=Track.OSS)
    db_session.add(source)
    db_session.flush()
    now = datetime.now(UTC)
    for hours, stars in ((48, 100), (0, 180)):
        repo = RawItem(stable_id="a/b", url="https://github.com/a/b", title="a/b", metrics={"stars": stars})
        ingest_items(db_session, source, [repo], fetch_run=None, now=now - timedelta(hours=hours), canary=True)

    result = runner.invoke(cli.app, ["trends", "movers", "--metric", "stars", "--track", "oss"])

    assert result.exit_code == 0, result.output
    assert "+80" in result.output and "a/b" in result.output


def test_trends_movers_explains_an_empty_result() -> None:
    result = runner.invoke(cli.app, ["trends", "movers"])

    assert "no movers yet" in result.output
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/test_cli_probe.py -q`
Expected: FAIL — `No such command 'probe-catalog'` 등 (종료 코드 2)

- [ ] **Step 3: 구현**

`apps/api/src/news_insight/sources/service.py` 끝에 추가:

```python
def probe_source(
    source: Source, *, fetcher: SafeFetcher, now: datetime
) -> list[tuple[ValidationStage, CheckResult]]:
    """Dry-run V0-V3 without touching the ladder or the database."""
    return [
        (ValidationStage.V0, check_identity(source)),
        (ValidationStage.V1, check_policy(source)),
        (ValidationStage.V2, check_network(source, fetcher)),
        (ValidationStage.V3, check_parser(source, fetcher, now=now)),
    ]
```

`apps/api/src/news_insight/cli.py`를 수정합니다.
- import 블록에 `from collections import Counter`, `from datetime import timedelta`(기존 `from datetime import UTC, datetime`를 `from datetime import UTC, datetime, timedelta`로), `from news_insight.content.trends import metric_movers`, `from news_insight.sources.enums import SourceStatus, Track`(기존 enums import에 합침), `from news_insight.sources.ladder import CheckResult`(기존 ladder import에 합침), `from news_insight.sources.service import probe_source`(기존 service import에 합침)를 추가합니다.
- `app.add_typer(dlq_app, name="dlq")` 아래에 추가:

```python
trends_app = typer.Typer(help="Signal trends from metric snapshots", no_args_is_help=True)
app.add_typer(trends_app, name="trends")
```

- 파일 끝에 추가:

```python
def _probe_line(source: Source, results: list[tuple[ValidationStage, CheckResult]]) -> str:
    marks = " ".join(f"{stage.value}:{'ok' if result.passed else 'FAIL'}" for stage, result in results)
    problems = "; ".join(
        f"{stage.value} {reason}"
        for stage, result in results
        if stage is not ValidationStage.V1
        for reason in result.reasons
    )
    line = f"{source.key:<30} {source.track.value:<11} {source.region.value:<13} {marks}"
    return f"{line} | {problems}" if problems else line


def _ready(results: list[tuple[ValidationStage, CheckResult]]) -> bool:
    return all(result.passed for stage, result in results if stage is not ValidationStage.V1)


@sources_app.command("probe")
def probe(key: str) -> None:
    """Dry-run V0-V3 for a registered source (nothing is recorded)."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            line = _probe_line(source, probe_source(source, fetcher=fetcher, now=datetime.now(UTC)))
    except SourceNotFound as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)


@sources_app.command("probe-catalog")
def probe_catalog(
    catalog: Annotated[Path, typer.Option(help="Catalog YAML path")] = DEFAULT_CATALOG_PATH,
    track: Annotated[Track | None, typer.Option(help="Only this track")] = None,
) -> None:
    """Dry-run V0, V2 and V3 for catalog entries before seeding (V1 shown for reference)."""
    entries = [entry for entry in load_catalog(catalog).sources if track is None or entry.track is track]
    totals: Counter[Track] = Counter()
    ready_tracks: Counter[Track] = Counter()
    ready_regions: Counter[str] = Counter()
    now = datetime.now(UTC)
    with _fetcher() as fetcher:
        for entry in entries:
            source = Source(
                **entry.model_dump(),
                validation_stage=ValidationStage.UNVERIFIED,
                status=SourceStatus.CANDIDATE,
            )
            results = probe_source(source, fetcher=fetcher, now=now)
            typer.echo(_probe_line(source, results))
            totals[entry.track] += 1
            if _ready(results):
                ready_tracks[entry.track] += 1
                ready_regions[entry.region.value] += 1
    typer.echo("Ready (V0+V2+V3) by track: " + ", ".join(
        f"{name.value} {ready_tracks[name]}/{totals[name]}" for name in Track if totals[name]
    ))
    typer.echo("Ready by region: " + ", ".join(f"{name} {count}" for name, count in sorted(ready_regions.items())))
    if sum(ready_tracks.values()) < len(entries):
        raise typer.Exit(code=1)


@trends_app.command("movers")
def movers(
    metric: Annotated[str, typer.Option(help="Metric key, e.g. stars, points, likes")] = "stars",
    days: Annotated[int, typer.Option(help="Window in days")] = 1,
    track: Annotated[Track | None, typer.Option(help="Only this track")] = None,
    limit: Annotated[int, typer.Option(help="Maximum rows")] = 20,
) -> None:
    """Items whose metric grew the most over the window."""
    with session_scope() as session:
        rows = metric_movers(
            session,
            metric=metric,
            window=timedelta(days=days),
            now=datetime.now(UTC),
            track=track,
            limit=limit,
        )
        lines = [f"{row.delta:+8d} {row.current:>9d}  {row.item.title}  {row.item.url}" for row in rows]
    typer.echo("\n".join(lines) if lines else "no movers yet (needs two snapshots per item)")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && uv run pytest -q`
Expected: `282 passed`

- [ ] **Step 5: 정적 검사 후 Commit**

Run: `cd apps/api && uv run ruff format . && uv run ruff check . && uv run mypy`

```bash
git add apps/api
git commit -m "feat(cli): add catalog probing and metric movers"
```

---

### Task 7: 기존 시드를 프리셋·arXiv API로 전환

**Files:**
- Modify: `apps/api/catalog/sources.yaml` (4개 항목)
- Test: `apps/api/tests/sources/test_catalog.py`

**Interfaces:**
- Consumes: Task 3 프리셋, Task 6 `probe-catalog`
- Produces: `arxiv-cs-ai`(arXiv API, Atom), `bluesky-official`(`bluesky_author_feed`), `openalex-works`(`openalex_works`, 매크로 날짜 필터), `github-on-device-ai`(`github_search`, `auth.secret: GITHUB_TOKEN`)

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/tests/sources/test_catalog.py` import에 `from news_insight.collect.presets import effective_config`를 추가하고 끝에 추가:

```python
def test_bundled_presets_resolve_and_github_declares_its_token() -> None:
    entries = {entry.key: entry for entry in load_catalog(DEFAULT_CATALOG_PATH).sources}

    for entry in entries.values():
        effective_config(entry.config)
    assert entries["github-on-device-ai"].config["auth"] == {"secret": "GITHUB_TOKEN"}
    assert entries["arxiv-cs-ai"].endpoint_url.startswith("https://export.arxiv.org/api/query")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd apps/api && uv run pytest tests/sources/test_catalog.py -q`
Expected: FAIL — `KeyError: 'auth'`

- [ ] **Step 3: 카탈로그 항목 교체**

`apps/api/catalog/sources.yaml`에서 네 항목을 다음으로 교체합니다 (나머지 키 `name`·`track`·`category`·`official_domain`·`operator`·`region`·`language`·`poll_class`·`dx_relevance`·`storage_right`는 그대로 둠).

```yaml
  - key: bluesky-official
    ...
    access_method: atproto
    endpoint_url: https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=bsky.app&limit=30
    ...
    config:
      preset: bluesky_author_feed

  - key: arxiv-cs-ai
    name: arXiv cs.AI (API)
    ...
    access_method: feed
    endpoint_url: https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=50
    ...
    (config 블록 삭제)

  - key: openalex-works
    ...
    access_method: research_api
    endpoint_url: https://api.openalex.org/works?filter=from_publication_date:{today-7d},to_publication_date:{today},title.search:on-device&sort=publication_date:desc&per-page=50
    ...
    config:
      preset: openalex_works

  - key: github-on-device-ai
    ...
    access_method: github
    endpoint_url: https://api.github.com/search/repositories?q=on-device+llm+pushed:>{today-30d}&sort=stars&order=desc&per_page=50
    ...
    config:
      preset: github_search
      auth:
        secret: GITHUB_TOKEN
      probe_url: https://api.github.com/rate_limit
```

- [ ] **Step 4: 테스트와 실제 사전 점검**

Run: `cd apps/api && uv run pytest -q`
Expected: `283 passed`

Run: `cd apps/api && uv run --env-file ../../.env news-insight sources probe-catalog`
Expected: 피드·Bluesky·OpenAlex 항목은 `V0:ok … V2:ok V3:ok`. GitHub는 토큰을 `.env`에 넣기 전까지 `V1:FAIL`과 `V3 credential … not configured`(종료 코드 1은 정상)

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat(catalog): move seeds to presets and the arXiv API"
```

---

### Task 8~11: 카탈로그 260개 확장 (트랙별)

데이터 작업이므로 코드 대신 **절차와 합격 기준**을 정의합니다. 각 태스크는 같은 절차를 따릅니다.

**절차 (트랙마다 반복)**
1. 요구사항 §2 표의 하위 범주와 지역 비율에 맞춰 후보를 고릅니다. 실제 피드·API 주소는 사이트에서 확인합니다. 추정한 주소는 넣지 않습니다.
2. `apps/api/catalog/sources.yaml`의 해당 트랙 구역에 항목을 추가합니다. 공통 규칙은 다음과 같습니다.
   - `terms_url` 생략, `storage_right: metadata_only`
   - 한국어 `dx_relevance` 10자 이상
   - 키 형식은 `<운영주체>-<범주>` (소문자·하이픈)
3. `uv run news-insight sources probe-catalog --track <track>`을 실행합니다. V0·V2·V3 중 하나라도 실패한 항목은 고치거나 뺍니다. 뺀 항목과 그 사유는 커밋 메시지에 남깁니다.
4. 트랙 목표 수를 채우면 `pytest`를 통과시킨 뒤 커밋합니다.

| Task | 트랙 | 목표 | 하위 범주 (요구사항 §2) | 주 접근 방식 |
|---|---|---:|---|---|
| 8 | `news` | 100 | 독립 테크 언론 25 · 빅테크/제조사 공식 35 · 정부/규제/표준 기관 20 · 연구기관/산업협회 20 | `feed` (일부 `crawler`는 V1 요건이 많으므로 최소화) |
| 9 | `community` | 100 | 개발자 포럼/Q&A 25 · 오픈 거버넌스 20 · 팟캐스트/뉴스레터 20 · 공식 기술 영상 20 · 탈중앙/공개 소셜 15 | `json_api`(HN Algolia·DEV·Stack Exchange 6개 이하) · `feed`(YouTube 채널 RSS·팟캐스트·뉴스레터) · `atproto` · `activitypub` |
| 10 | `research_ip` | 35 | 학술 (arXiv 카테고리별, OpenAlex·Crossref·Europe PMC 주제 쿼리) · 표준화 기구 공개 RSS | `feed` · `research_api` (특허 API는 D6에 따라 제외) |
| 11 | `oss` | 25 | DX 분야별 GitHub 검색 프로필 + 릴리스·보안 권고 | `github` (`github_search`·`github_releases`·`github_advisories`, `auth.secret: GITHUB_TOKEN`) |

**지역 배분 목표 (전체 후보 기준):** KR 65 · GLOBAL_EN 117 · JP 26 · GREATER_CHINA 21 · EU_OTHER 31. 트랙별 목표를 채우면서 지역 용량을 넘지 않게 고릅니다. 중화권과 일본은 공식 RSS가 부족할 수 있으므로, 목표에 못 미치면 부족분과 이유를 보고합니다.

**Task 11 마지막 Step: 포트폴리오 검증 테스트 추가**

`apps/api/tests/sources/test_catalog.py` 끝에 추가:

```python
def test_bundled_catalog_covers_track_targets() -> None:
    from collections import Counter

    from news_insight.sources.portfolio import TRACK_TARGETS

    counts = Counter(entry.track for entry in load_catalog(DEFAULT_CATALOG_PATH).sources)

    for track, target in TRACK_TARGETS.items():
        assert counts[track] >= target, f"{track.value}: {counts[track]}/{target}"
```

Run: `cd apps/api && uv run pytest -q`
Expected: `284 passed`

**합격 기준**
- 트랙별 후보 수가 목표 이상 (테스트로 확인)
- GitHub 토큰이 필요한 OSS 트랙을 빼고, `probe-catalog` 결과 V0·V2·V3 통과율 100%
- 지역 분포 요약을 커밋 메시지와 Phase 마무리 보고에 기록

---

### Task 12: 문서 정리

**Files:**
- Modify: `README.md`, `docs/runbooks/source-terms-review.md`

- [ ] **Step 1: README에 P3 절 추가**

`README.md` 끝에 추가:

````markdown
## 트랙 어댑터와 카탈로그 (Phase 3)

JSON API 소스는 `config.preset`으로 매핑을 고릅니다 (`github_search`, `bluesky_author_feed`, `mastodon_timeline`, `stackexchange_questions`, `hn_algolia`, `devto_articles`, `openalex_works`, `crossref_works`, `europepmc_search` 등).

```bash
cd apps/api
uv run --env-file ../../.env news-insight sources probe-catalog --track community   # 등록 전 V0·V2·V3 사전 점검
uv run news-insight sources probe <key>                                              # 등록된 소스 사전 점검
uv run news-insight trends movers --metric stars --days 1 --track oss                # 지표 상승 상위 항목
```

API 키는 카탈로그에 이름만 적고(`config.auth.secret: GITHUB_TOKEN`) 값은 `.env`의 `SOURCE_SECRET_GITHUB_TOKEN`에 둡니다.
````

- [ ] **Step 2: 런북에 자격 증명 절 추가**

`docs/runbooks/source-terms-review.md`의 "## Step 4." 바로 위에 다음 절을 추가합니다.

````markdown
## Step 3-1. (OSS 트랙) GitHub 토큰 넣기

GitHub 검색 소스는 V1에서 토큰 설정 여부까지 확인합니다.

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained token**을 만듭니다. 공개 저장소만 읽으므로 권한은 기본값(Public repositories read-only)이면 충분합니다.
2. 프로젝트 루트의 `.env`에 아래 줄을 채웁니다. 토큰을 채팅·코드·커밋에 붙여넣지 마세요.

   ```dotenv
   SOURCE_SECRET_GITHUB_TOKEN=github_pat_...
   ```

3. 로컬 CLI는 `.env`를 자동으로 읽지 않으므로 `--env-file`을 붙입니다.

   ```bash
   uv run --env-file ../../.env news-insight sources validate github-on-device-ai
   ```

4. Docker 스택(worker)은 `compose.yaml`이 같은 변수를 전달하므로 `scripts/dev.sh up`으로 다시 띄우면 적용됩니다.
````

- [ ] **Step 3: 전체 검증 후 Commit**

Run: `scripts/dev.sh verify`
Expected: 모든 단계 통과 (`284 passed`)

```bash
git add README.md docs
git commit -m "docs: describe presets, catalog probing and source credentials"
```

---

## Phase 3 완료 검증

1. `scripts/dev.sh verify` 통과, CI 통과
2. `uv run --env-file ../../.env news-insight sources probe-catalog` 실행 결과 트랙별·지역별 준비 수 기록 (OSS 트랙은 토큰을 넣은 뒤 통과)
3. 시드 소스 중 하나를 V3까지 올려 실제로 수집한 다음, `trends movers`에 결과가 나타나는지 확인 (지표가 있는 소스)
4. 다음 단계: P3.5 운영 콘솔 MVP 계획

## Self-Review 결과

- **요구사항 대비 범위:** §2 커뮤니티(HN·Stack Exchange·DEV·Bluesky·Mastodon·YouTube·팟캐스트) → Task 2·3·9, 연구(arXiv·OpenAlex·Crossref·Europe PMC·표준 기구 RSS) → Task 3·7·10, GitHub(검색·릴리스·보안 권고·Stars Delta) → Task 3·4·11. 어댑터별 V3 → Task 5. 자격 증명 → Task 1 (D11). OpenReview(D12)와 키가 필요한 특허 API(D6)는 명시적으로 제외. 기여자 활동성 지표는 GitHub 통계 API의 별도 호출이 필요해 이번 범위에서 제외하고, P4의 신호 설계 때 다시 검토
- **누락 표시 점검:** 코드 단계에는 전체 코드 또는 정확한 교체 지점이 있습니다. Task 8~11은 데이터 작업이라 절차·합격 기준·검증 명령으로 정의했습니다
- **이름 일관성:** `resolve_auth_headers(config, *, environ)`, `CollectContext.headers`, `RawItem.metrics`, `request_headers(context)`, `effective_config(config)`, `collect_context(source, *, now, …)`, `probe_items(items, *, now, …)`, `probe_source(source, *, fetcher, now)`, `metric_movers(session, *, metric, window, now, track, limit)`가 정의한 곳과 사용하는 곳에서 같은 시그니처로 쓰이는 것을 확인했습니다
- **테스트 수 누계 (Phase 2의 236개부터):** Task 1: 246 → 2: 252 → 3: 267 → 4: 273 → 5: 278 → 6: 282 → 7: 283 → 11: 284
