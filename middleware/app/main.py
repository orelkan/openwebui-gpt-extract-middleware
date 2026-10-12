"""Application factory."""

from fastapi import FastAPI

from app.config import Settings
from app.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Settings are read from the environment unless given explicitly, which lets
    tests build an app without any environment variables.
    """
    app = FastAPI(title="GPT Extract Middleware")
    app.state.settings = settings or Settings()
    app.include_router(health.router)
    return app
