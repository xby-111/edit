#!/usr/bin/env python3
"""
数据库自检脚本：检查并修复 comments 表缺少的 updated_at 列
"""
import sys
import os
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.db.session import get_db_connection
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    if exc.name == "py_opengauss":
        print(
            "缺少 py_opengauss 依赖，请先安装：pip install -r requirements.txt "
            "-i https://pypi.tuna.tsinghua.edu.cn/simple"
        )
        sys.exit(1)
    raise
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"
SQL_DIR.mkdir(exist_ok=True)


def _append_sql(filename: str, sql: str):
    path = SQL_DIR / filename
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(sql.strip())
        if not sql.strip().endswith(";"):
            fp.write(";")
        fp.write("\n\n")

def check_and_fix_comments_table():
    """检查并修复 comments 表结构"""
    conn = get_db_connection()
    
    try:
        # 检查 updated_at 列是否存在
        result = conn.query("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'comments' AND column_name = 'updated_at'
        """)
        
        if not result:
            print("comments 表缺少 updated_at 列，开始修复...")
            
            # 添加 updated_at 列
            conn.execute("""
                ALTER TABLE comments 
                ADD COLUMN updated_at TIMESTAMP
            """)
            
            # 回填历史数据
            conn.execute("""
                UPDATE comments 
                SET updated_at = COALESCE(created_at, NOW())
                WHERE updated_at IS NULL
            """)
            
            # 为新记录设置默认值（如果数据库支持）
            try:
                conn.execute("""
                    ALTER TABLE comments 
                    ALTER COLUMN updated_at SET DEFAULT NOW()
                """)
            except Exception as e:
                print(f"设置默认值失败（某些数据库不支持），跳过: {e}")
            
            print("✅ comments 表 updated_at 列已成功添加并回填数据")
        else:
            print("✅ comments 表已包含 updated_at 列，无需修复")
            
        # 验证修复结果
        null_result = conn.query("""
            SELECT COUNT(*) FROM comments WHERE updated_at IS NULL
        """)
        null_count = null_result[0][0] if null_result else 0
        
        if null_count > 0:
            print(f"⚠️  警告：仍有 {null_count} 条记录的 updated_at 为 NULL")
        else:
            print("✅ 所有记录的 updated_at 都已正确设置")

        anchor_col = conn.query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'comments' AND column_name = 'anchor_json'
            """
        )
        if not anchor_col:
            conn.execute("ALTER TABLE comments ADD COLUMN anchor_json TEXT NULL")
            print("✅ 已为 comments 添加 anchor_json 列")
        else:
            print("✅ comments.anchor_json 列已存在")
            
    except Exception as e:
        print(f"❌ 修复过程中出错: {e}")
        return False
    
    return True

def check_and_create_collaborators_table():
    """检查并创建 document_collaborators 表"""
    conn = get_db_connection()
    
    try:
        # 检查表是否存在
        result = conn.query("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'document_collaborators'
        """)
        
        if not result:
            print("document_collaborators 表不存在，开始创建...")
            
            # 创建表
            conn.execute("""
                CREATE TABLE document_collaborators (
                    document_id INT NOT NULL,
                    user_id INT NOT NULL,
                    role VARCHAR(16) NOT NULL DEFAULT 'editor',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (document_id, user_id)
                )
            """)
            
            # 创建索引以提高查询性能
            conn.execute("""
                CREATE INDEX idx_document_collaborators_user_id ON document_collaborators(user_id)
            """)
            
            print("✅ document_collaborators 表已成功创建")
        else:
            print("✅ document_collaborators 表已存在，无需创建")
            
            # 检查并添加索引（如果不存在）
            index_result = conn.query("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'document_collaborators' AND indexname = 'idx_document_collaborators_user_id'
            """)
            
            if not index_result:
                conn.execute("""
                    CREATE INDEX idx_document_collaborators_user_id ON document_collaborators(user_id)
                """)
                print("✅ 已添加 user_id 索引")
            
    except Exception as e:
        print(f"❌ 创建 document_collaborators 表时出错: {e}")
        return False
    
    return True


