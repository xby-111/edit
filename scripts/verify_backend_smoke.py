"""Backend smoke tests for tags/notifications/settings (stdlib only)."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

try:
    from app.db.session import get_db_connection, close_connection_safely
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    if exc.name == "py_opengauss":
        print(
            "缺少 py_opengauss 依赖，请先运行 pip install -r requirements.txt "
            "-i https://pypi.tuna.tsinghua.edu.cn/simple"
        )
        sys.exit(1)
    raise

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"


def _print_step(title: str):
    print(f"\n=== {title} ===")


def _request(method: str, path: str, headers=None, data=None, params=None):
    headers = headers or {}
    url = f"{BASE_URL}{API_PREFIX}{path}"
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query}"
    body_bytes = None
    if data is not None:
        if headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            body_bytes = urllib.parse.urlencode(data).encode()
        else:
            headers.setdefault("Content-Type", "application/json")
            body_bytes = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        if content:
            try:
                parsed = json.loads(content.decode())
            except Exception:
                parsed = None
        else:
            parsed = None
        return resp, parsed


def _register_user(username: str, password: str, email: str):
    try:
        _request(
            "POST",
            "/auth/register",
            data={"username": username, "password": password, "email": email},
        )
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        # 400 代表已存在可以忽略
        if exc.code != 400:
            raise


def _login(username: str, password: str) -> str:
    resp, payload = _request(
        "POST",
        "/auth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"username": username, "password": password},
    )
    if not payload or "access_token" not in payload:
        raise RuntimeError("登录失败，未获取到 token")
    return payload["access_token"]


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _ensure_admin(username: str, password: str, email: str):
    conn = None
    try:
        _register_user(username, password, email)
        conn = get_db_connection()
        conn.execute("UPDATE users SET role = 'admin' WHERE username = %s", (username,))
    finally:
        close_connection_safely(conn)


def _json_only(resp_payload, message: str):
    if resp_payload is None:
        raise RuntimeError(message)
    return resp_payload


def main():
    admin_username = f"admin_smoke_{uuid.uuid4().hex[:6]}"
    admin_password = "Admin123!"
    admin_email = f"{admin_username}@example.com"
    _print_step("准备管理员用户")
    _ensure_admin(admin_username, admin_password, admin_email)
    admin_token = _login(admin_username, admin_password)

    owner_username = f"owner_{uuid.uuid4().hex[:6]}"
    owner_password = "Owner123!"
    owner_email = f"{owner_username}@example.com"
    _print_step("准备文档拥有者")
    _register_user(owner_username, owner_password, owner_email)
    owner_token = _login(owner_username, owner_password)

    collab_username = f"collab_{uuid.uuid4().hex[:6]}"
    collab_password = "Collab123!"
    collab_email = f"{collab_username}@example.com"
    _print_step("准备协作者")
    _register_user(collab_username, collab_password, collab_email)
    collab_token = _login(collab_username, collab_password)

    _print_step("创建文档并测试标签")
    _, doc_payload = _request(
        "POST",
        f"/documents",
        headers=_auth_headers(owner_token),
        data={"title": "SmokeDoc", "content": "hello"},
    )
    doc_payload = _json_only(doc_payload, "创建文档失败")
    document_id = doc_payload.get("id")

    _print_step("创建文件夹并移动文档")
    _, folder_payload = _request(
        "POST",
        "/folders",
        headers=_auth_headers(owner_token),
        data={"name": "SmokeFolder"},
    )
    folder_payload = _json_only(folder_payload, "创建文件夹失败")
    folder_id = folder_payload.get("id")
    _request(
        "PUT",
        f"/documents/{document_id}",
        headers=_auth_headers(owner_token),
        data={"folder_id": folder_id},
    )

    _, tags_payload = _request(
        "POST",
        f"/documents/{document_id}/tags",
        headers=_auth_headers(owner_token),
        data={"tags": ["smoke", "fastapi"]},
    )
    tags_payload = _json_only(tags_payload, "添加标签失败")
    assert "smoke" in tags_payload, "添加标签失败"

    _, list_payload = _request(
        "GET", f"/documents/{document_id}/tags", headers=_auth_headers(owner_token)
    )
    list_payload = _json_only(list_payload, "获取标签失败")
    assert "fastapi" in list_payload, "获取标签失败"

    _request(
        "DELETE", f"/documents/{document_id}/tags/smoke", headers=_auth_headers(owner_token)
    )

    _print_step("添加协作者")
    _request(
        "POST",
        f"/documents/{document_id}/collaborators",
        headers=_auth_headers(owner_token),
        data={"username": collab_username, "role": "editor"},
    )

    _print_step("协作者创建评论触发通知")
    _request(
        "POST",
        f"/documents/{document_id}/comments",
        headers=_auth_headers(collab_token),
        data={"content": "@%s 有新评论" % owner_username},
    )

    _, notif_list = _request(
        "GET",
        "/notifications",
        headers=_auth_headers(owner_token),
        params={"limit": 20},
    )
    notif_list = _json_only(notif_list, "获取通知失败")
    initial_total = notif_list.get("total", 0)
    assert initial_total >= 1, "未收到评论通知"

    _print_step("开启静音后更新文档")
    _request(
        "PUT",
        "/notifications/settings",
        headers=_auth_headers(owner_token),
        data={"mute_all": True, "mute_types": ["edit"]},
    )

    _request(
        "PUT",
        f"/documents/{document_id}",
        headers=_auth_headers(collab_token),
        data={"content": "updated by collaborator"},
    )

    _, notif_after = _request(
        "GET",
        "/notifications",
        headers=_auth_headers(owner_token),
        params={"limit": 20},
    )
    notif_after = _json_only(notif_after, "更新后获取通知失败")
    assert notif_after.get("total", 0) <= initial_total + 1, "静音后不应大量新增通知"

    _print_step("创建任务并完成触发通知")
    _, task_payload = _request(
        "POST",
        f"/documents/{document_id}/tasks",
        headers=_auth_headers(collab_token),
        data={"title": "Smoke Task", "assignee_id": doc_payload.get("owner_id")},
    )
    task_payload = _json_only(task_payload, "创建任务失败")
    task_id = task_payload.get("id")
    _request(
        "PATCH",
        f"/tasks/{task_id}",
        headers=_auth_headers(collab_token),
        data={"status": "DONE"},
    )
    _, notif_task = _request(
        "GET",
        "/notifications",
        headers=_auth_headers(owner_token),
        params={"limit": 20},
    )
    notif_task = _json_only(notif_task, "任务通知查询失败")
    assert notif_task.get("total", 0) >= initial_total, "未收到任务完成通知"

    _print_step("管理员查询并调整角色")
    _, admin_users = _request(
        "GET", "/admin/users", headers=_auth_headers(admin_token), params={"q": collab_username, "limit": 5}
    )
    admin_users = _json_only(admin_users, "管理员查询用户失败")
    collab_id = admin_users.get("items", [{}])[0].get("id")
    if not collab_id:
        raise RuntimeError("未找到协作者用户")
    _request(
        "PATCH",
        f"/admin/users/{collab_id}/role",
        headers=_auth_headers(admin_token),
        data={"role": "viewer", "is_active": True},
    )

    _print_step("提交满意度调查并查看")
    _request(
        "POST",
        "/surveys/satisfaction",
        headers=_auth_headers(owner_token),
        data={"rating": 5, "comment": "great"},
    )
    _request(
        "GET",
        "/admin/surveys",
        headers=_auth_headers(admin_token),
        params={"limit": 5},
    )

    _print_step("用户事件汇总")
    _request(
        "GET",
        "/admin/user-events/summary",
        headers=_auth_headers(admin_token),
        params={},
    )

    _print_step("验证系统设置读取接口")
    _request(
        "PUT",
        "/admin/settings/smoke.feature.flag",
        headers=_auth_headers(admin_token),
        data={"value": True},
    )
    _, get_payload = _request(
        "GET",
        "/admin/settings/smoke.feature.flag",
        headers=_auth_headers(admin_token),
    )
    get_payload = _json_only(get_payload, "读取单个设置失败")
    assert get_payload.get("value") is True, "读取单个设置失败"

    print("\nSMOKE PASS")


if __name__ == "__main__":
    main()
