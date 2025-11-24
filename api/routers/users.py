"""
用户管理路由
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from core.security import get_current_user
from db.session import get_db
from schemas import User, UserUpdate
from services.user_service import get_user, update_user, delete_user
from models import OperationLog

logger = logging.getLogger(__name__)

router = APIRouter()

def log_operation(db: Session, user_id: int, action: str, resource_type: str = None, 
                  resource_id: int = None, description: str = None, 
                  ip_address: str = None, user_agent: str = None):
    """记录操作日志的辅助函数"""
    try:
        log = OperationLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}", exc_info=True)
        # 日志记录失败不应该影响主业务，只记录错误

@router.get("/users/{user_id}", response_model=User)
def read_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取用户信息"""
    db_user = get_user(db, user_id=user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 记录操作日志
    log_operation(db, current_user.id, "view_user", "user", user_id, 
                 f"查看用户 {db_user.username} 的信息")
    
    return User(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        phone=getattr(db_user, 'phone', None),
        is_active=db_user.is_active,
        role=db_user.role,
        full_name=getattr(db_user, 'full_name', None),
        bio=getattr(db_user, 'bio', None),
        avatar_url=getattr(db_user, 'avatar_url', None),
        created_at=db_user.created_at,
        updated_at=getattr(db_user, 'updated_at', None)
    )

@router.put("/users/{user_id}", response_model=User)
def update_user_info(user_id: int, user_update: UserUpdate, 
                     current_user: User = Depends(get_current_user), 
                     db: Session = Depends(get_db)):
    """更新用户信息（管理员或本人）"""
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    try:
        updated_user = update_user(db, user_id=user_id, user_update=user_update, commit=False)
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        db.commit()
        db.refresh(updated_user)
        
        # 记录操作日志
        log_operation(db, current_user.id, "update_user", "user", user_id, "更新用户信息")
        
        return User(
            id=updated_user.id,
            username=updated_user.username,
            email=updated_user.email,
            phone=getattr(updated_user, 'phone', None),
            is_active=updated_user.is_active,
            role=updated_user.role,
            full_name=getattr(updated_user, 'full_name', None),
            bio=getattr(updated_user, 'bio', None),
            avatar_url=getattr(updated_user, 'avatar_url', None),
            created_at=updated_user.created_at,
            updated_at=getattr(updated_user, 'updated_at', None)
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新用户失败")

@router.delete("/users/{user_id}")
def delete_user_info(user_id: int, current_user: User = Depends(get_current_user), 
                     db: Session = Depends(get_db)):
    """删除用户（仅管理员）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    try:
        success = delete_user(db, user_id=user_id, commit=False)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        
        db.commit()
        
        # 记录操作日志
        log_operation(db, current_user.id, "delete_user", "user", user_id, "删除用户")
        
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除用户失败")