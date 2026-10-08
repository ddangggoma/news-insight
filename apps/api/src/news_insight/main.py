from fastapi import FastAPI

from news_insight import __version__
from news_insight.auth.account_routes import router as accounts_router
from news_insight.console.routes import router as console_router
from news_insight.observability import RequestLogMiddleware, configure_logging
from news_insight.public.routes import router as public_router


def create_app() -> FastAPI:
    configure_logging("api")
    app = FastAPI(title="Daily IT Intelligence API", version=__version__)
    app.add_middleware(RequestLogMiddleware)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(console_router)
    app.include_router(accounts_router)
    app.include_router(public_router)
    return app


app = create_app()