def _sql_literal(s: str) -> str:
    """SQL字符串字面量转义"""
    return "'" + s.replace("'", "''") + "'"



def check_and_create_notifications_table():
    """检查并创建 notifications 表和索引"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'notifications'
            """
        )

        if not table_result:
            print("notifications 表不存在，开始创建...")
            create_sql = """
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
                """
            _append_sql("notifications.sql", create_sql)
            conn.execute(create_sql)
            print("✅ notifications 表已创建")
        else:
            print("✅ notifications 表已存在")

            column_result = conn.query(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'notifications' AND column_name = 'updated_at'
                """
            )
            if not column_result:
                alter_sql = "ALTER TABLE notifications ADD COLUMN updated_at TIMESTAMP NULL"
                _append_sql("notifications.sql", alter_sql)
                conn.execute(alter_sql)
                print("✅ 已添加 notifications.updated_at 列")
            else:
                print("✅ notifications.updated_at 列已存在")

        indexes = {
            "idx_notifications_user_created": "CREATE INDEX idx_notifications_user_created ON notifications (user_id, created_at DESC)",
            "idx_notifications_user_unread": "CREATE INDEX idx_notifications_user_unread ON notifications (user_id, is_read, created_at DESC)",
            "idx_notifications_user_type": "CREATE INDEX idx_notifications_user_type ON notifications (user_id, type, created_at DESC)",
        }

        for index_name, create_sql in indexes.items():
            index_result = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'notifications' AND indexname = %s
                """,
                (index_name,),
            )
            if not index_result:
                conn.execute(create_sql)
                print(f"✅ 已创建索引 {index_name}")
            else:
                print(f"✅ 索引 {index_name} 已存在")

    except Exception as e:
        print(f"❌ 检查 notifications 表时出错: {e}")
        return False

    return True


def check_and_create_document_tags_table():
    """创建 document_tags 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'document_tags'
            """
        )

        if not table_result:
            print("document_tags 表不存在，开始创建...")
            create_sql = """
                CREATE TABLE IF NOT EXISTS document_tags (
                    id BIGSERIAL PRIMARY KEY,
                    document_id BIGINT NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            _append_sql("document_tags.sql", create_sql)
            conn.execute(create_sql)
        else:
            print("✅ document_tags 表已存在")

        indexes = {
            "idx_document_tags_doc": "CREATE INDEX idx_document_tags_doc ON document_tags(document_id)",
            "idx_document_tags_tag": "CREATE INDEX idx_document_tags_tag ON document_tags(tag)",
        }
        for name, sql in indexes.items():
            idx = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'document_tags' AND indexname = %s
                """,
                (name,),
            )
            if not idx:
                _append_sql("document_tags.sql", sql)
                conn.execute(sql)
                print(f"✅ 已创建索引 {name}")
            else:
                print(f"✅ 索引 {name} 已存在")

    except Exception as e:
        print(f"❌ 创建 document_tags 表时出错: {e}")
        return False

    return True


