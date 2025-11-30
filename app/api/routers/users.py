"""
用户管理路由
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas import User, UserUpdate
from app.services.user_service import get_user, update_user, delete_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["用户管理"])

def log_operation(db, user_id: int, action: str, resource_type: str = None, 
                  resource_id: int = None, description: str = None, 
                  ip_address: str = None, user_agent: str = None):
    """记录操作日志的辅助函数"""
    try:
        from datetime import datetime
        db.execute(
            """
            INSERT INTO operation_logs (user_id, action, resource_type, resource_id, description, ip_address, user_agent, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [user_id, action, resource_type, resource_id, description, ip_address, user_agent, datetime.utcnow()]
        )
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}", exc_info=True)
        # 日志记录失败不应该影响主业务，只记录错误

@router.get("/users/{user_id}", response_model=User, summary="获取用户信息", description="根据用户ID获取用户详细信息")
def read_user(user_id: int, current_user: User = Depends(get_current_user), db = Depends(get_db)):
    """获取用户信息"""
    db_user = get_user(db, user_id=user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 记录操作日志
    log_operation(db, current_user.id, "view_user", "user", user_id, 
                 f"查看用户 {db_user['username']} 的信息")
    
    return User(
        id=db_user['id'],
        username=db_user['username'],
        email=db_user['email'],
        phone=db_user.get('phone'),
        is_active=db_user['is_active'],
        role=db_user['role'],
        full_name=db_user.get('full_name'),
        bio=db_user.get('bio'),
        avatar_url=db_user.get('avatar_url'),
        created_at=db_user['created_at'],
        updated_at=db_user.get('updated_at')
    )

@router.put("/users/{user_id}", response_model=User, summary="更新用户信息", description="更新指定用户的个人信息")
def update_user_info(user_id: int, user_update: UserUpdate, 
                     current_user: User = Depends(get_current_user), 
                     db = Depends(get_db)):
    """更新用户信息（管理员或本人）"""
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        updated_user = update_user(db, user_id=user_id, user_update=user_update)
        if not updated_user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        # 记录操作日志
        log_operation(db, current_user.id, "update_user", "user", user_id, "更新用户信息")
        
        return User(
            id=updated_user['id'],
            username=updated_user['username'],
            email=updated_user['email'],
            phone=updated_user.get('phone'),
            is_active=updated_user['is_active'],
            role=updated_user['role'],
            full_name=updated_user.get('full_name'),
            bio=updated_user.get('bio'),
            avatar_url=updated_user.get('avatar_url'),
            created_at=updated_user['created_at'],
            updated_at=updated_user['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新用户失败")

@router.delete("/users/{user_id}", summary="删除用户", description="删除指定用户账户（仅管理员）")
def delete_user_info(user_id: int, current_user: User = Depends(get_current_user), 
                     db = Depends(get_db)):
    """删除用户（仅管理员）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        success = delete_user(db, user_id=user_id)
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        # 记录操作日志
        log_operation(db, current_user.id, "delete_user", "user", user_id, "删除用户")
        
        return {"message": "用户删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除用户失败")