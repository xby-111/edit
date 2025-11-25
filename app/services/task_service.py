"""
任务服务：提供基础的任务查询、创建与状态更新。
"""
from datetime import datetime
from typing import Dict, List, Optional


def _escape(value: Optional[str]) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _row_to_task(row) -> Dict:
    return {
        "id": row[0],
        "document_id": row[1],
        "creator_id": row[2],
        "created_by": row[2],  # 映射为 created_by 以满足 schema 要求
        "assignee_id": row[3],
        "title": row[4],
        "description": row[5],
        "status": row[6],
        "due_at": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def list_tasks(db, document_id: int) -> List[Dict]:
    rows = db.query(
        f"""
        SELECT id, document_id, creator_id, assignee_id, title, description, status, due_at, created_at, updated_at
        FROM tasks
        WHERE document_id = {document_id}
        ORDER BY created_at ASC
        """
    )
    return [_row_to_task(row) for row in rows] if rows else []


def create_task(
    db,
    document_id: int,
    creator_id: int,
    title: str,
    description: Optional[str] = None,
    assignee_id: Optional[int] = None,
    due_at: Optional[str] = None,
) -> Dict:
    title_safe = _escape(title)
    description_safe = _escape(description) if description is not None else "NULL"
    assignee_value = "NULL" if assignee_id is None else assignee_id
    due_value = _escape(due_at) if due_at else "NULL"

    db.execute(
        f"""
        INSERT INTO tasks (document_id, creator_id, assignee_id, title, description, status, due_at, created_at, updated_at)
        VALUES ({document_id}, {creator_id}, {assignee_value}, {title_safe}, {description_safe}, 'TODO', {due_value}, '{datetime.utcnow()}', '{datetime.utcnow()}')
        """
    )

    rows = db.query(
        f"""
        SELECT id, document_id, creator_id, assignee_id, title, description, status, due_at, created_at, updated_at
        FROM tasks
        WHERE document_id = {document_id}
        ORDER BY id DESC
        LIMIT 1
        """
    )
    return _row_to_task(rows[0]) if rows else {}


def update_task(db, task_id: int, status: Optional[str] = None, due_at: Optional[str] = None, assignee_id: Optional[int] = None) -> Dict:
    set_clauses = []
    if status is not None:
        set_clauses.append(f"status = {_escape(status)}")
    if due_at is not None:
        set_clauses.append(f"due_at = {_escape(due_at)}")
    if assignee_id is not None:
        set_clauses.append(f"assignee_id = {assignee_id}")
    set_clauses.append(f"updated_at = '{datetime.utcnow()}'")

    if not set_clauses:
        return {}

    set_sql = ", ".join(set_clauses)
    db.execute(
        f"""
        UPDATE tasks
        SET {set_sql}
        WHERE id = {task_id}
        """
    )

    rows = db.query(
        f"""
        SELECT id, document_id, creator_id, assignee_id, title, description, status, due_at, created_at, updated_at
        FROM tasks
        WHERE id = {task_id}
        LIMIT 1
        """
    )
    return _row_to_task(rows[0]) if rows else {}
