# app/db/session.py

import logging
import urllib.parse
import time
from typing import Generator, Any
import py_opengauss
from app.core.config import settings

logger = logging.getLogger(__name__)

# 从配置中读取数据库连接字符串
# py-opengauss 需要特定的连接格式
DATABASE_URL = settings.DATABASE_URL

# 解析连接字符串
# 格式: opengauss://username:password@host:port/database
def parse_database_url(url):
    """解析数据库连接字符串，支持密码中的特殊字符"""
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
        
        # URL decode 密码（处理特殊字符如 %40）
        password = urllib.parse.unquote(password)
        
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


def create_connection(max_retries=3):
    """创建新的数据库连接（延迟连接 + 重试机制）"""
    last_error = None
    for attempt in range(max_retries):
        try:
            # 解析连接参数
            db_params = parse_database_url(DATABASE_URL)
            # 安全地记录连接参数（不包含密码）
            logger.info(f"尝试连接数据库 (尝试 {attempt + 1}/{max_retries}): host={db_params['host']}, port={db_params['port']}, user={db_params['user']}, database={db_params['database']}")
            
            # 使用解析后的参数创建连接
            # py-opengauss 使用 open 方法
            conn = py_opengauss.open(DATABASE_URL)
            logger.info("openGauss 连接创建成功")
            return conn
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避：1s, 2s, 4s
                logger.warning(f"连接数据库失败，{wait_time}秒后重试: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"创建 openGauss 连接失败（已重试{max_retries}次）: {e}", exc_info=True)
    
    # 所有重试都失败
    raise last_error


def get_db() -> Generator[Any, None, None]:
    """
    FastAPI 依赖：为每个请求提供独立的数据库连接。
    使用上下文管理器确保连接正确关闭。
    """
    conn = None
    try:
        conn = create_connection()
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        raise
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接失败: {e}")


def get_db_connection():
    """
    获取数据库连接（用于脚本等非FastAPI场景）
    注意：调用者需要负责关闭连接
    """
    return create_connection()


def close_connection_safely(conn):
    """安全关闭数据库连接"""
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")


# 向后兼容的全局连接（仅用于非关键路径，如脚本）
_global_conn = None

def get_global_connection():
    """获取全局连接（向后兼容，仅用于脚本等非并发场景）"""
    global _global_conn
    if _global_conn is None:
        try:
            _global_conn = create_connection()
            logger.warning("使用全局连接，仅建议用于脚本等非并发场景")
        except Exception as e:
            logger.error(f"创建全局连接失败: {e}")
            raise
    return _global_conn