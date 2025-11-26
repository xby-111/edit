#!/usr/bin/env python3
"""
数据库自检脚本：检查并修复 comments 表缺少的 updated_at 列
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_db_connection
from datetime import datetime

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    type VARCHAR(32) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    content TEXT NULL,
                    payload TEXT NULL,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            print("✅ notifications 表已创建")
        else:
            print("✅ notifications 表已存在")

        indexes = {
            "idx_notifications_user_created": "CREATE INDEX idx_notifications_user_created ON notifications (user_id, created_at DESC)",
            "idx_notifications_user_unread": "CREATE INDEX idx_notifications_user_unread ON notifications (user_id, is_read, created_at DESC)",
            "idx_notifications_user_type": "CREATE INDEX idx_notifications_user_type ON notifications (user_id, type, created_at DESC)",
        }

        for index_name, create_sql in indexes.items():
            # 使用参数化查询，兼容层会处理占位符转换
            index_result = conn.query(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'notifications' AND indexname = %s
                """,
                (index_name,)
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
    success4 = check_and_add_user_role_column()
    success5 = check_and_create_audit_logs_table()
    success6 = check_and_create_user_feedback_table()
    success7 = check_and_create_system_settings_table()

    if success1 and success2 and success3 and success4 and success5 and success6 and success7:
        print("🎉 数据库自检完成")
    else:
        print("💥 数据库自检失败")
        sys.exit(1)

if __name__ == "__main__":
    main()