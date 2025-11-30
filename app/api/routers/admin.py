from datetime import datetime
import json
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.api.admin_deps import require_admin
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix=f"{settings.API_V1_STR}/admin", tags=["系统管理"])


def _parse_iso(value: str):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式无效")


class RoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str):
        if v not in {"admin", "user"}:
            raise ValueError("角色必须是 admin 或 user")
        return v


@router.get("/users")
def list_users(
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    conditions: List[str] = []
    params: List[Any] = []

    if keyword:
        conditions.append("(username ILIKE %s OR email ILIKE %s)")
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword])

    if role:
        if role not in {"admin", "user"}:
            raise HTTPException(status_code=400, detail="角色参数无效")
        conditions.append("role = %s")
        params.append(role)

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    total_result = db.query(f"SELECT COUNT(*) FROM users{where_sql}", tuple(params))
    total = total_result[0][0] if total_result else 0

    rows = db.query(
        f"""
        SELECT id, username, email, role, created_at
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
            "role": row[3],
            "created_at": row[4],
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
    if user_id == getattr(current_admin, "id", None) and payload.role != "admin":
        raise HTTPException(status_code=400, detail="不能将自己降级为非管理员")

    update_result = db.query("SELECT id FROM users WHERE id = %s", (user_id,))
    if not update_result:
        raise HTTPException(status_code=404, detail="用户不存在")

    db.execute(
        "UPDATE users SET role = %s WHERE id = %s",
        (payload.role, user_id),
    )

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


@router.put("/settings/{key}")
def upsert_setting(
    key: str,
    payload: SettingUpdate,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    value_json = json.dumps(payload.value)
    
    # Check if setting exists
    existing = db.query("SELECT \"key\" FROM system_settings WHERE \"key\" = %s LIMIT 1", (key,))
    
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


# ==================== 系统监控接口 ====================

from app.services.monitoring_service import (
    get_system_info,
    get_application_stats,
    get_database_stats,
    health_check,
    get_recent_metrics,
    get_metric_aggregation,
    cleanup_old_metrics,
)


@router.get("/monitoring/health", summary="健康检查", description="检查系统各组件健康状态")
def system_health_check(db=Depends(get_db)):
    """系统健康检查（无需管理员权限）"""
    return health_check(db)


@router.get("/monitoring/system", summary="系统信息", description="获取服务器系统信息")
def get_system_monitoring(
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取系统信息（CPU、内存、磁盘等）"""
    return get_system_info()


@router.get("/monitoring/application", summary="应用统计", description="获取应用运行统计")
def get_application_monitoring(
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取应用统计信息"""
    return get_application_stats(db)


@router.get("/monitoring/database", summary="数据库统计", description="获取数据库统计信息")
def get_database_monitoring(
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取数据库统计信息"""
    return get_database_stats(db)


@router.get("/monitoring/dashboard", summary="监控仪表板", description="获取综合监控数据")
def get_monitoring_dashboard(
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取综合监控数据"""
    return {
        "system": get_system_info(),
        "application": get_application_stats(db),
        "database": get_database_stats(db),
        "health": health_check(db),
    }


@router.get("/monitoring/metrics/{metric_name}", summary="获取指标数据", description="获取指定指标的历史数据")
def get_metrics_data(
    metric_name: str,
    minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取指标历史数据"""
    metrics = get_recent_metrics(db, metric_name, minutes, limit)
    return {"metric_name": metric_name, "data": metrics}


@router.get("/monitoring/metrics/{metric_name}/aggregation", summary="获取指标聚合", description="获取指标聚合统计")
def get_metrics_aggregation(
    metric_name: str,
    bucket: str = Query("hour", regex="^(minute|hour|day)$"),
    hours: int = Query(24, ge=1, le=168),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """获取指标聚合统计"""
    aggregation = get_metric_aggregation(db, metric_name, bucket, hours)
    return {"metric_name": metric_name, "bucket": bucket, "data": aggregation}


@router.post("/monitoring/cleanup", summary="清理过期数据", description="清理过期的监控指标数据")
def cleanup_monitoring_data(
    days: int = Query(30, ge=7, le=365),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """清理过期的监控数据"""
    deleted_count = cleanup_old_metrics(db, days)
    return {"message": f"已清理 {deleted_count} 条过期数据", "deleted_count": deleted_count}


# ==================== 数据备份接口 ====================

from fastapi.responses import Response
from app.services.backup_service import (
    create_backup,
    list_backups,
    get_backup_info,
    restore_backup,
    delete_backup,
    export_table,
    cleanup_old_backups,
)


class BackupRequest(BaseModel):
    tables: Optional[List[str]] = None
    compress: bool = True


class RestoreRequest(BaseModel):
    backup_name: str
    tables: Optional[List[str]] = None
    truncate: bool = False


@router.get("/backup/list", summary="列出备份", description="获取所有备份文件列表")
def list_all_backups(
    current_admin=Depends(require_admin),
):
    """列出所有备份文件"""
    backups = list_backups()
    return {"backups": backups, "count": len(backups)}


@router.post("/backup/create", summary="创建备份", description="创建数据库备份")
def create_database_backup(
    data: BackupRequest,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """创建数据库备份"""
    try:
        result = create_backup(db, tables=data.tables, compress=data.compress)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建备份失败: {e}")


@router.get("/backup/{backup_name}", summary="获取备份详情", description="获取备份文件详细信息")
def get_backup_details(
    backup_name: str,
    current_admin=Depends(require_admin),
):
    """获取备份文件详细信息"""
    info = get_backup_info(backup_name)
    if not info:
        raise HTTPException(status_code=404, detail="备份不存在")
    return info


@router.post("/backup/restore", summary="恢复备份", description="从备份恢复数据")
def restore_database_backup(
    data: RestoreRequest,
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """从备份恢复数据"""
    try:
        result = restore_backup(
            db,
            backup_name=data.backup_name,
            tables=data.tables,
            truncate=data.truncate,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复备份失败: {e}")


@router.delete("/backup/{backup_name}", summary="删除备份", description="删除指定备份文件")
def delete_database_backup(
    backup_name: str,
    current_admin=Depends(require_admin),
):
    """删除备份文件"""
    success = delete_backup(backup_name)
    if success:
        return {"message": f"备份 {backup_name} 已删除"}
    else:
        raise HTTPException(status_code=404, detail="备份不存在或删除失败")


@router.get("/backup/export/{table}", summary="导出表", description="导出单个表为JSON或CSV")
def export_single_table(
    table: str,
    format: str = Query("json", regex="^(json|csv)$"),
    db=Depends(get_db),
    current_admin=Depends(require_admin),
):
    """导出单个表"""
    try:
        data = export_table(db, table, format)
        
        media_type = "application/json" if format == "json" else "text/csv"
        filename = f"{table}.{format}"
        
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


@router.post("/backup/cleanup", summary="清理旧备份", description="只保留最近N个备份")
def cleanup_backups(
    keep_count: int = Query(10, ge=1, le=100),
    current_admin=Depends(require_admin),
):
    """清理旧备份"""
    deleted = cleanup_old_backups(keep_count)
    return {"message": f"已清理 {deleted} 个旧备份", "deleted_count": deleted}