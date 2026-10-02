from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.api.routes_meetings import router as meetings_router
from app.api.routes_claims import router as claims_router
from app.api.routes_demo import router as demo_router
from app.api.routes_masking import router as masking_router
from app.api.routes_pipeline import router as pipeline_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    init_db()
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

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# Mount static web frontend
static_path = Path(__file__).resolve().parent.parent / "backend" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

from fastapi import Response

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/")
def serve_root_clay():
    clay_file = static_path / "clay.html"
    if clay_file.exists():
        return FileResponse(clay_file)
    return {
        "app": "ASCENT Clean Room",
        "status": "online",
        "web_console": "http://localhost:8000/demo",
        "clean_room": "http://localhost:8000/clean-room"
    }

@app.get("/clean-room", include_in_schema=False)
@app.get("/clay", include_in_schema=False)
def serve_clay_html():
    clay_file = static_path / "clay.html"
    if clay_file.exists():
        return FileResponse(clay_file)
    return {"error": "clay.html not found"}

@app.get("/demo", include_in_schema=False)
def serve_demo_html():
    demo_file = static_path / "demo.html"
    if demo_file.exists():
        return FileResponse(demo_file)
    return {"error": "demo.html not found"}

@app.get("/control-room", include_in_schema=False)
def serve_index_html():
    index_file = static_path / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"error": "index.html not found"}
