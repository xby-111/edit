"""
评论服务：提供基础的评论查询与创建能力。
"""
from datetime import datetime
from typing import Dict, List, Optional
from datetime import datetime


def _escape(value: Optional[str]) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _row_to_comment(row) -> Dict:
    return {
        "id": row[0],
        "document_id": row[1],
        "user_id": row[2],
        "content": row[3],
        "range_start": row[4],
        "range_end": row[5],
        "parent_id": row[6],
        "mentions": row[7],
        "anchor_json": row[8] if len(row) > 10 else None,
        "created_at": row[9] if len(row) > 10 else row[8],
        "updated_at": row[10] if len(row) > 10 else row[9]
    }


def list_comments(db, document_id: int) -> List[Dict]:
    rows = db.query(
        f"""
        SELECT id, document_id, user_id, content, range_start, range_end, parent_id, mentions, anchor_json, created_at, updated_at
        FROM comments
        WHERE document_id = {document_id}
        ORDER BY created_at ASC
        """
    )
    return [_row_to_comment(row) for row in rows] if rows else []


def create_comment(
    db,
    document_id: int,
    user_id: int,
    content: str,
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
    parent_id: Optional[int] = None,
    mentions: Optional[str] = None,
    anchor_json: Optional[str] = None,
) -> Dict:
    content_safe = _escape(content)
    parent_safe = "NULL" if parent_id is None else parent_id
    mentions_safe = _escape(mentions) if mentions is not None else "NULL"
    range_start_value = "NULL" if range_start is None else range_start
    range_end_value = "NULL" if range_end is None else range_end
    anchor_safe = _escape(anchor_json) if anchor_json is not None else "NULL"
    now = datetime.utcnow()

    db.execute(
        f"""
        INSERT INTO comments (document_id, user_id, content, range_start, range_end, parent_id, mentions, anchor_json, created_at, updated_at)
        VALUES ({document_id}, {user_id}, {content_safe}, {range_start_value}, {range_end_value}, {parent_safe}, {mentions_safe}, {anchor_safe}, '{now}', '{now}')
        """
    )

    # openGauss INSERT ... RETURNING 支持有限，使用查询获取最新一条
    rows = db.query(
        f"""
        SELECT id, document_id, user_id, content, range_start, range_end, parent_id, mentions, anchor_json, created_at, updated_at
        FROM comments
        WHERE document_id = {document_id}
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = rows[0] if rows else None
    if not row:
        return {}
    
    return {
        "id": row[0],
        "document_id": row[1],
        "user_id": row[2],
        "content": row[3],
        "range_start": row[4],
        "range_end": row[5],
        "parent_id": row[6],
        "mentions": row[7],
        "created_at": row[8],
        "updated_at": row[9]
    }
