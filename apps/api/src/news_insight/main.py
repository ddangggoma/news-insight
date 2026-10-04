from fastapi import FastAPI

from news_insight import __version__
from news_insight.auth.routes import router as auth_router
from news_insight.console.routes import router as console_router
from news_insight.public.routes import router as public_router


def create_app() -> FastAPI:
    app = FastAPI(title="Daily IT Intelligence API", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(console_router)
    app.include_router(auth_router)
    app.include_router(public_router)
    return app


app = create_app()
