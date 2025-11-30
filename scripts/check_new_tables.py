#!/usr/bin/env python3
"""
数据库自检脚本：检查并创建所有必需的表
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_db_connection


def get_connection():
    """获取数据库连接"""
    return get_db_connection()


def check_and_create_verification_codes_table():
    """检查并创建 verification_codes 表"""
    conn = get_connection()
    try:
        result = conn.query(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'verification_codes'"
        )
        if not result:
            print("verification_codes 表不存在，开始创建...")
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_verification_codes_email ON verification_codes (email, code_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_verification_codes_phone ON verification_codes (phone, code_type)")
            print("✅ verification_codes 表已创建")
        else:
            print("✅ verification_codes 表已存在")
    except Exception as e:
        print(f"❌ 检查 verification_codes 表时出错: {e}")
        return False
    return True


def check_and_create_oauth_accounts_table():
    """检查并创建 oauth_accounts 表"""
    conn = get_connection()
    try:
        result = conn.query(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'oauth_accounts'"
        )
        if not result:
            print("oauth_accounts 表不存在，开始创建...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS oauth_accounts (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    provider VARCHAR(32) NOT NULL,
                    provider_user_id VARCHAR(255) NOT NULL,
                    access_token TEXT NULL,
                    refresh_token TEXT NULL,
                    expires_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP NOT NULL DEFAULT now(),
                    UNIQUE (provider, provider_user_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_oauth_accounts_user_id ON oauth_accounts (user_id)")
            print("✅ oauth_accounts 表已创建")
        else:
            print("✅ oauth_accounts 表已存在")
    except Exception as e:
        print(f"❌ 检查 oauth_accounts 表时出错: {e}")
        return False
    return True


def check_and_create_totp_secrets_table():
    """检查并创建 totp_secrets 表"""
    conn = get_connection()
    try:
        result = conn.query(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'totp_secrets'"
        )
        if not result:
            print("totp_secrets 表不存在，开始创建...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS totp_secrets (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL UNIQUE,
                    secret VARCHAR(64) NOT NULL,
                    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    backup_codes TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """)
            print("✅ totp_secrets 表已创建")
        else:
            print("✅ totp_secrets 表已存在")
    except Exception as e:
        print(f"❌ 检查 totp_secrets 表时出错: {e}")
        return False
    return True


def check_and_create_chat_messages_table():
    """检查并创建 chat_messages 表"""
    conn = get_connection()
    try:
        result = conn.query(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'chat_messages'"
        )
        if not result:
            print("chat_messages 表不存在，开始创建...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    document_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    content TEXT NOT NULL,
                    message_type VARCHAR(16) NOT NULL DEFAULT 'text',
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_document ON chat_messages (document_id, created_at)")
            print("✅ chat_messages 表已创建")
        else:
            print("✅ chat_messages 表已存在")
    except Exception as e:
        print(f"❌ 检查 chat_messages 表时出错: {e}")
        return False
    return True


def check_and_create_system_metrics_table():
    """检查并创建 system_metrics 表"""
    conn = get_connection()
    try:
        result = conn.query(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'system_metrics'"
        )
        if not result:
            print("system_metrics 表不存在，开始创建...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id BIGSERIAL PRIMARY KEY,
                    metric_name VARCHAR(64) NOT NULL,
                    metric_value DOUBLE PRECISION NOT NULL,
                    tags TEXT NULL,
                    recorded_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics (metric_name, recorded_at)")
            print("✅ system_metrics 表已创建")
        else:
            print("✅ system_metrics 表已存在")
    except Exception as e:
        print(f"❌ 检查 system_metrics 表时出错: {e}")
        return False
    return True


def main():
    print("🔍 开始检查数据库表结构...")
    print()
    
    results = []
    results.append(("verification_codes", check_and_create_verification_codes_table()))
    results.append(("oauth_accounts", check_and_create_oauth_accounts_table()))
    results.append(("totp_secrets", check_and_create_totp_secrets_table()))
    results.append(("chat_messages", check_and_create_chat_messages_table()))
    results.append(("system_metrics", check_and_create_system_metrics_table()))
    
    print()
    if all(r[1] for r in results):
        print("🎉 数据库自检完成，所有表已就绪")
    else:
        failed = [r[0] for r in results if not r[1]]
        print(f"💥 数据库自检失败，以下表创建失败: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
