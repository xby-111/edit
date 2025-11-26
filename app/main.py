"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
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

# 后台任务句柄，避免重复创建
_ws_cleanup_task = None
_ws_heartbeat_task = None


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize the database before serving requests."""
    global _ws_cleanup_task, _ws_heartbeat_task
    
    init_db()
    
    # 启动WebSocket死连接清理任务和心跳任务（避免重复创建）
    if _ws_cleanup_task is None or _ws_cleanup_task.done():
        _ws_cleanup_task = asyncio.create_task(ws.cleanup_task())
        print("WebSocket 清理任务已启动")
    
    if _ws_heartbeat_task is None or _ws_heartbeat_task.done():
        _ws_heartbeat_task = asyncio.create_task(ws.heartbeat_task())
        print("WebSocket 心跳任务已启动")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """优雅关闭后台任务"""
    global _ws_cleanup_task, _ws_heartbeat_task
    
    print("正在关闭后台任务...")
    
    # 取消并等待清理任务结束
    if _ws_cleanup_task and not _ws_cleanup_task.done():
        _ws_cleanup_task.cancel()
        try:
            await _ws_cleanup_task
        except asyncio.CancelledError:
            print("WebSocket 清理任务已取消")
    
    # 取消并等待心跳任务结束
    if _ws_heartbeat_task and not _ws_heartbeat_task.done():
        _ws_heartbeat_task.cancel()
        try:
            await _ws_heartbeat_task
        except asyncio.CancelledError:
            print("WebSocket 心跳任务已取消")
    
    print("后台任务已全部关闭")


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

