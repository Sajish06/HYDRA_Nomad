"""API route aggregator combining all module sub-routers."""

from fastapi import APIRouter

from backend.api.demo_routes import router as demo_router
from backend.api.destinations import router as destinations_router
from backend.api.health import router as health_router
from backend.api.meetings import router as meetings_router
from backend.api.review import router as review_router
from backend.api.webhooks import router as webhooks_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(meetings_router)
api_router.include_router(webhooks_router)
api_router.include_router(review_router)
api_router.include_router(destinations_router)
api_router.include_router(demo_router)
