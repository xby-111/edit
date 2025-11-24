"""
数据库初始化模块
"""
import logging
from app.db.session import conn
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    """
    Initialize the database by testing connection and creating tables if needed.
    """
    try:
        # Test database connection（py-opengauss 要用 query 来拿结果）
        result = conn.query("SELECT 1")
        logger.info(f"数据库连接成功: {result}")

        # Create tables if they don't exist
        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE,
                phone VARCHAR(20) UNIQUE,
                hashed_password VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                role VARCHAR(20) DEFAULT 'viewer',
                avatar_url VARCHAR(500),
                full_name VARCHAR(100),
                bio TEXT,
                address VARCHAR(500),
                phone_secondary VARCHAR(20),
                password_reset_token VARCHAR(255),
                password_reset_expires TIMESTAMP,
                verification_code VARCHAR(10),
                verification_code_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Documents table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER REFERENCES users(id),
                title VARCHAR(200) NOT NULL,
                content TEXT DEFAULT '',
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Document versions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_versions (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id),
                user_id INTEGER REFERENCES users(id),
                version_number INTEGER NOT NULL,
                content_snapshot TEXT NOT NULL,
                summary VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Operation logs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id INTEGER,
                description TEXT,
                ip_address VARCHAR(50),
                user_agent VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Permissions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                resource_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Role permissions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                id SERIAL PRIMARY KEY,
                role VARCHAR(20) NOT NULL,
                permission_id INTEGER REFERENCES permissions(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ACL table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS acls (
                id SERIAL PRIMARY KEY,
                resource_type VARCHAR(50) NOT NULL,
                resource_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES users(id),
                role VARCHAR(20),
                permission VARCHAR(100) NOT NULL,
                granted BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise  # 数据库初始化失败应该阻止应用启动


if __name__ == "__main__":
    init_db()
