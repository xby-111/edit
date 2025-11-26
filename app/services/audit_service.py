"""审计日志服务"""
import json
from typing import Optional


def log_action(
    conn,
    *,
    user_id: Optional[int],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    request=None,
    meta: Optional[dict] = None,
):
    """记录审计日志，异常不影响主流程。"""
    try:
        ip = None
        user_agent = None
        if request is not None:
            client = getattr(request, "client", None)
            if client:
                ip = client.host
            headers = getattr(request, "headers", None)
            if headers:
                user_agent = headers.get("user-agent")

        meta_json = json.dumps(meta) if meta is not None else None
        conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id, ip, user_agent, meta_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, action, resource_type, resource_id, ip, user_agent, meta_json),
        )
    except Exception:
        # 审计失败不阻断业务，尽量静默
        return None
