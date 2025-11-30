"""
聊天服务 - 文档内实时聊天功能
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def create_chat_message(
    db,
    *,
    document_id: int,
    user_id: int,
    content: str,
    message_type: str = "text",
) -> Dict[str, Any]:
    """
    创建聊天消息
    
    Args:
        db: 数据库连接
        document_id: 文档ID
        user_id: 发送者ID
        content: 消息内容
        message_type: 消息类型 (text, image, file, system)
    
    Returns:
        创建的消息
    """
    db.execute(
        """
        INSERT INTO chat_messages (document_id, user_id, content, message_type)
        VALUES (%s, %s, %s, %s)
        """,
        (document_id, user_id, content, message_type)
    )
    
    # 获取刚插入的消息ID
    rows = db.query(
        """
        SELECT id, document_id, user_id, content, message_type, created_at
        FROM chat_messages
        WHERE document_id = %s AND user_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (document_id, user_id)
    )
    
    if rows:
        msg = rows[0]
        # 获取用户名
        user_rows = db.query(
            "SELECT username, avatar_url FROM users WHERE id = %s LIMIT 1",
            (user_id,)
        )
        username = user_rows[0][0] if user_rows else f"user_{user_id}"
        avatar_url = user_rows[0][1] if user_rows else None
        
        return {
            "id": msg[0],
            "document_id": msg[1],
            "user_id": msg[2],
            "username": username,
            "avatar_url": avatar_url,
            "content": msg[3],
            "message_type": msg[4],
            "created_at": msg[5],
        }
    
    return None


def list_chat_messages(
    db,
    document_id: int,
    before_id: Optional[int] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    获取聊天消息列表
    
    Args:
        db: 数据库连接
        document_id: 文档ID
        before_id: 获取此ID之前的消息（用于分页加载历史）
        limit: 返回数量
    
    Returns:
        消息列表（按时间倒序）
    """
    if before_id:
        rows = db.query(
            """
            SELECT m.id, m.document_id, m.user_id, m.content, m.message_type, m.created_at,
                   u.username, u.avatar_url
            FROM chat_messages m
            LEFT JOIN users u ON m.user_id = u.id
            WHERE m.document_id = %s AND m.id < %s
            ORDER BY m.id DESC
            LIMIT %s
            """,
            (document_id, before_id, limit)
        )
    else:
        rows = db.query(
            """
            SELECT m.id, m.document_id, m.user_id, m.content, m.message_type, m.created_at,
                   u.username, u.avatar_url
            FROM chat_messages m
            LEFT JOIN users u ON m.user_id = u.id
            WHERE m.document_id = %s
            ORDER BY m.id DESC
            LIMIT %s
            """,
            (document_id, limit)
        )
    
    messages = []
    for row in rows:
        messages.append({
            "id": row[0],
            "document_id": row[1],
            "user_id": row[2],
            "content": row[3],
            "message_type": row[4],
            "created_at": row[5],
            "username": row[6] or f"user_{row[2]}",
            "avatar_url": row[7],
        })
    
    # 反转顺序，使最新的在最后
    return list(reversed(messages))


def delete_chat_message(
    db,
    message_id: int,
    user_id: int,
    is_admin: bool = False,
) -> bool:
    """
    删除聊天消息（只能删除自己的，管理员可删除任意）
    """
    if is_admin:
        result = db.execute(
            "DELETE FROM chat_messages WHERE id = %s",
            (message_id,)
        )
    else:
        result = db.execute(
            "DELETE FROM chat_messages WHERE id = %s AND user_id = %s",
            (message_id, user_id)
        )
    
    return True


def get_chat_message(db, message_id: int) -> Optional[Dict[str, Any]]:
    """获取单条消息"""
    rows = db.query(
        """
        SELECT m.id, m.document_id, m.user_id, m.content, m.message_type, m.created_at,
               u.username, u.avatar_url
        FROM chat_messages m
        LEFT JOIN users u ON m.user_id = u.id
        WHERE m.id = %s
        LIMIT 1
        """,
        (message_id,)
    )
    
    if rows:
        row = rows[0]
        return {
            "id": row[0],
            "document_id": row[1],
            "user_id": row[2],
            "content": row[3],
            "message_type": row[4],
            "created_at": row[5],
            "username": row[6] or f"user_{row[2]}",
            "avatar_url": row[7],
        }
    
    return None
