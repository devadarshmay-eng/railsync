from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routers import (
    audit,
    candidates,
    health,
    incidents,
    planning,
    requests,
    speech,
    stream,
)
from app.config import settings
from app.core.safety import SAFETY_DISCLAIMER, get_safety_headers
from app.db.database import init_db


# Initialize database tables on load
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure DB tables are initialized
    init_db()
    # Warm up models once at startup to eliminate per-request cold-start latency
    try:
        from app.adapters.laya import get_laya_adapter
        adapter = get_laya_adapter()
        if hasattr(adapter, "is_loaded") and not adapter.is_loaded:
            print(f"[STARTUP] LAYA load warning: {getattr(adapter, 'load_error', None)}")
        else:
            print("[STARTUP] LAYA System 1 model loaded and warmed up.")
    except Exception as e:
        print(f"[STARTUP] LAYA warm-up notice: {e}")

    try:
        from app.adapters.asr import get_asr_adapter
        asr_adapter = get_asr_adapter()
        if hasattr(asr_adapter, "_ensure_model"):
            asr_adapter._ensure_model()
            print("[STARTUP] Local Whisper ASR engine loaded and warmed up.")
    except Exception as e:
        print(f"[STARTUP] ASR warm-up notice: {e}")

    yield
    # Shutdown logic if any


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-Assisted Railway Maintenance Block Planning System for Indian Railways.\n\n"
        "**SAFETY NOTICE**: " + SAFETY_DISCLAIMER
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for Stitch / Frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_safety_advisory_headers(request: Request, call_next):
    """Enforces Indian Railways advisory disclaimer header on every HTTP response."""
    response = await call_next(request)
    for k, v in get_safety_headers().items():
        response.headers[k] = v
    return response


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Include Routers
app.include_router(health.router)
app.include_router(requests.router)
app.include_router(planning.router)
app.include_router(candidates.router)
app.include_router(speech.router)
app.include_router(incidents.router)
app.include_router(audit.router)
app.include_router(stream.router)

# Mount static directory for frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/")
def root():
    index_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "advisory_notice": SAFETY_DISCLAIMER,
        "docs_url": "/docs",
        "status": "operational",
    }
