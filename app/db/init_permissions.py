"""
初始化默认权限和角色权限
"""
import logging
from app.db.session import SessionLocal
from models import Permission, RolePermission

logger = logging.getLogger(__name__)

def init_permissions():
    """初始化默认权限"""
    db = SessionLocal()
    try:
        # 定义默认权限
        default_permissions = [
            {"name": "read_document", "description": "读取文档", "resource_type": "document"},
            {"name": "write_document", "description": "创建文档", "resource_type": "document"},
            {"name": "update_document", "description": "更新文档", "resource_type": "document"},
            {"name": "delete_document", "description": "删除文档", "resource_type": "document"},
            {"name": "read_user", "description": "查看用户", "resource_type": "user"},
            {"name": "update_user", "description": "更新用户", "resource_type": "user"},
            {"name": "delete_user", "description": "删除用户", "resource_type": "user"},
            {"name": "manage_permissions", "description": "管理权限", "resource_type": "system"},
            {"name": "view_logs", "description": "查看日志", "resource_type": "system"},
        ]
        
        # 创建权限
        for perm_data in default_permissions:
            existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()
            if not existing:
                permission = Permission(**perm_data)
                db.add(permission)
        
        db.commit()
        
        # 获取所有权限ID
        all_permissions = db.query(Permission).all()
        perm_dict = {p.name: p.id for p in all_permissions}
        
        # 为角色分配权限
        role_permissions = {
            "admin": list(perm_dict.keys()),  # 管理员拥有所有权限
            "editor": ["read_document", "write_document", "update_document", "read_user"],
            "viewer": ["read_document", "read_user"]
        }
        
        for role, perm_names in role_permissions.items():
            for perm_name in perm_names:
                if perm_name in perm_dict:
                    existing = db.query(RolePermission).filter(
                        RolePermission.role == role,
                        RolePermission.permission_id == perm_dict[perm_name]
                    ).first()
                    if not existing:
                        role_perm = RolePermission(
                            role=role,
                            permission_id=perm_dict[perm_name]
                        )
                        db.add(role_perm)
        
        db.commit()
        logger.info("权限初始化完成")
    except Exception as e:
        db.rollback()
        logger.error(f"权限初始化失败: {e}", exc_info=True)
        raise  # 权限初始化失败应该抛出异常，让调用方决定如何处理
    finally:
        db.close()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    init_permissions()