def check_and_create_notification_settings_table():
    """创建 notification_settings 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'notification_settings'
            """
        )

        if not table_result:
            print("notification_settings 表不存在，开始创建...")
            create_sql = """
                CREATE TABLE IF NOT EXISTS notification_settings (
                    user_id BIGINT PRIMARY KEY,
                    mute_all BOOLEAN NOT NULL DEFAULT FALSE,
                    mute_types TEXT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            _append_sql("notification_settings.sql", create_sql)
            conn.execute(create_sql)
        else:
            print("✅ notification_settings 表已存在")

    except Exception as e:
        print(f"❌ 创建 notification_settings 表时出错: {e}")
        return False

    return True


def check_and_create_password_reset_tokens_table():
    """创建 password_reset_tokens 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'password_reset_tokens'
            """
        )

        if not table_result:
            print("password_reset_tokens 表不存在，开始创建...")
            create_sql = """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            _append_sql("password_reset_tokens.sql", create_sql)
            conn.execute(create_sql)
        else:
            print("✅ password_reset_tokens 表已存在")

        indexes = {
            "idx_password_reset_tokens_user": "CREATE INDEX idx_password_reset_tokens_user ON password_reset_tokens(user_id)",
            "idx_password_reset_tokens_token": "CREATE UNIQUE INDEX idx_password_reset_tokens_token ON password_reset_tokens(token)",
        }

        for name, sql in indexes.items():
            idx = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'password_reset_tokens' AND indexname = %s
                """,
                (name,),
            )
            if not idx:
                _append_sql("password_reset_tokens.sql", sql)
                conn.execute(sql)
                print(f"✅ 已创建索引 {name}")
            else:
                print(f"✅ 索引 {name} 已存在")

    except Exception as e:
        print(f"❌ 创建 password_reset_tokens 表时出错: {e}")
        return False

    return True


def check_and_add_user_role_column():
    """为 users 表添加 role 列（幂等）。"""
    conn = get_db_connection()

    try:
        result = conn.query(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'role'
            """
        )

        if not result:
            print("users 表缺少 role 列，开始添加...")
            conn.execute(
                """
                ALTER TABLE users
                ADD COLUMN role TEXT
                """
            )
            print("✅ 已添加 role 列")
        else:
            print("✅ users 表已包含 role 列，无需添加")

        # 确保在更新数据前移除旧的检查约束
        try:
            conn.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
        except Exception as e:
            print(f"❌ 移除旧的 role 检查约束失败: {e}")
            return False

        # 回填历史数据为默认值（避免 NULL/非法值）
        conn.execute(
            """
            UPDATE users
            SET role = 'user'
            WHERE role IS NULL OR role = '' OR role NOT IN ('admin', 'user')
            """
        )

        # 更新默认值和检查约束
        try:
            conn.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE users ALTER COLUMN role SET NOT NULL")
        except Exception:
            pass

        try:
            conn.execute(
                "ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('admin','user'))"
            )
        except Exception as e:
            print(f"⚠️ 更新 role 检查约束失败: {e}")

        # 创建索引（如果不存在）
        index_result = conn.query(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'users' AND indexname = 'idx_users_role'
            """
        )
        if not index_result:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            print("✅ 已创建 idx_users_role 索引")
        else:
            print("✅ idx_users_role 索引已存在")

    except Exception as e:
        print(f"❌ 添加 role 列时出错: {e}")
        return False

    return True


def check_and_add_user_phone_unique():
    """为 users 表添加 phone 列及唯一索引（幂等）。"""
    conn = get_db_connection()
    try:
        column_result = conn.query(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'phone'
            """
        )
        if not column_result:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            print("✅ 已添加 users.phone 列")
        else:
            print("✅ users.phone 列已存在")

        # 唯一索引
        index_result = conn.query(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'users' AND indexname = 'idx_users_phone_unique'
            """
        )
        if not index_result:
            conn.execute("CREATE UNIQUE INDEX idx_users_phone_unique ON users(phone) WHERE phone IS NOT NULL")
            print("✅ 已创建 users.phone 唯一索引")
        else:
            print("✅ users.phone 唯一索引已存在")
    except Exception as e:
        print(f"❌ 添加 users.phone 唯一索引时出错: {e}")
        return False
    return True


def check_and_create_folders():
    """检查并创建 folders 表及 documents.folder_id 列。"""
    conn = get_db_connection()
    try:
        table_result = conn.query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'folders'
            """
        )
        if not table_result:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    id BIGSERIAL PRIMARY KEY,
                    owner_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP NOT NULL DEFAULT now(),
                    UNIQUE(owner_id, name)
                )
                """
            )
            print("✅ folders 表已创建")
        else:
            print("✅ folders 表已存在")

        column_result = conn.query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'documents' AND column_name = 'folder_id'
            """
        )
        if not column_result:
            conn.execute("ALTER TABLE documents ADD COLUMN folder_id BIGINT NULL")
            print("✅ 已为 documents 添加 folder_id 列")
        else:
            print("✅ documents.folder_id 列已存在")

        fk_index = conn.query(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'documents' AND indexname = 'idx_documents_folder_id'
            """
        )
        if not fk_index:
            conn.execute("CREATE INDEX idx_documents_folder_id ON documents(folder_id)")
            print("✅ 已创建 documents.folder_id 索引")
        else:
            print("✅ documents.folder_id 索引已存在")
    except Exception as e:
        print(f"❌ 创建 folders 相关结构时出错: {e}")
        return False
    return True


def check_and_update_tasks_table():
    """确保 tasks 表包含 status/updated_at/completed_at 列。"""
    conn = get_db_connection()
    try:
        # status
        status_col = conn.query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'tasks' AND column_name = 'status'
            """
        )
        if not status_col:
            conn.execute("ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'TODO'")
            print("✅ 已添加 tasks.status 列")
        # updated_at
        updated_col = conn.query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'tasks' AND column_name = 'updated_at'
            """
        )
        if not updated_col:
            conn.execute("ALTER TABLE tasks ADD COLUMN updated_at TIMESTAMP NULL")
            conn.execute("UPDATE tasks SET updated_at = COALESCE(created_at, now()) WHERE updated_at IS NULL")
            print("✅ 已添加 tasks.updated_at 列并回填")
        # completed_at
        completed_col = conn.query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'tasks' AND column_name = 'completed_at'
            """
        )
        if not completed_col:
            conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TIMESTAMP NULL")
            print("✅ 已添加 tasks.completed_at 列")
    except Exception as e:
        print(f"❌ 更新 tasks 表结构失败: {e}")
        return False
    return True


