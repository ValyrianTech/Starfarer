"""
FastAPI application entry point for Starfarer: Echoes of the Void.

Creates and configures the FastAPI application, sets up the lifespan
context manager for database initialization, registers CORS middleware,
mounts static file directories, and includes the API router.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
import os

from backend.api.routes import router
from backend.multiplayer.api import router as multiplayer_router
from backend.database import init_db, run_migrations
from backend.multiplayer.database import init_multiplayer_db
from backend.config import DATA_DIR

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager for application startup and shutdown.

    On startup: initializes the SQLite database and creates required
    data directories. On shutdown: performs cleanup (currently a no-op).

    :param application: The FastAPI application instance.
    :type application: FastAPI
    :returns: An async generator that yields ``None`` during the
        application's lifetime.
    :rtype: AsyncGenerator[None, None]
    """
    init_db()
    run_migrations()
    init_multiplayer_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "save").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Starfarer: Echoes of the Void",
    description="A procedurally generated space exploration game \u2014 built by AI, for AI.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(multiplayer_router)


if os.path.isdir(FRONTEND_DIR):
    css_dir = os.path.join(FRONTEND_DIR, "css")
    if os.path.isdir(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    js_dir = os.path.join(FRONTEND_DIR, "js")
    if os.path.isdir(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/")
def index() -> Response:
    """Serve the frontend SPA or a fallback API message.

    If the frontend ``index.html`` exists, returns it as a file response.
    Otherwise returns a JSON message directing users to the API docs.

    :returns: The frontend HTML page or a JSON API message.
    :rtype: Response
    """
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Starfarer API. Visit /docs for API documentation."})
