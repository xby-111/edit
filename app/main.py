"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.core.config import settings
from app.db.init_db import init_db
from app.api.routers import auth, users, documents, ws

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="多人协作文档编辑后端 API，支持用户注册、登录、文档管理与协同编辑。",
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialize the database before serving requests."""
    init_db()


# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["认证与登录"])
app.include_router(users.router, prefix=settings.API_V1_STR, tags=["用户管理"])
app.include_router(documents.router, prefix=settings.API_V1_STR, tags=["文档管理"])
app.include_router(ws.router, tags=["实时通信"])  # 移除前缀，直接挂载到根级别

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


@app.get("/test_collab.html", response_class=HTMLResponse)
async def read_test(request: Request) -> HTMLResponse:
    """Serve the testing page if present."""
    return templates.TemplateResponse("test_collab.html", {"request": request})

