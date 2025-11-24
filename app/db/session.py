# app/db/session.py

import logging
import py_opengauss
from app.core.config import settings

logger = logging.getLogger(__name__)

# 从配置中读取数据库连接字符串
# py-opengauss 需要特定的连接格式
DATABASE_URL = settings.DATABASE_URL

# 解析连接字符串
# 格式: opengauss://username:password@host:port/database
def parse_database_url(url):
    """解析数据库连接字符串"""
    try:
        # 移除协议前缀
        if url.startswith('opengauss://'):
            url = url[12:]
        
        # 分离认证信息和主机信息
        if '@' in url:
            auth, host_db = url.split('@', 1)
        else:
            raise ValueError("Invalid database URL: missing @")
        
        # 分离用户名和密码
        if ':' in auth:
            username, password = auth.split(':', 1)
        else:
            raise ValueError("Invalid database URL: missing password")
        
        # 分离主机和数据库
        if '/' in host_db:
            host_port, database = host_db.split('/', 1)
        else:
            raise ValueError("Invalid database URL: missing database")
        
        # 分离主机和端口
        if ':' in host_port:
            host, port = host_port.split(':', 1)
        else:
            host = host_port
            port = 5432  # 默认端口
        
        return {
            'host': host,
            'port': int(port),
            'user': username,
            'password': password,
            'database': database
        }
    except Exception as e:
        logger.error(f"解析数据库连接字符串失败: {e}")
        raise

# 创建全局连接对象
try:
    # 解析连接参数
    db_params = parse_database_url(DATABASE_URL)
    logger.info(f"数据库连接参数: host={db_params['host']}, port={db_params['port']}, user={db_params['user']}, database={db_params['database']}")
    
    # 使用解析后的参数创建连接
    # py-opengauss 使用 open 方法
    conn = py_opengauss.open(DATABASE_URL)
    logger.info("openGauss 连接创建成功")
except Exception as e:
    logger.error(f"创建 openGauss 连接失败: {e}", exc_info=True)
    raise


def get_db():
    """
    FastAPI 依赖：为接口提供数据库连接。
    目前先使用全局 conn，后面需要的话可以改成“每请求一个连接”的模式。
    """
    try:
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        raise
