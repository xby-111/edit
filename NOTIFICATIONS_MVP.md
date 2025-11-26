# Notifications MVP

## 范围
- 实现通知落库、查询、标记已读（单条/批量）。
- 提供 `/api/v1/ws/notifications` WebSocket 实时推送，token 缺失允许匿名，token 无效关闭 code=1008。
- 仅接入一个触发点：任务创建成功后给受让人推送通知，其余触发点留 TODO。

## TODO
- 评论、协作邀请等事件的通知触发点接入。
- WebSocket 层的更多类型（聊天、屏幕共享等）。
- 根据产品需求扩展通知类型与模板。

## 匿名策略
- REST API 使用 `get_current_user`，匿名会被 401。
- WebSocket 缺失 token 允许保持连接，但不会推送通知。

## 数据
- 表 `notifications`，索引：
  - `idx_notifications_user_created (user_id, created_at desc)`
  - `idx_notifications_user_unread (user_id, is_read, created_at desc)`
  - `idx_notifications_user_type (user_id, type, created_at desc)`

## REST
- `GET /api/v1/notifications?type=&unread=&page=&page_size=` 查询当前用户通知（匿名 401）。
- `PATCH /api/v1/notifications/{id}/read` 标记单条已读。
- `POST /api/v1/notifications/read_batch` 批量已读。
- 触发点：`POST /api/v1/documents/{document_id}/tasks` 创建任务时给受让人发送 `type=task` 通知。

## WebSocket
- `ws://127.0.0.1:8000/api/v1/ws/notifications?token=...`
- 缺失 token 允许连接但不推送；无效 token 关闭 1008。
- 消息示例：`{"type":"notification","data":{"id":1,"user_id":2,"type":"task","title":"你有新的任务","content":"Demo","payload":{"task_id":10,"document_id":5},"is_read":false,"created_at":"..."}}`

## 验收脚本
- `python scripts/check_db.py` 检查/补齐通知表与索引。
- 先后台启动 uvicorn (`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > uvicorn.log 2>&1 &`).
- `python scripts/test_notification_rest_flow.py`：注册-登录-创建任务-查询/已读全链路。
- `python scripts/ws_notifications_smoke.py`：双用户 WS 推送与隔离验证。
- 停止 uvicorn：`pkill -f "uvicorn app.main:app"`（按需）。
