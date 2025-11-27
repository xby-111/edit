from datetime import datetime
import json
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.api.admin_deps import require_admin
from app.services.audit_service import log_action
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix=f"{settings.API_V1_STR}/admin", tags=["系统管理"])


def _parse_iso(value: str):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式无效")


class RoleUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]):
        if v is None:
            return v
        if v not in {"admin", "user", "editor", "viewer"}:
            raise ValueError("角色必须是 admin/user/editor/viewer")
        return v


@router.get("/users")
def list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    conditions: List[str] = []
    params: List[Any] = []

    if q:
        conditions.append("(username ILIKE %s OR email ILIKE %s OR phone ILIKE %s)")
        like_keyword = f"%{q}%"
        params.extend([like_keyword, like_keyword, like_keyword])

    if role:
        if role not in {"admin", "user", "editor", "viewer"}:
            raise HTTPException(status_code=400, detail="角色参数无效")
        conditions.append("role = %s")
        params.append(role)

    if page is not None:
        offset = (page - 1) * limit

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    total_result = db.query(f"SELECT COUNT(*) FROM users{where_sql}", tuple(params))
    total = total_result[0][0] if total_result else 0

    rows = db.query(
        f"""
        SELECT id, username, email, phone, role, is_active, created_at, NULL as last_login_at
        FROM users
        {where_sql}
        ORDER BY id
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    items = [
        {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "phone": row[3],
            "role": row[4],
            "is_active": row[5],
            "created_at": row[6],
            "last_login_at": row[7],
        }
        for row in rows
    ]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    rows = db.query(
        "SELECT id, username, email, role, created_at FROM users WHERE id = %s",
        (user_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="用户不存在")

    row = rows[0]
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "role": row[3],
        "created_at": row[4],
    }


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: RoleUpdate,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    if user_id == getattr(current_admin, "id", None) and payload.role is not None and payload.role != "admin":
        raise HTTPException(status_code=400, detail="不能将自己降级为非管理员")

    update_result = db.query("SELECT id FROM users WHERE id = %s", (user_id,))
    if not update_result:
        raise HTTPException(status_code=404, detail="用户不存在")

    updates = []
    params: List[Any] = []
    if payload.role is not None:
        updates.append("role = %s")
        params.append(payload.role)
    if payload.is_active is not None:
        updates.append("is_active = %s")
        params.append(payload.is_active)
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    params.append(user_id)
    db.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
        tuple(params),
    )

    try:
        log_action(
            db,
            user_id=getattr(current_admin, "id", None),
            action="admin.user.role.update",
            resource_type="user",
            resource_id=user_id,
            meta={"role": payload.role, "is_active": payload.is_active},
        )
    except Exception:
        pass

    rows = db.query(
        "SELECT id, username, email, role, created_at FROM users WHERE id = %s",
        (user_id,),
    )
    row = rows[0]
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "role": row[3],
        "created_at": row[4],
    }


@router.get("/audit")
def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    conditions: List[str] = []
    params: List[Any] = []

    if user_id is not None:
        conditions.append("user_id = %s")
        params.append(user_id)
    if action:
        conditions.append("action = %s")
        params.append(action)
    if date_from:
        conditions.append("created_at >= %s")
        params.append(_parse_iso(date_from))
    if date_to:
        conditions.append("created_at <= %s")
        params.append(_parse_iso(date_to))

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    total_result = db.query(f"SELECT COUNT(*) FROM audit_logs{where_sql}", tuple(params))
    total = total_result[0][0] if total_result else 0

    rows = db.query(
        f"""
        SELECT id, user_id, action, resource_type, resource_id, ip, user_agent, meta_json, created_at
        FROM audit_logs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    items = [
        {
            "id": row[0],
            "user_id": row[1],
            "action": row[2],
            "resource_type": row[3],
            "resource_id": row[4],
            "ip": row[5],
            "user_agent": row[6],
            "meta": json.loads(row[7]) if row[7] else None,
            "created_at": row[8],
        }
        for row in rows
    ]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/audit/summary")
def audit_summary(
    bucket: str = Query("day"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    action: Optional[str] = None,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    if bucket != "day":
        raise HTTPException(status_code=400, detail="仅支持按天聚合")

    conditions: List[str] = []
    params: List[Any] = []

    if date_from:
        conditions.append("created_at >= %s")
        params.append(_parse_iso(date_from))
    if date_to:
        conditions.append("created_at <= %s")
        params.append(_parse_iso(date_to))
    if action:
        conditions.append("action = %s")
        params.append(action)

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = db.query(
        f"""
        SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS bucket, COUNT(*)
        FROM audit_logs
        {where_sql}
        GROUP BY bucket
        ORDER BY bucket
        """,
        tuple(params),
    )

    items = [
        {"bucket": row[0], "count": row[1]}
        for row in rows
    ]

    return {"items": items}


@router.get("/user-events/summary")
def user_events_summary(
    start: Optional[str] = None,
    end: Optional[str] = None,
    user_id: Optional[int] = None,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    conditions: List[str] = []
    params: List[Any] = []
    if start:
        conditions.append("created_at >= %s")
        params.append(_parse_iso(start))
    if end:
        conditions.append("created_at <= %s")
        params.append(_parse_iso(end))
    if user_id is not None:
        conditions.append("user_id = %s")
        params.append(user_id)

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.query(
        f"""
        SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS bucket, event_type, COUNT(*)
        FROM user_events
        {where_sql}
        GROUP BY bucket, event_type
        ORDER BY bucket, event_type
        """,
        tuple(params),
    )
    items = [
        {"bucket": row[0], "event_type": row[1], "count": row[2]}
        for row in rows
    ]
    try:
        log_action(
            db,
            user_id=getattr(current_admin, "id", None),
            action="admin.user_events.summary",
            resource_type="user_events",
            resource_id=None,
        )
    except Exception:
        pass
    return {"items": items}


@router.get("/feedback")
def list_feedback(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    total_result = db.query("SELECT COUNT(*) FROM user_feedback", ())
    total = total_result[0][0] if total_result else 0

    rows = db.query(
        """
        SELECT id, user_id, rating, content, created_at
        FROM user_feedback
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )

    items = [
        {
            "id": row[0],
            "user_id": row[1],
            "rating": row[2],
            "content": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/surveys")
def list_surveys(
    rating: Optional[int] = Query(None, ge=1, le=5),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    conditions: List[str] = []
    params: List[Any] = []
    if rating is not None:
        conditions.append("rating = %s")
        params.append(rating)

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    total_result = db.query(f"SELECT COUNT(*) FROM satisfaction_surveys{where_sql}", tuple(params))
    total = total_result[0][0] if total_result else 0
    rows = db.query(
        f"""
        SELECT id, user_id, rating, comment, created_at
        FROM satisfaction_surveys
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    items = [
        {
            "id": row[0],
            "user_id": row[1],
            "rating": row[2],
            "comment": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]
    try:
        log_action(
            db,
            user_id=getattr(current_admin, "id", None),
            action="admin.surveys.view",
            resource_type="satisfaction_surveys",
            resource_id=None,
        )
    except Exception:
        pass
    return {"items": items, "total": total, "limit": limit, "offset": offset}


class SettingUpdate(BaseModel):
    value: Any


@router.get("/settings")
def list_settings(
    prefix: Optional[str] = None,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    if prefix:
        rows = db.query(
            "SELECT key, value, updated_at FROM system_settings WHERE key LIKE %s ORDER BY key",
            (f"{prefix}%",),
        )
    else:
        rows = db.query("SELECT key, value, updated_at FROM system_settings ORDER BY key", ())

    items = []
    for row in rows:
        try:
            parsed_value = json.loads(row[1])
        except Exception:
            parsed_value = row[1]
        items.append({"key": row[0], "value": parsed_value, "updated_at": row[2]})

    return {"items": items}


@router.get("/settings/{key}")
def get_setting_detail(
    key: str,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    rows = db.query(
        "SELECT value, updated_at FROM system_settings WHERE key = %s",
        (key,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="设置不存在")
    raw_value, updated_at = rows[0]
    try:
        parsed_value = json.loads(raw_value)
    except Exception:
        parsed_value = raw_value
    return {"key": key, "value": parsed_value, "updated_at": updated_at}


@router.put("/settings/{key}")
def upsert_setting(
    key: str,
    payload: SettingUpdate,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    value_json = json.dumps(payload.value)
    
    # Check if setting exists
    existing = db.execute("SELECT \"key\" FROM system_settings WHERE \"key\" = %s", (key,)).fetchone()
    
    if existing:
        # Update existing setting
        db.execute(
            "UPDATE system_settings SET value = %s, updated_at = now() WHERE \"key\" = %s",
            (value_json, key),
        )
    else:
        # Insert new setting
        db.execute(
            "INSERT INTO system_settings (\"key\", value, updated_at) VALUES (%s, %s, now())",
            (key, value_json),
        )
    
    return {"key": key, "value": payload.value}
