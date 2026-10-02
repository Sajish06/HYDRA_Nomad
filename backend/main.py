"""Meetily Clean Room - Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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


# Mount static assets
static_path = Path("./backend/static")
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/demo.html", include_in_schema=False)
async def redirect_old_demo():
    return RedirectResponse(url="/demo")


@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/demo")
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "docs_url": "/docs",
        "demo_url": "/demo",
    }
