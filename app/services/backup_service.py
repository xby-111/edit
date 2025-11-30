"""
数据备份服务 - 支持数据库表的导出和恢复
"""
import os
import json
import gzip
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# 备份目录
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))
BACKUP_DIR.mkdir(exist_ok=True)

# 需要备份的表
BACKUP_TABLES = [
    "users",
    "documents",
    "document_versions",
    "document_collaborators",
    "comments",
    "tasks",
    "notifications",
    "audit_logs",
    "system_settings",
    "user_feedback",
    "oauth_accounts",
    "totp_secrets",
    "verification_codes",
    "chat_messages",
]


def create_backup(
    db,
    tables: Optional[List[str]] = None,
    compress: bool = True,
) -> Dict[str, Any]:
    """
    创建数据库备份
    
    Args:
        db: 数据库连接
        tables: 要备份的表列表（默认所有表）
        compress: 是否压缩备份文件
    
    Returns:
        备份信息
    """
    tables_to_backup = tables or BACKUP_TABLES
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    
    backup_data = {
        "version": "1.0",
        "created_at": datetime.utcnow().isoformat(),
        "tables": {},
    }
    
    total_rows = 0
    
    for table in tables_to_backup:
        try:
            # 获取表结构
            columns_result = db.query(
                """
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position
                """,
                (table,)
            )
            
            if not columns_result:
                logger.warning(f"表 {table} 不存在，跳过")
                continue
            
            columns = [row[0] for row in columns_result]
            column_types = {row[0]: row[1] for row in columns_result}
            
            # 获取数据
            rows = db.query(f"SELECT * FROM {table}", ())
            
            # 转换数据
            table_data = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # 处理特殊类型
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    elif isinstance(value, bytes):
                        value = value.decode('utf-8', errors='replace')
                    row_dict[col] = value
                table_data.append(row_dict)
            
            backup_data["tables"][table] = {
                "columns": columns,
                "column_types": column_types,
                "row_count": len(table_data),
                "data": table_data,
            }
            
            total_rows += len(table_data)
            logger.info(f"已备份表 {table}: {len(table_data)} 行")
            
        except Exception as e:
            logger.error(f"备份表 {table} 失败: {e}")
            backup_data["tables"][table] = {"error": str(e)}
    
    backup_data["total_rows"] = total_rows
    
    # 保存备份文件
    if compress:
        backup_file = BACKUP_DIR / f"{backup_name}.json.gz"
        with gzip.open(backup_file, 'wt', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
    else:
        backup_file = BACKUP_DIR / f"{backup_name}.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    file_size = backup_file.stat().st_size
    
    logger.info(f"备份完成: {backup_file}, 大小: {file_size} bytes")
    
    return {
        "backup_name": backup_name,
        "file_path": str(backup_file),
        "file_size": file_size,
        "total_rows": total_rows,
        "tables_count": len([t for t in backup_data["tables"] if "error" not in backup_data["tables"].get(t, {})]),
        "created_at": backup_data["created_at"],
        "compressed": compress,
    }


def list_backups() -> List[Dict[str, Any]]:
    """列出所有备份文件"""
    backups = []
    
    for file in BACKUP_DIR.iterdir():
        if file.suffix in ['.json', '.gz']:
            try:
                stat = file.stat()
                backups.append({
                    "name": file.stem.replace('.json', ''),
                    "file_name": file.name,
                    "file_size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "compressed": file.suffix == '.gz',
                })
            except Exception as e:
                logger.warning(f"读取备份文件 {file} 信息失败: {e}")
    
    # 按时间倒序
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def get_backup_info(backup_name: str) -> Optional[Dict[str, Any]]:
    """获取备份文件详细信息"""
    # 尝试两种文件格式
    for ext in ['.json.gz', '.json']:
        file_path = BACKUP_DIR / f"{backup_name}{ext}"
        if file_path.exists():
            try:
                if ext == '.json.gz':
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                
                return {
                    "backup_name": backup_name,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "version": data.get("version"),
                    "created_at": data.get("created_at"),
                    "total_rows": data.get("total_rows", 0),
                    "tables": {
                        name: {
                            "row_count": info.get("row_count", 0) if isinstance(info, dict) else 0,
                            "error": info.get("error") if isinstance(info, dict) else None,
                        }
                        for name, info in data.get("tables", {}).items()
                    },
                }
            except Exception as e:
                logger.error(f"读取备份文件失败: {e}")
                return None
    
    return None


def restore_backup(
    db,
    backup_name: str,
    tables: Optional[List[str]] = None,
    truncate: bool = False,
) -> Dict[str, Any]:
    """
    从备份恢复数据
    
    Args:
        db: 数据库连接
        backup_name: 备份文件名
        tables: 要恢复的表列表（默认所有表）
        truncate: 是否先清空表
    
    Returns:
        恢复结果
    """
    # 加载备份文件
    backup_data = None
    for ext in ['.json.gz', '.json']:
        file_path = BACKUP_DIR / f"{backup_name}{ext}"
        if file_path.exists():
            try:
                if ext == '.json.gz':
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        backup_data = json.load(f)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        backup_data = json.load(f)
                break
            except Exception as e:
                raise ValueError(f"读取备份文件失败: {e}")
    
    if not backup_data:
        raise ValueError(f"备份文件不存在: {backup_name}")
    
    tables_to_restore = tables or list(backup_data.get("tables", {}).keys())
    
    result = {
        "backup_name": backup_name,
        "tables": {},
        "total_restored": 0,
        "errors": [],
    }
    
    for table in tables_to_restore:
        table_backup = backup_data.get("tables", {}).get(table)
        if not table_backup or "error" in table_backup:
            result["errors"].append(f"表 {table} 备份数据无效")
            continue
        
        try:
            columns = table_backup.get("columns", [])
            data = table_backup.get("data", [])
            
            if not columns or not data:
                result["tables"][table] = {"restored": 0, "status": "empty"}
                continue
            
            # 清空表（如果需要）
            if truncate:
                db.execute(f"DELETE FROM {table}")
            
            # 插入数据
            restored_count = 0
            for row in data:
                try:
                    values = [row.get(col) for col in columns]
                    placeholders = ", ".join(["%s"] * len(columns))
                    columns_str = ", ".join([f'"{col}"' for col in columns])
                    
                    db.execute(
                        f'INSERT INTO {table} ({columns_str}) VALUES ({placeholders})',
                        tuple(values)
                    )
                    restored_count += 1
                except Exception as e:
                    # 可能是主键冲突，尝试更新
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                        continue
                    logger.warning(f"恢复表 {table} 行数据失败: {e}")
            
            result["tables"][table] = {"restored": restored_count, "status": "success"}
            result["total_restored"] += restored_count
            logger.info(f"已恢复表 {table}: {restored_count} 行")
            
        except Exception as e:
            result["tables"][table] = {"restored": 0, "status": "error", "error": str(e)}
            result["errors"].append(f"恢复表 {table} 失败: {e}")
            logger.error(f"恢复表 {table} 失败: {e}")
    
    return result


def delete_backup(backup_name: str) -> bool:
    """删除备份文件"""
    for ext in ['.json.gz', '.json']:
        file_path = BACKUP_DIR / f"{backup_name}{ext}"
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"已删除备份文件: {file_path}")
                return True
            except Exception as e:
                logger.error(f"删除备份文件失败: {e}")
                return False
    
    return False


