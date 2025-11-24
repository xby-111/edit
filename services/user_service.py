"""
用户服务层 - 不直接提交事务，由调用方控制
"""
import logging
from sqlalchemy.orm import Session
from models import User
from schemas import UserCreate
from core.security import get_password_hash
from datetime import datetime

logger = logging.getLogger(__name__)

def get_user(db: Session, user_id: int):
    """获取用户（不提交事务）"""
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    """通过用户名获取用户（不提交事务）"""
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str):
    """通过邮箱获取用户（不提交事务）"""
    return db.query(User).filter(User.email == email).first()

def get_user_by_phone(db: Session, phone: str):
    """通过手机号获取用户（不提交事务）"""
    return db.query(User).filter(User.phone == phone).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    """获取用户列表（不提交事务）"""
    return db.query(User).offset(skip).limit(limit).all()

def create_user(db: Session, user: UserCreate, commit: bool = False):
    """
    创建新用户
    
    Args:
        db: 数据库会话
        user: 用户创建数据
        commit: 是否立即提交事务（默认False，由调用方控制）
        
    Returns:
        创建的用户对象
    """
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        phone=getattr(user, 'phone', None),
        hashed_password=hashed_password,
        is_active=user.is_active if user.is_active is not None else True,
        role=user.role if user.role else "viewer"
    )
    db.add(db_user)
    if commit:
        db.commit()
        db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update, commit: bool = False):
    """
    更新用户信息
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        user_update: 更新数据
        commit: 是否立即提交事务（默认False）
        
    Returns:
        更新后的用户对象，如果用户不存在返回None
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        # Update only the fields that are provided in the update request
        for field, value in user_update.model_dump(exclude_unset=True).items():
            setattr(db_user, field, value)
        db_user.updated_at = datetime.utcnow()
        if commit:
            db.commit()
            db.refresh(db_user)
        return db_user
    return None

def delete_user(db: Session, user_id: int, commit: bool = False):
    """
    删除用户
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        commit: 是否立即提交事务（默认False）
        
    Returns:
        是否删除成功
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        if commit:
            db.commit()
        return True
    return False

def update_user_password(db: Session, user_id: int, new_password: str, commit: bool = False):
    """更新用户密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.hashed_password = get_password_hash(new_password)
        user.updated_at = datetime.utcnow()
        if commit:
            db.commit()
            db.refresh(user)
        return user
    return None

def update_user_profile(db: Session, user_id: int, profile_update, commit: bool = False):
    """更新用户个人资料"""
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        update_data = profile_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_user, field, value)
        db_user.updated_at = datetime.utcnow()
        if commit:
            db.commit()
            db.refresh(db_user)
        return db_user
    return None

def get_user_profile(db: Session, user_id: int):
    """获取用户完整个人资料"""
    return db.query(User).filter(User.id == user_id).first()

def generate_verification_code(db: Session, user_id: int, code_type: str, commit: bool = False) -> str:
    """
    生成验证码（6位数字）
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        code_type: 验证码类型（"email" 或 "phone"）
        commit: 是否立即提交事务（默认False）
        
    Returns:
        验证码字符串
    """
    import random
    from datetime import timedelta
    
    # 生成6位数字验证码
    code = str(random.randint(100000, 999999))
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.verification_code = code
        user.verification_code_expires = datetime.utcnow() + timedelta(minutes=10)  # 10分钟有效
        if commit:
            db.commit()
    
    return code

def verify_verification_code(db: Session, user_id: int, code: str) -> bool:
    """
    验证验证码
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        code: 验证码
        
    Returns:
        验证是否成功
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    
    # 检查验证码是否匹配
    if user.verification_code != code:
        return False
    
    # 检查验证码是否过期
    if user.verification_code_expires and user.verification_code_expires < datetime.utcnow():
        return False
    
    return True