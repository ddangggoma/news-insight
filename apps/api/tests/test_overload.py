import anyio
import httpx
from fastapi import FastAPI

from news_insight.overload import OverloadGuard


def guarded_app(release: anyio.Event, *, max_inflight: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(OverloadGuard, max_inflight=max_inflight, queue_seconds=0.1)

    @app.get("/api/slow")
    async def slow() -> dict[str, bool]:
        await release.wait()
        return {"ok": True}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_requests_beyond_the_limit_get_503_with_retry_after_and_health_still_passes() -> None:
    async def scenario() -> tuple[int, int, str | None, int]:
        release = anyio.Event()
        app = guarded_app(release, max_inflight=1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            first: list[httpx.Response] = []

            async def hold() -> None:
                first.append(await client.get("/api/slow"))

            async with anyio.create_task_group() as group:
                group.start_soon(hold)
                await anyio.sleep(0.05)  # the first request now holds the only slot
                refused = await client.get("/api/slow")
                health = await client.get("/api/health")
                release.set()
            return (
                first[0].status_code,
                refused.status_code,
                refused.headers.get("retry-after"),
                health.status_code,
            )

    assert anyio.run(scenario) == (200, 503, "5", 200)


def test_a_waiting_request_gets_the_slot_once_it_frees_up() -> None:
    async def scenario() -> list[int]:
        release = anyio.Event()
        app = guarded_app(release, max_inflight=1)
        transport = httpx.ASGITransport(app=app)
        statuses: list[int] = []
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:

            async def call() -> None:
                statuses.append((await client.get("/api/slow")).status_code)

            async with anyio.create_task_group() as group:
                group.start_soon(call)
                await anyio.sleep(0.02)
                group.start_soon(call)
                await anyio.sleep(0.02)
                release.set()  # both finish well inside the 0.1 s queue wait
        return statuses

    assert anyio.run(scenario) == [200, 200]


def test_zero_turns_the_guard_off() -> None:
    async def scenario() -> list[int]:
        release = anyio.Event()
        release.set()
        app = guarded_app(release, max_inflight=0)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            return [(await client.get("/api/slow")).status_code for _ in range(3)]

    assert anyio.run(scenario) == [200, 200, 200]
