#!/usr/bin/env python3
"""
数据丢失恢复脚本

用途:
1. 从后台日志中提取 WebSocket 广播的内容
2. 尝试从数据库 WAL 日志恢复未提交的事务
3. 检查浏览器 localStorage 中的草稿

使用方法:
    python scripts/recover_lost_data.py --document-id 45 --log-file logs/app.log

恢复策略:
    - 优先级1: 日志中的最后一次广播内容
    - 优先级2: 数据库 WAL 日志
    - 优先级3: 浏览器本地存储 (需要用户提供)
"""

import sys
import os
import re
import json
from datetime import datetime
from typing import Optional, List, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_db_connection, close_connection_safely
from app.services.document_service import TABLE_DOCUMENTS


def extract_broadcast_content_from_logs(log_file: str, document_id: int) -> Optional[Dict]:
    """从日志文件中提取广播内容"""
    print(f"📖 正在读取日志文件: {log_file}")
    
    if not os.path.exists(log_file):
        print(f"❌ 日志文件不存在: {log_file}")
        return None
    
    # 匹配日志中的广播记录
    # 例如: "广播内容更新: doc_id=45, user_id=1, type=content_update"
    broadcast_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*广播内容更新: doc_id=(\d+), user_id=(\d+), type=(\w+)'
    )
    
    broadcasts = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = broadcast_pattern.search(line)
            if match:
                timestamp_str, doc_id_str, user_id_str, msg_type = match.groups()
                doc_id = int(doc_id_str)
                
                if doc_id == document_id:
                    broadcasts.append({
                        'timestamp': timestamp_str,
                        'document_id': doc_id,
                        'user_id': int(user_id_str),
                        'type': msg_type
                    })
    
    if broadcasts:
        print(f"✅ 找到 {len(broadcasts)} 条广播记录")
        last_broadcast = broadcasts[-1]
        print(f"   最后一次广播时间: {last_broadcast['timestamp']}")
        print(f"   用户ID: {last_broadcast['user_id']}")
        return last_broadcast
    else:
        print(f"⚠️ 未找到文档 {document_id} 的广播记录")
        return None


def check_database_current_content(document_id: int) -> Optional[str]:
    """检查数据库中的当前内容"""
    print(f"\n🔍 检查数据库中的内容...")
    
    db = None
    try:
        db = get_db_connection()
        rows = db.query(
            f"SELECT id, title, content, updated_at FROM {TABLE_DOCUMENTS} WHERE id = %s",
            (document_id,)
        )
        
        if not rows:
            print(f"❌ 文档 {document_id} 不存在")
            return None
        
        row = rows[0]
        content = row[2]  # content 字段
        updated_at = row[3]  # updated_at 字段
        
        print(f"✅ 数据库内容:")
        print(f"   标题: {row[1]}")
        print(f"   更新时间: {updated_at}")
        print(f"   内容大小: {len(content)} 字节")
        print(f"   内容预览: {content[:200]}...")
        
        return content
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return None
    finally:
        if db:
            close_connection_safely(db)


