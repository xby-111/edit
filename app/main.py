"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.config import settings
from db.init_db import init_db
from api.routers import auth, users, documents, ws

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialize the database before serving requests."""
    init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=settings.API_V1_STR, tags=["users"])
app.include_router(documents.router, prefix=settings.API_V1_STR, tags=["documents"])
app.include_router(ws.router, prefix=settings.API_V1_STR, tags=["websocket"])

# Mount static files and templates
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount uploads directory for avatar access
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request) -> HTMLResponse:
    """Serve the collaborative editor front-end."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/test", response_class=HTMLResponse)
async def read_test(request: Request) -> HTMLResponse:
    """Serve the testing page if present."""
    return templates.TemplateResponse("test_collab.html", {"request": request})