def check_and_create_user_events():
    """检查并创建 user_events 表。"""
    conn = get_db_connection()
    try:
        table_result = conn.query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'user_events'
            """
        )
        if not table_result:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_events (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    event_type TEXT NOT NULL,
                    document_id BIGINT NULL,
                    meta TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            print("✅ user_events 表已创建")
        else:
            print("✅ user_events 表已存在")

        idx = conn.query(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'user_events' AND indexname = 'idx_user_events_user_created'
            """
        )
        if not idx:
            conn.execute("CREATE INDEX idx_user_events_user_created ON user_events(user_id, created_at)")
            print("✅ 已创建 user_events 索引")
    except Exception as e:
        print(f"❌ 创建 user_events 表失败: {e}")
        return False
    return True


def check_and_create_audit_logs_table():
    """检查并创建 audit_logs 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'audit_logs'
            """
        )

        if not table_result:
            print("audit_logs 表不存在，开始创建...")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NULL,
                    resource_id BIGINT NULL,
                    ip TEXT NULL,
                    user_agent TEXT NULL,
                    meta_json TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            print("✅ audit_logs 表已创建")
        else:
            print("✅ audit_logs 表已存在")

        indexes = {
            "idx_audit_logs_user_created": "CREATE INDEX idx_audit_logs_user_created ON audit_logs (user_id, created_at)",
            "idx_audit_logs_action_created": "CREATE INDEX idx_audit_logs_action_created ON audit_logs (action, created_at)",
            "idx_audit_logs_resource": "CREATE INDEX idx_audit_logs_resource ON audit_logs (resource_type, resource_id)",
        }

        for index_name, create_sql in indexes.items():
            index_result = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'audit_logs' AND indexname = %s
                """,
                (index_name,),
            )
            if not index_result:
                conn.execute(create_sql)
                print(f"✅ 已创建索引 {index_name}")
            else:
                print(f"✅ 索引 {index_name} 已存在")

    except Exception as e:
        print(f"❌ 检查 audit_logs 表时出错: {e}")
        return False

    return True


def check_and_create_user_feedback_table():
    """检查并创建 user_feedback 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'user_feedback'
            """
        )

        if not table_result:
            print("user_feedback 表不存在，开始创建...")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NULL,
                    rating INT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            print("✅ user_feedback 表已创建")
        else:
            print("✅ user_feedback 表已存在")

        indexes = {
            "idx_user_feedback_created": "CREATE INDEX idx_user_feedback_created ON user_feedback (created_at)",
            "idx_user_feedback_user_created": "CREATE INDEX idx_user_feedback_user_created ON user_feedback (user_id, created_at)",
        }

        for index_name, create_sql in indexes.items():
            index_result = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'user_feedback' AND indexname = %s
                """,
                (index_name,),
            )
            if not index_result:
                conn.execute(create_sql)
                print(f"✅ 已创建索引 {index_name}")
            else:
                print(f"✅ 索引 {index_name} 已存在")

    except Exception as e:
        print(f"❌ 检查 user_feedback 表时出错: {e}")
        return False

    return True


