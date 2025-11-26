#!/usr/bin/env python3
"""
运行说明（Linux/Windows 通用）：
1. 先启动后端服务（请后台运行，避免阻塞）：
   Linux: nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
   Windows: start /b python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1
   可用 "tail -f uvicorn.log" 或 "type uvicorn.log" 查看日志。
2. 设置 BASE_URL 环境变量（可选，默认 http://127.0.0.1:8000），然后运行本脚本：
   python scripts/verify_system_admin_mvp.py
"""
import os
import sys
import uuid
import requests

from app.db.session import get_db_connection, close_connection_safely

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"


def _print_step(title: str):
    print(f"\n=== {title} ===")


def _ensure_admin_user(username: str, password: str, email: str):
    conn = None
    try:
        conn = get_db_connection()
        # 注册用户（若已存在则忽略错误）
        resp = requests.post(
            f"{BASE_URL}{API_PREFIX}/auth/register",
            json={"username": username, "password": password, "email": email},
            timeout=10,
        )
        if resp.status_code not in (200, 400):
            resp.raise_for_status()

        # 将该用户提升为 admin
        conn.execute("UPDATE users SET role = 'admin' WHERE username = %s", (username,))
        print(f"用户 {username} 已具备 admin 角色")
    finally:
        close_connection_safely(conn)


def _login(username: str, password: str) -> str:
    resp = requests.post(
        f"{BASE_URL}{API_PREFIX}/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("登录失败，未获得 token")
    print("管理员登录成功，获取到 token")
    return token


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _create_regular_user():
    username = f"user_{uuid.uuid4().hex[:6]}"
    password = "User123!"
    email = f"{username}@example.com"
    resp = requests.post(
        f"{BASE_URL}{API_PREFIX}/auth/register",
        json={"username": username, "password": password, "email": email},
        timeout=10,
    )
    if resp.status_code not in (200, 400):
        resp.raise_for_status()
    return username, password, email


def main():
    admin_username = os.environ.get("ADMIN_USERNAME", "admin_mvp")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    admin_email = f"{admin_username}@example.com"

    _print_step("创建/登录管理员")
    _ensure_admin_user(admin_username, admin_password, admin_email)
    token = _login(admin_username, admin_password)

    _print_step("调用管理员用户列表")
    resp = requests.get(f"{BASE_URL}{API_PREFIX}/admin/users", headers=_auth_headers(token), timeout=10)
    resp.raise_for_status()
    print(f"用户总数: {resp.json().get('total')}")

    _print_step("PATCH 修改用户角色")
    normal_username, normal_password, normal_email = _create_regular_user()
    # 查找该用户 ID
    conn = get_db_connection()
    try:
        rows = conn.query("SELECT id FROM users WHERE username = %s", (normal_username,))
        target_id = rows[0][0]
    finally:
        close_connection_safely(conn)
    patch_resp = requests.patch(
        f"{BASE_URL}{API_PREFIX}/admin/users/{target_id}/role",
        headers=_auth_headers(token),
        json={"role": "admin"},
        timeout=10,
    )
    patch_resp.raise_for_status()
    print(f"已将用户 {normal_username} 角色更新为: {patch_resp.json().get('role')}")

    _print_step("创建文档/评论/任务以触发审计")
    doc_resp = requests.post(
        f"{BASE_URL}{API_PREFIX}/documents",
        headers=_auth_headers(token),
        json={"title": "MVP 测试文档", "content": "hello", "status": "active"},
        timeout=10,
    )
    doc_resp.raise_for_status()
    document_id = doc_resp.json().get("id")
    requests.post(
        f"{BASE_URL}{API_PREFIX}/documents/{document_id}/comments",
        headers=_auth_headers(token),
        json={"content": "审计评论", "line_no": 1},
        timeout=10,
    ).raise_for_status()
    requests.post(
        f"{BASE_URL}{API_PREFIX}/documents/{document_id}/tasks",
        headers=_auth_headers(token),
        json={"title": "审计任务", "description": "desc"},
        timeout=10,
    ).raise_for_status()
    requests.get(
        f"{BASE_URL}{API_PREFIX}/documents/{document_id}/export",
        headers=_auth_headers(token),
        params={"format": "html"},
        timeout=10,
    ).raise_for_status()
    print("已触发审计事件：登录/文档/评论/任务/导出")

    _print_step("查询审计日志")
    audit_resp = requests.get(
        f"{BASE_URL}{API_PREFIX}/admin/audit",
        headers=_auth_headers(token),
        params={"limit": 5},
        timeout=10,
    )
    audit_resp.raise_for_status()
    print(f"最新审计记录数: {len(audit_resp.json().get('items', []))}")

    _print_step("提交用户反馈")
    fb_resp = requests.post(
        f"{BASE_URL}{API_PREFIX}/feedback",
        headers=_auth_headers(token),
        json={"rating": 5, "content": "一切正常"},
        timeout=10,
    )
    fb_resp.raise_for_status()
    print(f"反馈创建成功，ID: {fb_resp.json().get('id')}")

    _print_step("管理员查看反馈")
    fb_list = requests.get(
        f"{BASE_URL}{API_PREFIX}/admin/feedback",
        headers=_auth_headers(token),
        params={"limit": 5},
        timeout=10,
    )
    fb_list.raise_for_status()
    print(f"反馈条数: {fb_list.json().get('total')}")

    _print_step("切换导出开关并验证")
    off_resp = requests.put(
        f"{BASE_URL}{API_PREFIX}/admin/settings/feature.export.enabled",
        headers=_auth_headers(token),
        json={"value": False},
        timeout=10,
    )
    off_resp.raise_for_status()
    blocked = requests.get(
        f"{BASE_URL}{API_PREFIX}/documents/{document_id}/export",
        headers=_auth_headers(token),
        params={"format": "html"},
        timeout=10,
    )
    if blocked.status_code != 403:
        print("⚠️ 导出关闭后期望 403，实际: ", blocked.status_code)
    else:
        print("导出开关关闭验证通过")

    # 重新打开开关
    requests.put(
        f"{BASE_URL}{API_PREFIX}/admin/settings/feature.export.enabled",
        headers=_auth_headers(token),
        json={"value": True},
        timeout=10,
    ).raise_for_status()
    reopen_resp = requests.get(
        f"{BASE_URL}{API_PREFIX}/documents/{document_id}/export",
        headers=_auth_headers(token),
        params={"format": "html"},
        timeout=10,
    )
    reopen_resp.raise_for_status()
    print("导出开关重新打开验证通过")

    print("\n验证流程完成✅")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"验证失败: {exc}")
        sys.exit(1)
