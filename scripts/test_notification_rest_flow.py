"""
最小通知 REST 流程验收脚本。

步骤：
1. 注册并登录获取 token。
2. 创建文档。
3. 创建任务以触发通知。
4. 拉取通知列表并校验字段。
5. 标记已读并再次确认。

退出码：成功 0，失败 1。
"""
import json
import os
import sys
import time
import uuid
from typing import Dict, Optional
from urllib import request, parse, error

BASE_URL = os.environ.get("NOTIFY_BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = os.environ.get("NOTIFY_API_PREFIX", "/api/v1")
BASE_API = f"{BASE_URL.rstrip('/')}{API_PREFIX}"


def _http_request(path: str, method: str = "GET", data: Optional[dict] = None, token: Optional[str] = None) -> Dict:
    url = f"{BASE_API}{path}"
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode()
            if content:
                return json.loads(content)
            return {}
    except error.HTTPError as exc:
        details = exc.read().decode()
        print(f"HTTP {exc.code} for {path}: {details}")
        raise
    except Exception as exc:  # pragma: no cover - 诊断打印
        print(f"请求失败 {path}: {exc}")
        raise


def _login(username: str, password: str) -> str:
    url = f"{BASE_API}/auth/token"
    form = parse.urlencode({"username": username, "password": password}).encode()
    req = request.Request(url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        return data.get("access_token", "")


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    username = os.environ.get("NOTIFY_TEST_USER", f"notify_user_{suffix}")
    password = os.environ.get("NOTIFY_TEST_PASSWORD", "Test1234!")
    email = f"{username}@example.com"

    try:
        print("[1] 注册用户...")
        user_payload = {"username": username, "password": password, "email": email}
        user = _http_request("/auth/register", "POST", data=user_payload)
        user_id = user.get("id")
        if not user_id:
            print("❌ 注册失败，未返回用户ID")
            return 1

        print("[2] 登录获取 token...")
        token = _login(username, password)
        if not token:
            print("❌ 登录失败，未获取 token")
            return 1

        print("[3] 创建文档...")
        doc_payload = {"title": f"Notify Doc {suffix}", "content": "demo", "status": "active"}
        document = _http_request("/documents", "POST", data=doc_payload, token=token)
        document_id = document.get("id")
        if not document_id:
            print("❌ 创建文档失败")
            return 1

        print("[4] 创建任务以触发通知...")
        task_payload = {"title": "Demo Task", "description": "notify", "assigned_to": user_id}
        task_path = f"/documents/{document_id}/tasks"
        task = _http_request(task_path, "POST", data=task_payload, token=token)
        task_id = task.get("id")
        if not task_id:
            print("❌ 创建任务失败")
            return 1

        print("等待通知入库...")
        time.sleep(1)

        print("[5] 查询通知列表...")
        notif_resp = _http_request("/notifications?type=task", "GET", token=token)
        items = notif_resp.get("items", []) if isinstance(notif_resp, dict) else []
        target = None
        for item in items:
            payload = item.get("payload") or {}
            if isinstance(payload, dict) and payload.get("task_id") == task_id:
                target = item
                break
        if not target:
            print(f"❌ 未找到关联任务 {task_id} 的通知，返回 {items}")
            return 1

        required_keys = ["id", "type", "title", "content", "created_at", "is_read"]
        missing = [k for k in required_keys if k not in target]
        if missing:
            print(f"❌ 通知字段缺失: {missing}")
            return 1

        notif_id = target["id"]
        print(f"找到通知 {notif_id}，开始标记已读...")
        updated = _http_request(f"/notifications/{notif_id}/read", "PATCH", token=token)
        if not updated.get("is_read"):
            print("❌ 标记已读失败")
            return 1

        print("再次确认列表状态...")
        notif_resp = _http_request("/notifications?unread=false", "GET", token=token)
        items = notif_resp.get("items", []) if isinstance(notif_resp, dict) else []
        if not any(item.get("id") == notif_id and item.get("is_read") for item in items):
            print("❌ 列表未体现已读状态")
            return 1

        print("✅ 通知 REST 流程验证通过")
        return 0
    except error.URLError as exc:
        print(f"❌ 请求失败，可能服务未启动或地址错误: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - 诊断输出
        print(f"❌ 验证失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
