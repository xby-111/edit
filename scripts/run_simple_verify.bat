@echo off
echo ==== 开始通知MVP验证 ====

REM 检查导入
echo [RUN] 检查关键模块导入
python scripts\check_imports_fixed.py
if %ERRORLEVEL% neq 0 (
    echo 导入检查失败
    exit /b 1
)

REM 静态检查
echo [RUN] python -m compileall app
python -m compileall app
if %ERRORLEVEL% neq 0 (
    echo 静态检查失败
    exit /b 1
)

echo [RUN] python scripts\smoke_imports.py
python scripts\smoke_imports.py
if %ERRORLEVEL% neq 0 (
    echo 导入测试失败
    exit /b 1
)

REM 数据库检查
echo [RUN] python scripts\check_db.py
python scripts\check_db.py
set DB_EXIT=%ERRORLEVEL%

REM 启动服务
echo [RUN] 后台启动uvicorn
start /b python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > uvicorn.log 2>uvicorn.err.log
echo 等待服务启动...
timeout /t 5 /nobreak >nul

REM 测试API
echo [RUN] python scripts\test_notification_rest_flow.py
python scripts\test_notification_rest_flow.py
set REST_EXIT=%ERRORLEVEL%

REM 测试WebSocket
echo [RUN] python scripts\ws_notifications_smoke.py
python scripts\ws_notifications_smoke.py
set WS_EXIT=%ERRORLEVEL%

REM 停止服务
echo [RUN] 停止uvicorn服务
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1

echo ==== 验证完成 ====
echo 数据库检查退出码: %DB_EXIT%
echo REST API退出码: %REST_EXIT%
echo WebSocket退出码: %WS_EXIT%

exit /b 0