def export_table(db, table: str, format: str = "json") -> bytes:
    """
    导出单个表为指定格式
    
    Args:
        db: 数据库连接
        table: 表名
        format: 导出格式 (json, csv)
    
    Returns:
        导出的数据（字节）
    """
    # 获取表结构
    columns_result = db.query(
        """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position
        """,
        (table,)
    )
    
    if not columns_result:
        raise ValueError(f"表 {table} 不存在")
    
    columns = [row[0] for row in columns_result]
    
    # 获取数据
    rows = db.query(f"SELECT * FROM {table}", ())
    
    if format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        
        for row in rows:
            csv_row = []
            for value in row:
                if isinstance(value, datetime):
                    csv_row.append(value.isoformat())
                elif value is None:
                    csv_row.append("")
                else:
                    csv_row.append(str(value))
            writer.writerow(csv_row)
        
        return output.getvalue().encode('utf-8')
    
    else:  # json
        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if isinstance(value, datetime):
                    value = value.isoformat()
                row_dict[col] = value
            data.append(row_dict)
        
        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')


def cleanup_old_backups(keep_count: int = 10) -> int:
    """清理旧备份，只保留最近 N 个"""
    backups = list_backups()
    
    if len(backups) <= keep_count:
        return 0
    
    # 删除多余的备份
    deleted = 0
    for backup in backups[keep_count:]:
        if delete_backup(backup["name"]):
            deleted += 1
    
    logger.info(f"已清理 {deleted} 个旧备份")
    return deleted
