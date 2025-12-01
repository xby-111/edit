"""
数据库初始化模块
"""
import logging
from app.db.session import get_global_connection
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _create_schema(conn):
    """幂等创建数据库表结构与索引。"""
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
            role VARCHAR(20) NOT NULL DEFAULT 'user',
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
            CONSTRAINT ck_users_role CHECK (role IN ('admin','user')),
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
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
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

    # Notifications table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            type VARCHAR(32) NOT NULL,
            title VARCHAR(200) NOT NULL,
            content TEXT NULL,
            payload TEXT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NULL
        )
    """)
    # 如果表已存在但没有updated_at字段，添加它
    try:
        conn.execute("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL
        """)
    except Exception:
        # 如果ALTER失败（可能字段已存在），忽略
        pass
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications (user_id, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications (user_id, is_read, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_type ON notifications (user_id, type, created_at DESC)
    """)

    # Audit logs table (审计日志表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NULL,
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50) NULL,
            resource_id BIGINT NULL,
            ip VARCHAR(50) NULL,
            user_agent VARCHAR(500) NULL,
            meta_json TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON audit_logs (user_id, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action)
    """)

    # System settings table (系统设置表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id SERIAL PRIMARY KEY,
            key VARCHAR(200) UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_system_settings_key ON system_settings (key)
    """)

    # User feedback table (用户反馈表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_feedback (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NULL,
            rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_feedback_created ON user_feedback (created_at DESC)
    """)

    # Document collaborators table (文档协作者表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_collaborators (
            id BIGSERIAL PRIMARY KEY,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_doc_collab UNIQUE (document_id, user_id),
            CONSTRAINT ck_doc_collab_role CHECK (role IN ('viewer', 'editor'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_doc_collab_document ON document_collaborators (document_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_doc_collab_user ON document_collaborators (user_id)
    """)

    # Verification codes table (验证码表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS verification_codes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NULL,
            email VARCHAR(255) NULL,
            phone VARCHAR(32) NULL,
            code_hash VARCHAR(64) NOT NULL,
            code_type VARCHAR(32) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_codes_email ON verification_codes (email, code_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_codes_phone ON verification_codes (phone, code_type)
    """)

    # OAuth accounts table (OAuth 账户表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_accounts (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(32) NOT NULL,
            provider_user_id VARCHAR(255) NOT NULL,
            access_token TEXT NULL,
            refresh_token TEXT NULL,
            expires_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_oauth_provider_user UNIQUE (provider, provider_user_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_accounts_user_id ON oauth_accounts (user_id)
    """)

    # TOTP secrets table (双因素认证密钥表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS totp_secrets (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            secret VARCHAR(64) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            backup_codes TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)

    # Chat messages table (聊天消息表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGSERIAL PRIMARY KEY,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            message_type VARCHAR(16) NOT NULL DEFAULT 'text',
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_document ON chat_messages (document_id, created_at DESC)
    """)

    # System metrics table (系统指标表)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            id BIGSERIAL PRIMARY KEY,
            metric_name VARCHAR(64) NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            tags TEXT NULL,
            recorded_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics (metric_name, recorded_at DESC)
    """)

    # 插入默认模板
    insert_default_templates()

    logger.info("数据库表创建成功")


def init_db():
    """初始化数据库表结构"""
    logger.info("开始初始化数据库...")
    
    # 获取数据库连接
    conn = get_global_connection()
    
    # 检查数据库连接
    try:
        conn.query("SELECT 1")
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise

    try:
        _create_schema(conn)
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
    
    conn = get_global_connection()
    for template in default_templates:
        # 检查模板是否已存在
        existing = conn.query("SELECT id FROM document_templates WHERE name = %s LIMIT 1", (template['name'],))
        if not existing:
            conn.execute("""
                INSERT INTO document_templates (name, description, content, category, is_active) 
                VALUES (%s, %s, %s, %s, TRUE)
            """, (template['name'], template['description'], template['content'], template['category']))


if __name__ == "__main__":
    init_db()
