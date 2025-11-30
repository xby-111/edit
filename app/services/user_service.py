"""
用户服务层 - 使用 py-opengauss 直接 SQL 操作
"""
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.schemas import UserCreate
from app.core.security import get_password_hash
from app.core.utils import (
    escape_sql_string as _escape,
    format_sql_bool as _format_bool,
    format_sql_datetime as _format_datetime,
    parse_datetime as _parse_db_datetime,
)

logger = logging.getLogger(__name__)

# 用户表字段列表
USER_FIELDS = "id, username, email, phone, is_active, role, avatar_url, full_name, bio, address, phone_secondary, created_at, updated_at"
USER_FIELDS_WITH_PASSWORD = "id, username, email, phone, is_active, role, hashed_password, created_at, updated_at"

# 可更新用户字段白名单（防止字段名注入）
_UPDATABLE_USER_FIELDS = {
    'username', 'email', 'phone', 'full_name', 'bio', 'address', 
    'avatar_url', 'phone_secondary', 'is_active', 'role'
}


def _row_to_user_dict(row, include_password: bool = False) -> Dict[str, Any]:
    """将数据库行转换为用户字典"""
    if include_password:
        return {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'phone': row[3],
            'is_active': row[4],
            'role': row[5],
            'hashed_password': row[6],
            'created_at': row[7],
            'updated_at': row[8]
        }
    return {
        'id': row[0],
        'username': row[1],
        'email': row[2],
        'phone': row[3],
        'is_active': row[4],
        'role': row[5],
        'avatar_url': row[6],
        'full_name': row[7],
        'bio': row[8],
        'address': row[9],
        'phone_secondary': row[10],
        'created_at': row[11],
        'updated_at': row[12]
    }


def _row_to_basic_user_dict(row) -> Dict[str, Any]:
    """将基本用户信息行转换为字典"""
    return {
        'id': row[0],
        'username': row[1],
        'email': row[2],
        'phone': row[3],
        'is_active': row[4],
        'role': row[5],
        'created_at': row[6],
        'updated_at': row[7]
    }

def get_user_by_id(db, user_id: int) -> Optional[Dict[str, Any]]:
    """获取用户 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(
        f"SELECT {USER_FIELDS} FROM users WHERE id = %s LIMIT 1",
        (user_id,)
    )
    if rows:
        return _row_to_user_dict(rows[0])
    return None


def get_user_by_username(db, username: str) -> Optional[Dict[str, Any]]:
    """通过用户名获取用户 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(
        f"SELECT {USER_FIELDS_WITH_PASSWORD} FROM users WHERE username = %s LIMIT 1",
        (username,)
    )
    if rows:
        return _row_to_user_dict(rows[0], include_password=True)
    return None


def get_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    """通过邮箱获取用户 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(
        "SELECT id, username, email, phone, is_active, role, created_at, updated_at "
        "FROM users WHERE email = %s LIMIT 1",
        (email,)
    )
    if rows:
        return _row_to_basic_user_dict(rows[0])
    return None


def get_user_by_phone(db, phone: str) -> Optional[Dict[str, Any]]:
    """通过手机号获取用户 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(
        "SELECT id, username, email, phone, is_active, role, created_at, updated_at "
        "FROM users WHERE phone = %s LIMIT 1",
        (phone,)
    )
    if rows:
        return _row_to_basic_user_dict(rows[0])
    return None


def get_users(db, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """获取用户列表 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(
        "SELECT id, username, email, phone, is_active, role, created_at, updated_at "
        "FROM users ORDER BY id LIMIT %s OFFSET %s",
        (limit, skip)
    )
    return [_row_to_basic_user_dict(row) for row in rows]

def create_user(db, user: UserCreate):
    """
    创建新用户 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        user: 用户创建数据
        
    Returns:
        创建的用户对象
    """
    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()
    
    # 使用参数化查询插入用户数据
    phone_value = getattr(user, 'phone', None)
    is_active = user.is_active if user.is_active is not None else True
    role = user.role if user.role else "user"
    
    # 使用参数化查询，兼容层会处理占位符转换
    db.execute("""
        INSERT INTO users (username, email, phone, hashed_password, is_active, role, created_at, updated_at) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user.username, user.email, phone_value, hashed_password, is_active, role, now, now))
    
    # 获取刚插入的用户数据
    rows = db.query("SELECT id, username, email, phone, is_active, role, created_at, updated_at FROM users WHERE username = %s ORDER BY id DESC LIMIT 1", (user.username,))
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'username': result[1],
            'email': result[2],
            'phone': result[3],
            'is_active': result[4],
            'role': result[5],
            'created_at': result[6],
            'updated_at': result[7]
        }
    return None

