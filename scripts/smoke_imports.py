#!/usr/bin/env python3
"""
导入测试脚本 - 验证所有修改后的模块可以正常导入
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """测试关键模块导入"""
    tests = [
        ("app.services.user_service", "用户服务模块"),
        ("app.services.websocket_service", "WebSocket服务模块"),
        ("app.api.routers.ws", "WebSocket路由模块"),
        ("app.core.security", "安全模块"),
        ("app.db.session", "数据库会话模块"),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for module_name, description in tests:
        try:
            __import__(module_name)
            print(f"✅ {description} ({module_name}) - 导入成功")
            success_count += 1
        except Exception as e:
            print(f"❌ {description} ({module_name}) - 导入失败: {e}")
    
    print(f"\n导入测试完成: {success_count}/{total_count} 成功")
    return success_count == total_count

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)