"""
通知 WebSocket 实时推送验收脚本。

流程：
1. 注册两名用户并登录获取 token。
2. 使用用户1连接通知 WS，用户2连接验证权限隔离。
3. 通过 HTTP 创建文档与任务（指派给用户1）。
4. 确认用户1 WS 收到通知，用户2 未收到。

退出码：成功 0，失败 1，未安装 websockets 时返回 2（跳过）。
"""
import asyncio
import json
import os
import sys
import uuid
from typing import Dict, Optional
from urllib import request, parse, error

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print("websockets 未安装，跳过 WS 验收")
    sys.exit(2)

BASE_HTTP = os.environ.get("NOTIFY_BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = os.environ.get("NOTIFY_API_PREFIX", "/api/v1")
BASE_HTTP_API = f"{BASE_HTTP.rstrip('/')}{API_PREFIX}"
BASE_WS = os.environ.get("NOTIFY_WS_URL", f"ws://127.0.0.1:8000{API_PREFIX}/ws/notifications")


def _http_request(path: str, method: str = "GET", data: Optional[dict] = None, token: Optional[str] = None) -> Dict:
    url = f"{BASE_HTTP_API}{path}"
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode()
        return json.loads(content) if content else {}


def _login(username: str, password: str) -> str:
    url = f"{BASE_HTTP_API}/auth/token"
    form = parse.urlencode({"username": username, "password": password}).encode()
    req = request.Request(url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        return data.get("access_token", "")


def _register_user(prefix: str, password: str) -> Dict:
    suffix = uuid.uuid4().hex[:6]
    username = f"{prefix}_{suffix}"
    payload = {"username": username, "password": password, "email": f"{username}@example.com"}
    user = _http_request("/auth/register", "POST", data=payload)
    token = _login(username, payload["password"])
    return {"id": user.get("id"), "username": username, "token": token}


async def _drain_init(ws):
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=1)
        data = json.loads(raw)
        if data.get("type") != "init":
            return data
    except (asyncio.TimeoutError, ConnectionClosed, json.JSONDecodeError):
        return None
    return None


async def _wait_for_notification(ws, task_id: int, timeout: int = 5) -> Optional[Dict]:
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        remaining = end_time - asyncio.get_event_loop().time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            data = json.loads(raw)
            if data.get("type") == "notification":
                payload = (data.get("data") or {}).get("payload") or {}
                if isinstance(payload, dict) and payload.get("task_id") == task_id:
                    return data
        except (asyncio.TimeoutError, ConnectionClosed):
            break
        except json.JSONDecodeError:
            continue
    return None


async def _ensure_no_notification(ws, task_id: int, timeout: int = 3) -> bool:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("type") == "notification":
            payload = (data.get("data") or {}).get("payload") or {}
            if isinstance(payload, dict) and payload.get("task_id") == task_id:
                print(f"❌ 非目标用户收到了 task {task_id} 通知: {data}")
                return False
    except asyncio.TimeoutError:
        return True
    except (ConnectionClosed, json.JSONDecodeError):
        return True
    return True


async def main() -> int:
    try:
        password = os.environ.get("NOTIFY_TEST_PASSWORD", "Test1234!")
        print("[1] 注册用户...")
        user1 = _register_user("wsnotify1", password)
        user2 = _register_user("wsnotify2", password)
        if not user1.get("token") or not user2.get("token"):
            print("❌ 注册或登录失败")
            return 1

        print("[2] 建立 WebSocket 连接...")
        uri1 = f"{BASE_WS}?token={user1['token']}"
        uri2 = f"{BASE_WS}?token={user2['token']}"
        async with websockets.connect(uri1) as ws1, websockets.connect(uri2) as ws2:
            await _drain_init(ws1)
            await _drain_init(ws2)

            print("[3] 创建文档与任务触发通知...")
            doc_payload = {"title": "WS Notify Doc", "content": "demo", "status": "active"}
            document = _http_request("/documents", "POST", data=doc_payload, token=user1["token"])
            document_id = document.get("id")
            if not document_id:
                print("❌ 文档创建失败")
                return 1

            task_payload = {"title": "WS Task", "description": "notify", "assigned_to": user1["id"]}
            task_path = f"/documents/{document_id}/tasks"
            task = _http_request(task_path, "POST", data=task_payload, token=user1["token"])
            task_id = task.get("id")
            if not task_id:
                print("❌ 任务创建失败")
                return 1

            print("[4] 等待用户1收到通知...")
            received = await _wait_for_notification(ws1, task_id)
            if not received:
                print("❌ 用户1 未在超时时间内收到通知")
                return 1
            print(f"✅ 用户1 收到通知: {received}")

            print("[5] 确认用户2 未收到该通知...")
            isolated = await _ensure_no_notification(ws2, task_id)
            if not isolated:
                return 1
            print("✅ 用户2 未收到非本人通知")

        print("✅ WebSocket 通知验证通过")
        return 0
    except error.URLError as exc:
        print(f"❌ 请求失败，可能服务未启动或地址错误: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - 诊断输出
        print(f"❌ 验证失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
