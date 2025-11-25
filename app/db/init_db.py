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
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                role VARCHAR(20) NOT NULL DEFAULT 'viewer',
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_users_role CHECK (role IN ('admin','editor','viewer')),
                CONSTRAINT ck_users_is_active CHECK (is_active IN (TRUE, FALSE))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_status_role ON users (is_active, role)
        """)

        # Documents table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
                title VARCHAR(200) NOT NULL,
                content TEXT DEFAULT '',
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                folder_name VARCHAR(100) NOT NULL DEFAULT '',
                tags VARCHAR(500),
                is_locked BOOLEAN NOT NULL DEFAULT FALSE,
                locked_by INTEGER REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_documents_status CHECK (status IN ('active','archived','draft','deleted')),
                CONSTRAINT ck_documents_lock CHECK ((is_locked = FALSE AND locked_by IS NULL) OR (is_locked = TRUE AND locked_by IS NOT NULL)),
                CONSTRAINT ck_documents_tags_fmt CHECK (tags ~ '^[A-Za-z0-9_\\-]+(,[A-Za-z0-9_\\-]+)*$' OR tags IS NULL)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_owner_updated ON documents (owner_id, updated_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_folder ON documents (folder_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents (created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents (updated_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_tags_fts ON documents USING GIN (to_tsvector('simple', tags))
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_search_fts ON documents USING GIN (to_tsvector('simple', title || ' ' || content))
        """)

        # Comments table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                range_start INTEGER NULL,
                range_end INTEGER NULL,
                parent_id INTEGER NULL,
                mentions TEXT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_doc ON comments (document_id, created_at)
        """)

        # Tasks table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                assignee_id INTEGER NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'TODO',
                due_at DATE NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_doc ON tasks (document_id, status)
        """)

        # Document versions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_versions (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE ON UPDATE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
                version_number INTEGER NOT NULL,
                content_snapshot TEXT NOT NULL,
                summary VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_doc_versions_doc_ver UNIQUE (document_id, version_number),
                CONSTRAINT ck_doc_versions_ver CHECK (version_number > 0)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_versions_doc_ver ON document_versions (document_id, version_number DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_versions_doc ON document_versions (document_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_versions_created ON document_versions (created_at)
        """)

        # Operation logs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id INTEGER NOT NULL,
                description TEXT,
                ip_address VARCHAR(50),
                user_agent VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_op_logs_user_time ON operation_logs (user_id, created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_op_logs_resource ON operation_logs (resource_type, resource_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_op_logs_action ON operation_logs (action)
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
                permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE ON UPDATE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_role_permissions UNIQUE (role, permission_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions (role)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_role_permissions_perm ON role_permissions (permission_id)
        """)

        # Document templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                content TEXT NOT NULL,
                category VARCHAR(100) NOT NULL DEFAULT 'general',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_doc_templates_name UNIQUE (name),
                CONSTRAINT ck_doc_templates_category CHECK (char_length(category) <= 100)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_templates_category_active ON document_templates (category, is_active)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_templates_updated ON document_templates (updated_at)
        """)

        # ACL table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS acls (
                id SERIAL PRIMARY KEY,
                resource_type VARCHAR(50) NOT NULL,
                resource_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
                role VARCHAR(20),
                permission VARCHAR(100) NOT NULL,
                granted BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_acls_user_perm UNIQUE (resource_type, resource_id, user_id, permission)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_acls_user_res ON acls (user_id, resource_type, resource_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_acls_role_res ON acls (role, resource_type, resource_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_acls_res ON acls (resource_type, resource_id)
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
