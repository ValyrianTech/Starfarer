from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.api.routes import router
from backend.database import init_db

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "save"), exist_ok=True)
    yield


app = FastAPI(
    title="Starfarer: Echoes of the Void",
    description="A procedurally generated space exploration game — built by AI, for AI.",
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


if os.path.isdir(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")


@app.get("/")
def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Starfarer API. Visit /docs for API documentation."}
