from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from backend.storage.database import init_db as init_backend_db
from app.api.routes_meetings import router as meetings_router
from app.api.routes_claims import router as claims_router
from app.api.routes_demo import router as demo_router
from app.api.routes_masking import router as masking_router
from app.api.routes_pipeline import router as pipeline_router
from backend.api.routes import api_router as backend_api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    init_db()
    init_backend_db()
    yield

app = FastAPI(
    title="ReqCopilot Proof",
    version="1.0.0",
    description="Deterministic local claim verification engine for meeting intelligence.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline_router)
app.include_router(demo_router)
app.include_router(meetings_router)
app.include_router(claims_router)
app.include_router(masking_router)
app.include_router(backend_api_router)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from fastapi import Response

# Mount static web frontend (only clay.html)
static_path = Path(__file__).resolve().parent.parent / "backend" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def favicon_and_devtools():
    return Response(status_code=204)

@app.get("/")
def serve_root():
    clay_file = static_path / "clay.html"
    if clay_file.exists():
        return FileResponse(clay_file)
    return {"status": "online", "app": "NOMAD Verification & Privacy Masking"}

@app.get("/demo", include_in_schema=False)
@app.get("/clean-room", include_in_schema=False)
@app.get("/control-room", include_in_schema=False)
@app.get("/clay", include_in_schema=False)
def redirect_to_root():
    return RedirectResponse(url="/", status_code=302)

