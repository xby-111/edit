# 通知系统 MVP 验收指南

本指南帮助在本地以最小改动完成通知系统（REST + WebSocket）的验收闭环。

## 依赖准备
- 使用已有依赖清单（用户提供）：
  `fastapi==0.121.2, uvicorn==0.38.0, py-opengauss==1.3.10, python-dotenv==1.2.1, python-jose[cryptography]==3.5.0, passlib[bcrypt]==1.7.4, email-validator==2.3.0, anyio==4.11.0, websockets==15.0.1, pydantic-settings==2.0.3, python-multipart==0.0.12, jinja2==3.1.4, requests==2.32.5, pydantic==2.12.4, SQLAlchemy==2.0.44, psycopg2-binary==2.9.11, asyncpg==0.30.0, PyYAML==6.0.3`。
- 如需隔离环境，请使用 `python -m venv .venv` 并在其中安装上述依赖；验收脚本会检测缺失模块并提示补装。

## 数据库前提
- 连接字符串读取自环境变量 `DATABASE_URL`（默认在 `app/core/config.py` 中定义 opengauss URL）。
- 确认数据库监听端口可访问（例如 `Test-NetConnection <host> -Port <port>`）。
- `scripts/check_db.py` 会幂等地检查/创建 `notifications` 表及索引：
  - `idx_notifications_user_created`、`idx_notifications_user_unread`、`idx_notifications_user_type`。

## 服务与验收一键命令
在 PowerShell 中执行（需在仓库根目录）：

```powershell
cd /d D:\Projects\edit
.\scripts\verify_notifications_mvp.ps1
```

脚本会完成：
1. 检测/创建虚拟环境并输出已装模块；检查 `fastapi/pydantic/jose/uvicorn/py_opengauss/websockets` 是否可导入。
2. 运行 `python -m compileall app`、`python scripts/smoke_imports.py`、`python scripts/check_db.py`。
3. 后台启动 uvicorn（日志输出到 `uvicorn.log` / `uvicorn.err.log`，PID 写入 `uvicorn.pid`），轮询端口或 `/health` 直至可用。
4. 执行 REST 验收脚本 `scripts/test_notification_rest_flow.py`。
5. 执行 WS 验收脚本 `scripts/ws_notifications_smoke.py`（缺少 websockets 时会跳过并返回码 2）。
6. 最后按 `uvicorn.pid` 精确停止服务并确认 8000 端口不再监听。

## REST/WS 接口摘要
- REST 基础路径：`/api/v1`（可通过环境变量 `NOTIFY_BASE_URL` / `NOTIFY_API_PREFIX` 在脚本中重写）。
  - `GET /notifications`：分页查询（支持 `type`、`unread`）。
  - `PATCH /notifications/{id}/read`：标记单条已读。
  - `POST /notifications/read_batch`：批量已读。
- WebSocket：`/api/v1/ws/notifications?token=...`，无效 token 关闭码 1008；缺失 token 允许连接但不推送用户级通知。
- 任务创建触发点：`app/api/routers/documents.py` 的 `create_document_task` 在任务分配成功后调用 `create_notification`（type=`"task"`）。
- WS 推送格式：`{"type":"notification","data":{...通知字段...}}`，连接后会先发送 `{"type":"init","data":[...最近通知...]}`。

## 排查建议
- 服务未起：查看 `uvicorn.err.log`；确认数据库连接字符串与网络可达。
- DB 检查失败：重复执行 `python scripts/check_db.py`，确认账户权限及端口。
- REST/WS 验收失败：
  - REST：检查返回的 HTTP 码与 body；确保注册/登录接口可用。
  - WS：确认 `websockets` 模块已安装；查看脚本输出的 token/URI；验证数据库有通知入库。
- 停服后仍占用端口：查看 `uvicorn.pid` 并使用 `Stop-Process -Id <pid>`，再用 `netstat -ano | findstr :8000` 确认。
