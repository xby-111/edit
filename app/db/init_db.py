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
                folder_name VARCHAR(100),
                tags VARCHAR(500),
                is_locked BOOLEAN DEFAULT FALSE,
                locked_by INTEGER REFERENCES users(id),
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

        # Document templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                content TEXT NOT NULL,
                category VARCHAR(100) DEFAULT 'general',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # 插入默认模板
        insert_default_templates()

        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise  # 数据库初始化失败应该阻止应用启动


def insert_default_templates():
    """插入默认文档模板"""
    default_templates = [
        {
            'name': '空白文档',
            'description': '一个空白文档，适合自由创作',
            'content': '<p>开始编写您的内容...</p>',
            'category': 'general'
        },
        {
            'name': '会议纪要',
            'description': '标准的会议纪要模板',
            'content': '''<h2>会议纪要</h2>
<h3>会议基本信息</h3>
<p><strong>会议主题：</strong></p>
<p><strong>会议时间：</strong></p>
<p><strong>会议地点：</strong></p>
<p><strong>参会人员：</strong></p>
<h3>会议议程</h3>
<ol>
<li></li>
<li></li>
<li></li>
</ol>
<h3>讨论内容</h3>
<p></p>
<h3>会议决议</h3>
<p></p>
<h3>行动项</h3>
<ul>
<li><strong>负责人：</strong> <strong>截止时间：</strong> <strong>任务：</strong></li>
</ul>''',
            'category': 'business'
        },
        {
            'name': '项目计划',
            'description': '项目计划书模板',
            'content': '''<h2>项目计划书</h2>
<h3>1. 项目概述</h3>
<p><strong>项目名称：</strong></p>
<p><strong>项目目标：</strong></p>
<p><strong>项目背景：</strong></p>
<h3>2. 项目范围</h3>
<p></p>
<h3>3. 时间计划</h3>
<p><strong>开始时间：</strong></p>
<p><strong>预计完成时间：</strong></p>
<p><strong>关键里程碑：</strong></p>
<h3>4. 资源需求</h3>
<p></p>
<h3>5. 风险评估</h3>
<p></p>''',
            'category': 'project'
        },
        {
            'name': '技术文档',
            'description': '技术文档编写模板',
            'content': '''<h2>技术文档</h2>
<h3>1. 概述</h3>
<p></p>
<h3>2. 系统架构</h3>
<p></p>
<h3>3. 接口说明</h3>
<p></p>
<h3>4. 数据模型</h3>
<p></p>
<h3>5. 部署说明</h3>
<p></p>
<h3>6. 故障排除</h3>
<p></p>''',
            'category': 'technical'
        }
    ]
    
    for template in default_templates:
        name_safe = _escape(template['name'])
        desc_safe = _escape(template['description'])
        content_safe = _escape(template['content'])
        category_safe = _escape(template['category'])
        
        # 检查模板是否已存在
        existing = conn.query(f"SELECT id FROM document_templates WHERE name = {name_safe} LIMIT 1")
        if not existing:
            conn.execute(f"""
                INSERT INTO document_templates (name, description, content, category, is_active) 
                VALUES ({name_safe}, {desc_safe}, {content_safe}, {category_safe}, TRUE)
            """)

def _escape(value: str | None) -> str:
    """简单转义单引号，避免 SQL 语法错误"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

if __name__ == "__main__":
    init_db()
