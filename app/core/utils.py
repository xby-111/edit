"""
公共工具函数模块

提供数据库操作、格式化等常用工具函数，避免代码重复。
"""
from datetime import datetime
from typing import Optional, Any, Dict, List


# ==================== SQL 格式化工具 ====================

def escape_sql_string(value: Optional[str]) -> str:
    """
    转义 SQL 字符串值，防止 SQL 注入
    
    Args:
        value: 待转义的字符串值，可为 None
        
    Returns:
        转义后的 SQL 字符串表达式（如 'value' 或 NULL）
    
    Example:
        >>> escape_sql_string("test")
        "'test'"
        >>> escape_sql_string("it's")
        "'it''s'"
        >>> escape_sql_string(None)
        'NULL'
    """
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"


def format_sql_bool(value: Optional[bool]) -> str:
    """
    格式化布尔值为 SQL 表达式
    
    Args:
        value: 布尔值，可为 None
        
    Returns:
        SQL 布尔表达式（TRUE/FALSE/NULL）
    """
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"


def format_sql_datetime(dt: Optional[datetime]) -> str:
    """
    格式化日期时间为 SQL 字符串
    
    Args:
        dt: datetime 对象，可为 None
        
    Returns:
        SQL 日期时间字符串表达式
    
    注意：此函数仅用于拼接 SQL，参数化查询时直接传 datetime 对象
    """
    if dt is None:
        return "NULL"
    if isinstance(dt, str):
        return f"'{dt}'"
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def format_sql_int(value: Optional[int]) -> str:
    """
    格式化整数为 SQL 表达式
    
    Args:
        value: 整数值，可为 None
        
    Returns:
        SQL 整数表达式
    """
    if value is None:
        return "NULL"
    return str(int(value))


# ==================== 日期时间工具 ====================

def parse_datetime(dt_value: Any) -> Optional[datetime]:
    """
    解析数据库返回的 datetime 值（兼容多种格式）
    
    Args:
        dt_value: 待解析的值，可能是 datetime、str 或 None
        
    Returns:
        datetime 对象或 None
    """
    if dt_value is None:
        return None
    
    if isinstance(dt_value, datetime):
        return dt_value
    
    if isinstance(dt_value, str):
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(dt_value, fmt)
            except ValueError:
                continue
    
    return None


def get_utc_now() -> datetime:
    """获取当前 UTC 时间"""
    return datetime.utcnow()


# ==================== 数据库行转换工具 ====================

def row_to_dict(row: tuple, columns: List[str]) -> Dict[str, Any]:
    """
    将数据库查询结果行转换为字典
    
    Args:
        row: 数据库查询结果行（元组）
        columns: 列名列表
        
    Returns:
        包含列名和值的字典
    
    Example:
        >>> row_to_dict((1, 'test'), ['id', 'name'])
        {'id': 1, 'name': 'test'}
    """
    return dict(zip(columns, row))


# ==================== 字符串工具 ====================

def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    截断字符串到指定长度
    
    Args:
        s: 原始字符串
        max_length: 最大长度
        suffix: 截断后的后缀
        
    Returns:
        截断后的字符串
    """
    if not s or len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def is_valid_email(email: str) -> bool:
    """简单验证邮箱格式"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_phone(phone: str) -> bool:
    """验证中国手机号格式"""
    import re
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


# ==================== 向后兼容别名 ====================
# 保持与旧代码的兼容性

_escape = escape_sql_string
_format_bool = format_sql_bool
_format_datetime = format_sql_datetime
_parse_db_datetime = parse_datetime
