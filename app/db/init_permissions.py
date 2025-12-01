"""
初始化默认权限和角色权限 - 使用原生 SQL 操作
"""
import logging
from app.db.session import get_global_connection

logger = logging.getLogger(__name__)

def init_permissions():
    """初始化默认权限"""
    conn = get_global_connection()
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
        
        # 创建权限（使用原生 SQL）
        for perm_data in default_permissions:
            # 检查权限是否已存在
            existing = conn.query(
                "SELECT id FROM permissions WHERE name = %s LIMIT 1",
                (perm_data["name"],)
            )
            if not existing:
                conn.execute(
                    """
                    INSERT INTO permissions (name, description, resource_type) 
                    VALUES (%s, %s, %s)
                    """,
                    (perm_data["name"], perm_data["description"], perm_data["resource_type"])
                )
        
        # 获取所有权限ID
        all_permissions = conn.query("SELECT id, name FROM permissions", ())
        perm_dict = {row[1]: row[0] for row in all_permissions}
        
        # 为角色分配权限
        role_permissions = {
            "admin": list(perm_dict.keys()),  # 管理员拥有所有权限
            "editor": ["read_document", "write_document", "update_document", "read_user"],
            "viewer": ["read_document", "read_user"]
        }
        
        for role, perm_names in role_permissions.items():
            for perm_name in perm_names:
                if perm_name in perm_dict:
                    # 检查角色权限是否已存在
                    existing = conn.query(
                        "SELECT id FROM role_permissions WHERE role = %s AND permission_id = %s LIMIT 1",
                        (role, perm_dict[perm_name])
                    )
                    if not existing:
                        conn.execute(
                            """
                            INSERT INTO role_permissions (role, permission_id) 
                            VALUES (%s, %s)
                            """,
                            (role, perm_dict[perm_name])
                        )
        
        logger.info("权限初始化完成")
    except Exception as e:
        logger.error(f"权限初始化失败: {e}", exc_info=True)
        raise  # 权限初始化失败应该抛出异常，让调用方决定如何处理

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    init_permissions()

