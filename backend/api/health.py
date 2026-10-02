"""Health and diagnostics API endpoints."""

from fastapi import APIRouter, Depends

from backend.config import Settings
from backend.dependencies import get_app_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(settings: Settings = Depends(get_app_settings)):
    """System health check and configuration report."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "config": settings.safe_dict(),
    }
