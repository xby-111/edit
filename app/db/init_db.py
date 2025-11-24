"""
数据库初始化模块
"""
import logging
from app.db.session import engine
from models import Base

logger = logging.getLogger(__name__)

def init_db():
    """
    Initialize the database by creating all tables.
    """
    # Create all tables for user and document models
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")
        
        # 初始化默认权限（如果权限模块存在）
        try:
            from app.db.init_permissions import init_permissions
            init_permissions()
        except ImportError:
            # 权限初始化模块不存在，跳过
            logger.warning("权限初始化模块不存在，跳过权限初始化")
        except Exception as e:
            logger.error(f"权限初始化失败: {e}", exc_info=True)
            # 权限初始化失败不应该阻止应用启动，但需要记录错误
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise  # 数据库初始化失败应该阻止应用启动

if __name__ == "__main__":
    init_db()