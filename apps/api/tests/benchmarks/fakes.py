"""A SafeFetcher over httpx.MockTransport for the leaderboard collectors (no network)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from news_insight.benchmarks.sources.lmarena import BOARDS
from news_insight.net.safe_fetch import SafeFetcher

FIXTURES = Path(__file__).parent / "fixtures"
HOME_HTML = (
    '<!doctype html><html><head><script defer="defer" src="/static/js/main.1e1ce12d.js">'
    "</script></head><body><div id=root></div></body></html>"
)
HTML_BODY = "<!doctype html><html><body>Sign in to continue</body></html>"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


Responder = Callable[[httpx.Request], httpx.Response]


def reply(status: int, body: str | bytes, content_type: str) -> httpx.Response:
    content = body.encode() if isinstance(body, str) else body
    return httpx.Response(status, headers={"content-type": content_type}, content=content)


class Router:
    """Routes by substring of the full URL, or the whole URL when the key starts with "="
    (first added wins); anything else is a 404."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, Responder]] = []
        self.requests: list[httpx.Request] = []

    def add(self, part: str, response: httpx.Response | Responder) -> "Router":
        responder = response if callable(response) else (lambda _r, _x=response: _x)
        self.routes.append((part, responder))
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for part, responder in self.routes:
            if (url == part[1:]) if part.startswith("=") else (part in url):
                return responder(request)
        return reply(404, "Not found", "text/plain")

    def fetcher(self) -> SafeFetcher:
        return SafeFetcher(
            client=httpx.Client(transport=httpx.MockTransport(self)),
            resolver=lambda h, p: ["93.184.216.34"],
            verify_peer=False,
        )


def deepswe_routes(router: Router, *, body: str | None = None) -> Router:
    """Both boards' JSON; `body` replaces what each answers (e.g. a page of HTML)."""
    for url, name in (
        ("deepswe.datacurve.ai/artifacts/v1.1/", "deepswe_v1_1.json"),
        ("deepswe.datacurve.ai/artifacts/v1/", "deepswe_v1.json"),
    ):
        if body is None:
            router.add(url, reply(200, fixture_text(name), "application/json"))
        else:
            router.add(url, reply(200, body, "text/html"))
    return router


def livebench_routes(router: Router, *, table: str | None = None) -> Router:
    csv_type = "text/csv; charset=utf-8"
    return (
        router.add(
            "livebench.ai/static/js/main",
            reply(200, fixture_text("livebench_main.js"), "application/javascript"),
        )
        .add(
            "livebench.ai/data/20261025/table.csv",
            reply(200, table or fixture_text("livebench_table.csv"), csv_type),
        )
        .add(
            "livebench.ai/data/20261025/cost.csv",
            reply(200, fixture_text("livebench_cost.csv"), csv_type),
        )
        .add(
            "livebench.ai/data/20261025/categories.json",
            reply(200, fixture_text("livebench_categories.json"), "application/json"),
        )
        .add(
            "livebench.ai/data/20261025/breakdown.json",
            reply(200, fixture_text("livebench_breakdown.json"), "application/json"),
        )
        .add("=https://livebench.ai/", reply(200, HOME_HTML, "text/html; charset=utf-8"))
    )


PARQUET_MIME = "application/octet-stream"
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us"


def parquet_url(board: str) -> str:
    return f"https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main/{board}/latest-00000-of-00001.parquet"


def lmarena_routes(router: Router) -> Router:
    """Each board's latest parquet: a 302 from the Hub to a CDN host, as the real one answers."""
    for board in BOARDS:
        body = (FIXTURES / f"lmarena_{board}.parquet").read_bytes()
        router.add(
            f"={parquet_url(board)}",
            httpx.Response(302, headers={"location": f"{CDN}/{board}?user_id=public"}),
        )
        router.add(f"={CDN}/{board}?user_id=public", reply(200, body, PARQUET_MIME))
    return router


def artificial_analysis_routes(router: Router, *, key: str = "test-key") -> Router:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-api-key") != key:
            return reply(401, '{"error":"unauthorized"}', "application/json")
        return reply(200, fixture_text("artificial_analysis.json"), "application/json")

    return router.add("artificialanalysis.ai/api/v2/language/models", respond)


def all_sites() -> Router:
    router = Router()
    deepswe_routes(router)
    livebench_routes(router)
    lmarena_routes(router)
    artificial_analysis_routes(router)
    return router


class FakeClock:
    """Replaces lmarena's clock and sleep: sleeping advances time, nothing really waits."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
