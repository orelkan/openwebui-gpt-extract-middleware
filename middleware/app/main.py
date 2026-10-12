"""Application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.logging import configure_logging, log_event
from app.prompt import load_system_prompt
from app.routes import chat, health, models
from app.upstream import create_upstream_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the prompt and open the shared upstream client for the app's lifetime."""
    settings: Settings = app.state.settings
    app.state.system_prompt = load_system_prompt(settings.system_prompt_path)
    async with create_upstream_client(settings) as upstream_client:
        app.state.upstream_client = upstream_client
        log_event(
            logger,
            "startup_completed",
            upstream_base_url=settings.openai_base_url,
            system_prompt_chars=len(app.state.system_prompt),
        )
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Settings are read from the environment unless given explicitly, which lets
    tests build an app without any environment variables.
    """
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="GPT Extract Middleware", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    return app