def update_user(db, user_id: int, user_update):
    """
    更新用户信息 - 使用参数化查询
    
    Args:
        db: 数据库连接
        user_id: 用户ID
        user_update: 更新数据
        
    Returns:
        更新后的用户对象，如果用户不存在返回None
    """
    # 检查用户是否存在
    user = get_user(db, user_id)
    if not user:
        return None
    
    # 获取更新数据
    update_data = {}
    if hasattr(user_update, 'model_dump'):
        update_data = user_update.model_dump(exclude_unset=True)
    elif hasattr(user_update, '__dict__'):
        update_data = user_update.__dict__
    
    # 使用白名单过滤字段，防止字段名注入
    valid_updates = {}
    for field, value in update_data.items():
        if field in _UPDATABLE_USER_FIELDS:
            valid_updates[field] = value
    
    if not valid_updates:
        # 没有有效字段，直接返回原用户
        return user
    
    # 构建参数化更新语句
    set_clauses = []
    params = []
    
    for field, value in valid_updates.items():
        if field in ['is_active']:
            # 布尔字段
            set_clauses.append(f"{field} = %s")
            params.append(_format_bool(value))
        else:
            # 字符串字段
            set_clauses.append(f"{field} = %s")
            params.append(value if value is not None else None)
    
    # 添加更新时间
    set_clauses.append("updated_at = %s")
    params.append(datetime.utcnow())
    
    # 添加WHERE条件参数
    params.append(user_id)
    
    # 执行参数化更新
    sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s"
    db.execute(sql, params)
    
    # 返回更新后的用户数据
    return get_user(db, user_id)

def delete_user(db, user_id: int):
    """
    删除用户 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        user_id: 用户ID
        
    Returns:
        是否删除成功
    """
    # 检查用户是否存在
    user = get_user(db, user_id)
    if not user:
        return False
    
    # 使用 py-opengauss 的 execute 方法删除用户
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    return True

def update_user_password(db, user_id: int, new_password: str):
    """更新用户密码 - 使用参数化查询"""
    user = get_user(db, user_id)
    if user:
        hashed_password = get_password_hash(new_password)
        now = datetime.utcnow()
        # 使用 py-opengauss 的 execute 方法更新（直接传datetime对象）
        db.execute("UPDATE users SET hashed_password = %s, updated_at = %s WHERE id = %s", 
                  (hashed_password, now, user_id))
        return get_user(db, user_id)
    return None

def update_user_profile(db, user_id: int, profile_update):
    """更新用户个人资料 - 使用参数化查询"""
    user = get_user(db, user_id)
    if not user:
        return None
    
    # 获取更新数据
    update_data = {}
    if hasattr(profile_update, 'model_dump'):
        update_data = profile_update.model_dump(exclude_unset=True)
    elif hasattr(profile_update, '__dict__'):
        update_data = profile_update.__dict__
    
    # 使用白名单过滤字段（个人资料相关）
    profile_fields = {'full_name', 'bio', 'address', 'avatar_url', 'phone_secondary'}
    valid_updates = {}
    for field, value in update_data.items():
        if field in profile_fields:
            valid_updates[field] = value
    
    if not valid_updates:
        # 没有有效字段，直接返回原用户
        return user
    
    # 构建参数化更新语句
    set_clauses = []
    params = []
    
    for field, value in valid_updates.items():
        set_clauses.append(f"{field} = %s")
        params.append(value if value is not None else None)
    
    # 添加更新时间
    set_clauses.append("updated_at = %s")
    params.append(datetime.utcnow())
    
    # 添加WHERE条件参数
    params.append(user_id)
    
    # 执行参数化更新
    sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s"
    db.execute(sql, params)
    
    # 返回更新后的用户数据
    return get_user(db, user_id)

def get_user(db, user_id: int):
    """获取用户 - get_user_by_id的别名"""
    return get_user_by_id(db, user_id)

def get_user_profile(db, user_id: int):
    """获取用户完整个人资料"""
    return get_user(db, user_id)

def generate_verification_code(db, user_id: int, code_type: str):
    """
    生成验证码（6位数字）- 使用参数化查询
    
    Args:
        db: 数据库连接
        user_id: 用户ID
        code_type: 验证码类型（"email" 或 "phone"）
        
    Returns:
        验证码字符串
    """
    # 生成6位数字验证码
    code = str(random.randint(100000, 999999))
    expires = datetime.utcnow() + timedelta(minutes=10)  # 10分钟有效
    
    # 使用 py-opengauss 的 execute 方法更新（直接传datetime对象）
    db.execute("UPDATE users SET verification_code = %s, verification_code_expires = %s WHERE id = %s", 
              (code, expires, user_id))
    
    return code

def verify_verification_code(db, user_id: int, code: str) -> bool:
    """
    验证验证码 - 使用 py-opengauss 的 query 方法
    
    Args:
        db: 数据库连接
        user_id: 用户ID
        code: 验证码
        
    Returns:
        验证是否成功
    """
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query("SELECT verification_code, verification_code_expires FROM users WHERE id = %s LIMIT 1", (user_id,))
    
    if not rows:
        return False
    
    result = rows[0]
    db_code, expires = result
    
    # 检查验证码是否匹配
    if db_code != code:
        return False
    
    # 解析过期时间（兼容datetime和字符串格式）
    expires_dt = _parse_db_datetime(expires)
    if not expires_dt:
        return False
    
    # 检查验证码是否过期
    if expires_dt < datetime.utcnow():
        return False
    
    return True