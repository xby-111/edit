"""
系统监控服务 - 收集和展示系统性能指标
"""
import os
import time
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 内存中的指标缓存（用于快速查询最近数据）
_metrics_cache: Dict[str, List[Dict]] = {}
_cache_max_size = 1000  # 每种指标最多缓存条数


def record_metric(
    db,
    *,
    metric_name: str,
    metric_value: float,
    tags: Optional[Dict[str, str]] = None,
) -> None:
    """
    记录指标到数据库
    
    Args:
        db: 数据库连接
        metric_name: 指标名称
        metric_value: 指标值
        tags: 标签（用于过滤）
    """
    tags_json = json.dumps(tags) if tags else None
    
    try:
        db.execute(
            """
            INSERT INTO system_metrics (metric_name, metric_value, tags)
            VALUES (%s, %s, %s)
            """,
            (metric_name, metric_value, tags_json)
        )
        
        # 同时写入缓存
        if metric_name not in _metrics_cache:
            _metrics_cache[metric_name] = []
        
        _metrics_cache[metric_name].append({
            "value": metric_value,
            "tags": tags,
            "ts": datetime.utcnow().isoformat(),
        })
        
        # 限制缓存大小
        if len(_metrics_cache[metric_name]) > _cache_max_size:
            _metrics_cache[metric_name] = _metrics_cache[metric_name][-_cache_max_size:]
            
    except Exception as e:
        logger.warning(f"记录指标失败: {e}")


