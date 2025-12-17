#!/usr/bin/env python3
"""
快速诊断脚本 - 检查系统持久化机制是否正常

用途:
1. 验证数据库连接和事务提交
2. 检查后台保存任务是否运行
3. 测试 update_document_internal 是否正确提交

使用方法:
    python scripts/diagnose_persistence.py
"""

import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_db_connection, close_connection_safely
from app.services.document_service import update_document_internal, TABLE_DOCUMENTS


def test_database_commit():
    """测试数据库事务提交"""
    print("=" * 60)
    print("🧪 测试 1: 数据库事务提交")
    print("=" * 60)
    
    db = None
    test_doc_id = None
    
    try:
        db = get_db_connection()
        
        # 创建测试文档
        print("📝 创建测试文档...")
        db.execute(
            f"""
            INSERT INTO {TABLE_DOCUMENTS} (owner_id, title, content, status, created_at, updated_at)
            VALUES (1, '持久化测试文档', '<p>初始内容</p>', 'active', NOW(), NOW())
            RETURNING id
            """,
            ()
        )
        result = db.fetchone()
        test_doc_id = result[0]
        db.commit()
        print(f"✅ 测试文档创建成功 (ID: {test_doc_id})")
        
        # 测试 update_document_internal
        print("\n🔄 测试 update_document_internal...")
        test_content = f"<p>测试内容 - {time.time()}</p>"
        success = update_document_internal(db, test_doc_id, test_content)
        
        if success:
            print("✅ update_document_internal 返回成功")
        else:
            print("❌ update_document_internal 返回失败")
            return False
        
        # 验证内容是否真的写入
        print("\n🔍 验证内容是否持久化...")
        db2 = get_db_connection()  # 新连接验证
        rows = db2.query(
            f"SELECT content FROM {TABLE_DOCUMENTS} WHERE id = %s",
            (test_doc_id,)
        )
        
        if rows and rows[0][0] == test_content:
            print("✅ 内容已成功持久化到数据库!")
        else:
            print("❌ 内容未持久化或不匹配!")
            print(f"   期望: {test_content}")
            print(f"   实际: {rows[0][0] if rows else 'NULL'}")
            close_connection_safely(db2)
            return False
        
        close_connection_safely(db2)
        
        # 清理测试文档
        print("\n🧹 清理测试文档...")
        db.execute(f"DELETE FROM {TABLE_DOCUMENTS} WHERE id = %s", (test_doc_id,))
        db.commit()
        print("✅ 清理完成")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            close_connection_safely(db)


async def test_background_task():
    """测试后台保存任务是否运行"""
    print("\n" + "=" * 60)
    print("🧪 测试 2: 后台保存任务")
    print("=" * 60)
    
    try:
        from app.api.routers import ws
        
        if not hasattr(ws, 'manager'):
            print("❌ ws.manager 不存在!")
            return False
        
        manager = ws.manager
        print(f"✅ ConnectionManager 实例存在")
        
        # 检查后台任务
        if hasattr(manager, '_background_task') and manager._background_task:
            print(f"✅ 后台任务对象存在")
            if manager._background_task.done():
                print(f"❌ 后台任务已结束! (可能崩溃了)")
                try:
                    await manager._background_task
                except Exception as e:
                    print(f"   任务异常: {e}")
                return False
            else:
                print(f"✅ 后台任务正在运行")
                return True
        else:
            print(f"❌ 后台任务未启动!")
            print(f"   提示: 检查 app/main.py 中的 on_startup 是否正确启动任务")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dirty_docs_mechanism():
    """测试脏文档标记机制"""
    print("\n" + "=" * 60)
    print("🧪 测试 3: 脏文档标记机制")
    print("=" * 60)
    
    try:
        from app.api.routers import ws
        
        manager = ws.manager
        
        # 检查 dirty_docs 集合
        print(f"📋 当前脏文档列表: {manager.dirty_docs}")
        print(f"   数量: {len(manager.dirty_docs)}")
        
        if len(manager.dirty_docs) > 0:
            print(f"⚠️ 有 {len(manager.dirty_docs)} 个文档待保存:")
            for doc_id in manager.dirty_docs:
                print(f"   - 文档 {doc_id}")
        else:
            print(f"✅ 无待保存文档 (正常状态)")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    print("🔬 系统持久化诊断工具")
    print()
    
    # 测试 1: 数据库提交
    test1_passed = test_database_commit()
    
    # 测试 2: 后台任务 (需要 async)
    try:
        loop = asyncio.get_event_loop()
        test2_passed = loop.run_until_complete(test_background_task())
    except Exception as e:
        print(f"❌ 后台任务测试失败: {e}")
        test2_passed = False
    
    # 测试 3: 脏文档机制
    test3_passed = test_dirty_docs_mechanism()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 诊断总结")
    print("=" * 60)
    
    results = {
        "数据库事务提交": test1_passed,
        "后台保存任务": test2_passed,
        "脏文档标记机制": test3_passed,
    }
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✅ 所有测试通过! 持久化机制正常")
    else:
        print("\n❌ 部分测试失败! 需要修复以下问题:")
        for test_name, passed in results.items():
            if not passed:
                print(f"  - {test_name}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
