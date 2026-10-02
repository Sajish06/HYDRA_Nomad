"""Meetily Clean Room - Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import settings
from backend.logging import logger
from backend.storage.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info("Initializing Meetily Clean Room database schema...")
    init_db()

    # Warn loudly if unsigned webhooks are allowed
    if settings.WEBHOOK_ALLOW_UNSIGNED:
        if settings.APP_ENV == "development":
            logger.warning("SECURITY WARNING: WEBHOOK_ALLOW_UNSIGNED=true is active in development mode!")
        else:
            logger.error("CRITICAL SECURITY ERROR: Unsigned webhooks not permitted outside development!")

    yield

    logger.info("Shutting down Meetily Clean Room...")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Verification, masking, and distribution gatekeeper for meeting intelligence in M&A due diligence.",
    lifespan=lifespan,
)

# Include all API routes
from backend.api.routes import api_router

app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "docs_url": "/docs",
        "demo_url": "/demo",
    }