def get_recent_metrics(
    db,
    metric_name: str,
    minutes: int = 60,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    获取最近的指标数据
    """
    since = datetime.utcnow() - timedelta(minutes=minutes)
    
    rows = db.query(
        """
        SELECT metric_value, tags, recorded_at
        FROM system_metrics
        WHERE metric_name = %s AND recorded_at >= %s
        ORDER BY recorded_at DESC
        LIMIT %s
        """,
        (metric_name, since, limit)
    )
    
    result = []
    for row in rows:
        tags = None
        if row[1]:
            try:
                tags = json.loads(row[1])
            except Exception:
                pass
        
        result.append({
            "value": row[0],
            "tags": tags,
            "recorded_at": row[2],
        })
    
    return list(reversed(result))


def get_metric_aggregation(
    db,
    metric_name: str,
    bucket: str = "hour",  # minute, hour, day
    hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    获取指标聚合统计
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # 根据 bucket 类型确定聚合粒度
    date_trunc = {
        "minute": "minute",
        "hour": "hour",
        "day": "day",
    }.get(bucket, "hour")
    
    rows = db.query(
        f"""
        SELECT 
            to_char(date_trunc('{date_trunc}', recorded_at), 'YYYY-MM-DD HH24:MI') AS bucket,
            AVG(metric_value) AS avg_value,
            MAX(metric_value) AS max_value,
            MIN(metric_value) AS min_value,
            COUNT(*) AS count
        FROM system_metrics
        WHERE metric_name = %s AND recorded_at >= %s
        GROUP BY bucket
        ORDER BY bucket
        """,
        (metric_name, since)
    )
    
    return [
        {
            "bucket": row[0],
            "avg": row[1],
            "max": row[2],
            "min": row[3],
            "count": row[4],
        }
        for row in rows
    ]


# ==================== 系统信息收集 ====================

def get_system_info() -> Dict[str, Any]:
    """获取当前系统信息"""
    import platform
    
    info = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }
    
    # 尝试获取 CPU 和内存信息
    try:
        import psutil
        
        # CPU
        info["cpu_count"] = psutil.cpu_count()
        info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        
        # 内存
        mem = psutil.virtual_memory()
        info["memory_total"] = mem.total
        info["memory_available"] = mem.available
        info["memory_percent"] = mem.percent
        
        # 磁盘
        disk = psutil.disk_usage('/')
        info["disk_total"] = disk.total
        info["disk_used"] = disk.used
        info["disk_percent"] = disk.percent
        
        # 网络
        net = psutil.net_io_counters()
        info["network_bytes_sent"] = net.bytes_sent
        info["network_bytes_recv"] = net.bytes_recv
        
    except ImportError:
        info["note"] = "安装 psutil 可获取更详细的系统信息"
    except Exception as e:
        info["error"] = str(e)
    
    return info


def get_application_stats(db) -> Dict[str, Any]:
    """获取应用统计信息"""
    stats = {}
    
    try:
        # 用户统计
        user_result = db.query("SELECT COUNT(*) FROM users", ())
        stats["total_users"] = user_result[0][0] if user_result else 0
        
        active_result = db.query(
            "SELECT COUNT(*) FROM users WHERE is_active = TRUE", ()
        )
        stats["active_users"] = active_result[0][0] if active_result else 0
        
        # 文档统计
        doc_result = db.query("SELECT COUNT(*) FROM documents", ())
        stats["total_documents"] = doc_result[0][0] if doc_result else 0
        
        # 今日活跃
        today = datetime.utcnow().date()
        today_audit = db.query(
            """
            SELECT COUNT(DISTINCT user_id) 
            FROM audit_logs 
            WHERE created_at >= %s
            """,
            (today,)
        )
        stats["today_active_users"] = today_audit[0][0] if today_audit else 0
        
        # 最近24小时请求数
        yesterday = datetime.utcnow() - timedelta(days=1)
        requests = db.query(
            """
            SELECT COUNT(*) FROM audit_logs WHERE created_at >= %s
            """,
            (yesterday,)
        )
        stats["requests_24h"] = requests[0][0] if requests else 0
        
        # WebSocket 连接数（从 ws 模块获取）
        try:
            from app.api.routers.ws import manager
            total_connections = sum(len(room) for room in manager.rooms.values())
            stats["websocket_connections"] = total_connections
        except Exception:
            stats["websocket_connections"] = 0
        
    except Exception as e:
        logger.error(f"获取应用统计失败: {e}")
        stats["error"] = str(e)
    
    return stats


def get_database_stats(db) -> Dict[str, Any]:
    """获取数据库统计信息"""
    stats = {}
    
    try:
        # 表大小统计
        tables = ["users", "documents", "comments", "tasks", "notifications", "audit_logs"]
        table_sizes = {}
        
        for table in tables:
            try:
                result = db.query(f"SELECT COUNT(*) FROM {table}", ())
                table_sizes[table] = result[0][0] if result else 0
            except Exception:
                table_sizes[table] = -1
        
        stats["table_row_counts"] = table_sizes
        
        # 数据库连接信息（OpenGauss 特定）
        try:
            conn_result = db.query(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'", ()
            )
            stats["active_connections"] = conn_result[0][0] if conn_result else 0
        except Exception:
            pass
        
    except Exception as e:
        logger.error(f"获取数据库统计失败: {e}")
        stats["error"] = str(e)
    
    return stats


# ==================== 健康检查 ====================

def health_check(db) -> Dict[str, Any]:
    """系统健康检查"""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }
    
    # 数据库检查
    try:
        db.query("SELECT 1", ())
        health["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        health["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        health["status"] = "unhealthy"
    
    # 磁盘空间检查
    try:
        import psutil
        disk = psutil.disk_usage('/')
        if disk.percent > 90:
            health["checks"]["disk"] = {
                "status": "warning",
                "message": f"磁盘使用率: {disk.percent}%"
            }
        else:
            health["checks"]["disk"] = {"status": "healthy", "usage_percent": disk.percent}
    except ImportError:
        health["checks"]["disk"] = {"status": "unknown", "message": "psutil 未安装"}
    
    # 内存检查
    try:
        import psutil
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            health["checks"]["memory"] = {
                "status": "warning",
                "message": f"内存使用率: {mem.percent}%"
            }
        else:
            health["checks"]["memory"] = {"status": "healthy", "usage_percent": mem.percent}
    except ImportError:
        health["checks"]["memory"] = {"status": "unknown", "message": "psutil 未安装"}
    
    return health


# ==================== 清理过期数据 ====================

def cleanup_old_metrics(db, days: int = 30) -> int:
    """清理过期的指标数据"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    try:
        result = db.execute(
            "DELETE FROM system_metrics WHERE recorded_at < %s",
            (cutoff,)
        )
        count = result if isinstance(result, int) else 0
        logger.info(f"已清理 {count} 条过期指标数据")
        return count
    except Exception as e:
        logger.error(f"清理过期指标失败: {e}")
        return 0