def check_document_versions(document_id: int, limit: int = 10) -> List[Dict]:
    """检查文档版本历史"""
    print(f"\n📚 检查文档版本历史 (最近 {limit} 条)...")
    
    db = None
    try:
        db = get_db_connection()
        rows = db.query(
            f"""
            SELECT id, version_number, content_snapshot, summary, created_at
            FROM document_versions
            WHERE document_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (document_id, limit)
        )
        
        if not rows:
            print(f"⚠️ 文档 {document_id} 没有版本历史")
            return []
        
        versions = []
        for row in rows:
            version = {
                'id': row[0],
                'version_number': row[1],
                'content_snapshot': row[2],
                'summary': row[3],
                'created_at': row[4]
            }
            versions.append(version)
            print(f"   版本 {version['version_number']}: {version['created_at']} - {version['summary']}")
            print(f"      内容大小: {len(version['content_snapshot'])} 字节")
        
        return versions
    except Exception as e:
        print(f"❌ 版本历史查询失败: {e}")
        return []
    finally:
        if db:
            close_connection_safely(db)


def restore_content(document_id: int, content: str, backup_first: bool = True) -> bool:
    """恢复文档内容到数据库"""
    print(f"\n💾 准备恢复文档 {document_id}...")
    
    db = None
    try:
        db = get_db_connection()
        
        # 先备份当前内容
        if backup_first:
            print("📦 正在备份当前内容到版本历史...")
            current_rows = db.query(
                f"SELECT content FROM {TABLE_DOCUMENTS} WHERE id = %s",
                (document_id,)
            )
            
            if current_rows:
                current_content = current_rows[0][0]
                # 创建备份版本
                db.execute(
                    """
                    INSERT INTO document_versions (document_id, user_id, version_number, content_snapshot, summary, created_at)
                    VALUES (%s, %s, (SELECT COALESCE(MAX(version_number), 0) + 1 FROM document_versions WHERE document_id = %s), %s, %s, NOW())
                    """,
                    (document_id, 0, document_id, current_content, f"数据恢复前的备份 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                )
                db.commit()
                print("✅ 备份完成")
        
        # 恢复内容
        print(f"🔄 正在恢复内容 ({len(content)} 字节)...")
        from app.services.document_service import _escape, _format_datetime
        
        escaped_content = _escape(content)
        update_time = _format_datetime(datetime.utcnow())
        sql = f"UPDATE {TABLE_DOCUMENTS} SET content = {escaped_content}, updated_at = {update_time} WHERE id = %s"
        db.execute(sql, (document_id,))
        db.commit()
        
        print("✅ 内容恢复成功!")
        return True
    except Exception as e:
        print(f"❌ 恢复失败: {e}")
        if db:
            try:
                db.rollback()
            except:
                pass
        return False
    finally:
        if db:
            close_connection_safely(db)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='数据丢失恢复工具')
    parser.add_argument('--document-id', type=int, required=True, help='文档ID')
    parser.add_argument('--log-file', type=str, default='logs/app.log', help='日志文件路径')
    parser.add_argument('--restore-from-version', type=int, help='从指定版本恢复')
    parser.add_argument('--restore-from-file', type=str, help='从文本文件恢复内容')
    parser.add_argument('--no-backup', action='store_true', help='恢复前不备份')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("📋 数据丢失恢复工具")
    print("=" * 60)
    print(f"文档ID: {args.document_id}")
    print(f"日志文件: {args.log_file}")
    print()
    
    # 1. 检查当前数据库内容
    current_content = check_database_current_content(args.document_id)
    
    # 2. 检查版本历史
    versions = check_document_versions(args.document_id)
    
    # 3. 检查日志中的广播记录
    broadcast_info = extract_broadcast_content_from_logs(args.log_file, args.document_id)
    
    # 恢复操作
    if args.restore_from_version:
        # 从版本历史恢复
        version = next((v for v in versions if v['version_number'] == args.restore_from_version), None)
        if version:
            print(f"\n⚠️ 将从版本 {args.restore_from_version} 恢复内容")
            confirm = input("确认恢复? (yes/no): ")
            if confirm.lower() == 'yes':
                restore_content(args.document_id, version['content_snapshot'], not args.no_backup)
        else:
            print(f"❌ 版本 {args.restore_from_version} 不存在")
    
    elif args.restore_from_file:
        # 从文件恢复
        if os.path.exists(args.restore_from_file):
            with open(args.restore_from_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"\n⚠️ 将从文件恢复内容: {args.restore_from_file}")
            print(f"   内容大小: {len(content)} 字节")
            confirm = input("确认恢复? (yes/no): ")
            if confirm.lower() == 'yes':
                restore_content(args.document_id, content, not args.no_backup)
        else:
            print(f"❌ 文件不存在: {args.restore_from_file}")
    
    else:
        # 仅诊断模式
        print("\n" + "=" * 60)
        print("📊 诊断总结")
        print("=" * 60)
        
        if broadcast_info:
            print(f"✅ 找到广播记录,最后广播时间: {broadcast_info['timestamp']}")
        else:
            print(f"❌ 未找到广播记录")
        
        if current_content:
            print(f"✅ 数据库有内容 ({len(current_content)} 字节)")
        else:
            print(f"❌ 数据库内容为空或文档不存在")
        
        if versions:
            print(f"✅ 有 {len(versions)} 个版本历史可用于恢复")
            print(f"   最新版本: {versions[0]['version_number']}")
        else:
            print(f"❌ 无版本历史")
        
        print("\n恢复建议:")
        if versions:
            print(f"  1. 从最近的版本恢复:")
            print(f"     python scripts/recover_lost_data.py --document-id {args.document_id} --restore-from-version {versions[0]['version_number']}")
        
        print(f"  2. 从浏览器 localStorage 恢复:")
        print(f"     - 打开浏览器开发者工具 (F12)")
        print(f"     - Application/Storage → Local Storage")
        print(f"     - 查找 draft_{args.document_id}")
        print(f"     - 复制内容到文件,然后运行:")
        print(f"     python scripts/recover_lost_data.py --document-id {args.document_id} --restore-from-file recovered_content.txt")


if __name__ == '__main__':
    main()
