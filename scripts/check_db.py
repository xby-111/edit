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

def main():
    print("🔍 开始检查数据库表结构...")
    
    success1 = check_and_fix_comments_table()
    success2 = check_and_create_collaborators_table()
    
    if success1 and success2:
        print("🎉 数据库自检完成")
    else:
        print("💥 数据库自检失败")
        sys.exit(1)

if __name__ == "__main__":
    main()