def check_and_create_satisfaction_surveys_table():
    """检查并创建 satisfaction_surveys 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'satisfaction_surveys'
            """,
        )

        if not table_result:
            print("satisfaction_surveys 表不存在，开始创建...")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS satisfaction_surveys (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    rating INT NOT NULL,
                    comment TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """,
            )
            print("✅ satisfaction_surveys 表已创建")
        else:
            print("✅ satisfaction_surveys 表已存在")

        indexes = {
            "idx_satisfaction_user_created": "CREATE INDEX idx_satisfaction_user_created ON satisfaction_surveys (user_id, created_at)",
            "idx_satisfaction_rating": "CREATE INDEX idx_satisfaction_rating ON satisfaction_surveys (rating)",
        }

        for index_name, create_sql in indexes.items():
            index_result = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'satisfaction_surveys' AND indexname = %s
                """,
                (index_name,),
            )
            if not index_result:
                conn.execute(create_sql)
                print(f"✅ 已创建索引 {index_name}")
            else:
                print(f"✅ 索引 {index_name} 已存在")
    except Exception as e:
        print(f"❌ 检查 satisfaction_surveys 表时出错: {e}")
        return False

    return True


def check_and_create_system_settings_table():
    """检查并创建 system_settings 表（幂等）。"""
    conn = get_db_connection()

    try:
        table_result = conn.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'system_settings'
            """
        )

        if not table_result:
            print("system_settings 表不存在，开始创建...")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            print("✅ system_settings 表已创建")
        else:
            print("✅ system_settings 表已存在")

    except Exception as e:
        print(f"❌ 检查 system_settings 表时出错: {e}")
        return False

    return True

def main():
    print("🔍 开始检查数据库表结构...")

    success1 = check_and_fix_comments_table()
    success2 = check_and_create_collaborators_table()
    success3 = check_and_create_notifications_table()
    success4 = check_and_create_document_tags_table()
    success5 = check_and_create_notification_settings_table()
    success6 = check_and_create_password_reset_tokens_table()
    success7 = check_and_add_user_role_column()
    success8 = check_and_add_user_phone_unique()
    success9 = check_and_create_audit_logs_table()
    success10 = check_and_create_user_feedback_table()
    success11 = check_and_create_system_settings_table()
    success12 = check_and_create_folders()
    success13 = check_and_update_tasks_table()
    success14 = check_and_create_user_events()
    success15 = check_and_create_satisfaction_surveys_table()

    if all([success1, success2, success3, success4, success5, success6, success7, success8, success9, success10, success11, success12, success13, success14, success15]):
        print("🎉 数据库自检完成")
    else:
        print("💥 数据库自检失败")
        sys.exit(1)

if __name__ == "__main__":
    main()