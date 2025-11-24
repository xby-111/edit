import sys
sys.path.append('D:/Projects/edit')

from app.db.session import conn

# 查询用户表
try:
    rows = conn.query("SELECT id, username, email FROM users LIMIT 10")
    print(f"用户表数据: {rows}")
    
    # 查询特定用户
    rows = conn.query("SELECT id, username, hashed_password FROM users WHERE username = 'test1' LIMIT 1")
    print(f"test1用户数据: {rows}")
    
except Exception as e:
    print(f"查询失败: {e}")
    import traceback
    traceback.print_exc()