"""
文档服务层 - 使用 py-opengauss 直接 SQL 操作

本模块提供文档、文档版本、模板等相关的数据库操作服务。
所有函数都使用原生 SQL 与 py-opengauss 进行交互。
"""
import difflib
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.schemas import DocumentCreate, DocumentUpdate, TemplateCreate, TemplateUpdate
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

# ==================== 常量定义 ====================

# 表名
TABLE_DOCUMENTS = "documents"
TABLE_DOCUMENT_VERSIONS = "document_versions"
TABLE_DOCUMENT_TEMPLATES = "document_templates"
TABLE_DOCUMENT_REVISIONS = "document_revisions"

# 文档状态
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

# 排序字段白名单
VALID_SORT_FIELDS = ["title", "created_at", "updated_at"]

# 文档字段列表（用于 SELECT 查询）
DOCUMENT_FIELDS = "id, owner_id, title, content, status, folder_name, folder_id, tags, is_locked, locked_by, created_at, updated_at"

# 模板字段列表
TEMPLATE_FIELDS = "id, name, description, content, category, is_active, created_at, updated_at"

# 版本字段列表
VERSION_FIELDS = "id, document_id, user_id, version_number, content_snapshot, summary, created_at"

# 版本历史字段
REVISION_FIELDS = "id, document_id, created_at, created_by, title, content, content_hash, reason"


# ==================== 私有辅助函数 ====================

def _escape(value: Optional[str]) -> str:
    """
    转义 SQL 字符串值，防止 SQL 注入
    
    Args:
        value: 待转义的字符串值，可为 None
        
    Returns:
        转义后的 SQL 字符串表达式（如 'value' 或 NULL）
    """
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"


def _format_bool(value: Optional[bool]) -> str:
    """
    格式化布尔值为 SQL 表达式
    
    Args:
        value: 布尔值，可为 None
        
    Returns:
        SQL 布尔表达式（TRUE/FALSE/NULL）
    """
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"


def _format_datetime(dt: Optional[datetime | str]) -> str:
    """
    格式化日期时间为 SQL 字符串
    
    Args:
        dt: datetime 对象或日期字符串，可为 None
        
    Returns:
        SQL 日期时间字符串表达式
    """
    if dt is None:
        return "NULL"
    if isinstance(dt, str):
        # 如果是字符串，直接使用（假设已经是正确格式）
        return f"'{dt}'"
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def _row_to_document_dict(row) -> Dict:
    """
    将数据库查询结果行转换为文档字典
    
    Args:
        row: 数据库查询结果行（元组）
        
    Returns:
        文档字典，包含所有文档字段
    """
    return {
        'id': row[0],
        'owner_id': row[1],
        'title': row[2],
        'content': row[3],
        'status': row[4],
        'folder_name': row[5] if len(row) > 5 else None,
        'folder_id': row[6] if len(row) > 6 else None,
        'tags': row[7] if len(row) > 7 else None,
        'is_locked': row[8] if len(row) > 8 else None,
        'locked_by': row[9] if len(row) > 9 else None,
        'created_at': row[10] if len(row) > 10 else (row[9] if len(row) > 9 else None),
        'updated_at': row[11] if len(row) > 11 else (row[10] if len(row) > 10 else None)
    }


def _row_to_template_dict(row) -> Dict:
    """
    将数据库查询结果行转换为模板字典
    
    Args:
        row: 数据库查询结果行（元组）
        
    Returns:
        模板字典，包含所有模板字段
    """
    return {
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'content': row[3],
        'category': row[4],
        'is_active': row[5],
        'created_at': row[6],
        'updated_at': row[7]
    }


def _row_to_revision_dict(row) -> Dict:
    return {
        'id': row[0],
        'document_id': row[1],
        'created_at': row[2],
        'created_by': row[3],
        'title': row[4],
        'content': row[5],
        'content_hash': row[6],
        'reason': row[7],
    }


def _row_to_version_dict(row) -> Dict:
    """
    将数据库查询结果行转换为版本字典
    
    Args:
        row: 数据库查询结果行（元组）
        
    Returns:
        版本字典，包含所有版本字段
    """
    return {
        'id': row[0],
        'document_id': row[1],
        'user_id': row[2],
        'version_number': row[3],
        'content_snapshot': row[4],
        'summary': row[5],
        'created_at': row[6]
    }


def _get_document_by_id_and_owner(db, document_id: int, owner_id: int) -> Optional[Dict]:
    """
    根据文档ID和所有者ID获取文档（私有辅助函数）
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 所有者ID
        
    Returns:
        文档字典，如果不存在则返回 None
    """
    rows = db.query(
        f"SELECT {DOCUMENT_FIELDS} FROM {TABLE_DOCUMENTS} "
        f"WHERE id = {document_id} AND owner_id = {owner_id} LIMIT 1"
    )
    if rows:
        return _row_to_document_dict(rows[0])
    return None


def _get_template_by_id(db, template_id: int, active_only: bool = True) -> Optional[Dict]:
    """
    根据模板ID获取模板（私有辅助函数）
    
    Args:
        db: 数据库连接对象
        template_id: 模板ID
        active_only: 是否只查询激活的模板
        
    Returns:
        模板字典，如果不存在则返回 None
    """
    # 使用参数化查询避免SQL注入
    params = [template_id]
    where_clause = "WHERE id = %s"
    if active_only:
        where_clause += " AND is_active = TRUE"
    
    rows = db.query(
        f"SELECT {TEMPLATE_FIELDS} FROM {TABLE_DOCUMENT_TEMPLATES} {where_clause} LIMIT 1",
        tuple(params)
    )
    if rows:
        return _row_to_template_dict(rows[0])
    return None


def _extract_update_data(obj) -> Dict:
    """
    从 Pydantic 模型或普通对象中提取更新数据
    
    Args:
        obj: Pydantic 模型对象或普通对象
        
    Returns:
        包含更新字段的字典（排除未设置的字段）
    """
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(exclude_unset=True)
    elif hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items() if v is not None}
    return {}


def _build_update_clause(update_data: Dict, exclude_fields: List[str] = None) -> List[str]:
    """
    构建 SQL UPDATE 语句的 SET 子句
    
    Args:
        update_data: 更新数据字典
        exclude_fields: 需要排除的字段列表
        
    Returns:
        SET 子句字段列表，如 ["title = 'xxx'", "status = 'active'"]
    """
    if exclude_fields is None:
        exclude_fields = []
    
    update_fields = []
    for field, value in update_data.items():
        if field in exclude_fields:
            continue
        
        if field in ['title', 'content', 'status', 'name', 'description', 'category']:
            value_safe = _escape(value)
            update_fields.append(f"{field} = {value_safe}")
        elif field in ['folder_name', 'tags', 'summary']:
            value_safe = _escape(value) if value is not None else "NULL"
            update_fields.append(f"{field} = {value_safe}")
        elif field == 'is_active':
            value_safe = _format_bool(value)
            update_fields.append(f"{field} = {value_safe}")
        else:
            value_safe = _escape(str(value)) if value is not None else "NULL"
            update_fields.append(f"{field} = {value_safe}")
    
    return update_fields


def _refresh_document_tags_cache(db, document_id: int):
    try:
        rows = db.query(
            "SELECT tag FROM document_tags WHERE document_id = %s ORDER BY tag",
            (document_id,),
        )
        tags = [row[0] for row in rows] if rows else []
        tags_str = ",".join(tags)
        db.execute(
            f"UPDATE {TABLE_DOCUMENTS} SET tags = %s WHERE id = %s",
            (tags_str, document_id),
        )
    except Exception as e:
        logger.warning("刷新文档标签缓存失败: %s", e)


# ==================== 文档 CRUD 相关函数 ====================

def get_documents(
    db,
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
    folder: Optional[str] = None, 
    status: Optional[str] = None, 
    tag: Optional[str] = None
) -> List[Dict]:
    """
    获取文档列表
    
    Args:
        db: 数据库连接对象
        owner_id: 文档所有者ID
        skip: 跳过的记录数（分页）
        limit: 返回的最大记录数（分页）
        folder: 文件夹名称（可选筛选）
        status: 文档状态（可选筛选）
        tag: 标签（可选筛选，使用全文搜索）
        
    Returns:
        文档字典列表，按更新时间降序排列
    """
    where_conditions = [f"owner_id = {owner_id}"]
    
    if folder:
        folder_safe = _escape(folder)
        where_conditions.append(f"folder_name = {folder_safe}")
    
    if status:
        status_safe = _escape(status)
        where_conditions.append(f"status = {status_safe}")

    if tag:
        tag_query = _escape(tag)
        where_conditions.append(f"to_tsvector('simple', tags) @@ plainto_tsquery({tag_query})")

    where_clause = " WHERE " + " AND ".join(where_conditions)
    
    rows = db.query(
        f"SELECT {DOCUMENT_FIELDS} FROM {TABLE_DOCUMENTS}{where_clause} "
        f"ORDER BY updated_at DESC LIMIT {limit} OFFSET {skip}"
    )

    return [_row_to_document_dict(row) for row in rows]


def list_documents_for_user(
    db,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    folder: Optional[str] = None,
    folder_id: Optional[int] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    keyword: Optional[str] = None,
    owner: Optional[int] = None,
    sort: str = "updated_at",
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    updated_from: Optional[datetime] = None,
    updated_to: Optional[datetime] = None,
    author: Optional[str] = None,
) -> List[Dict]:
    fields = (
        "d.id, d.owner_id, d.title, d.content, d.status, d.folder_name, d.folder_id, d.tags, "
        "d.is_locked, d.locked_by, d.created_at, d.updated_at"
    )
    joins = ["LEFT JOIN document_collaborators dc ON d.id = dc.document_id"]
    params: List = [user_id, user_id]
    conditions = ["(d.owner_id = %s OR dc.user_id = %s)"]

    if tag:
        joins.append("INNER JOIN document_tags dt ON dt.document_id = d.id")
        conditions.append("dt.tag = %s")
        params.append(tag)

    if owner is not None:
        conditions.append("d.owner_id = %s")
        params.append(owner)

    if folder:
        conditions.append("d.folder_name = %s")
        params.append(folder)

    if folder_id is not None:
        conditions.append("d.folder_id = %s")
        params.append(folder_id)

    if status:
        conditions.append("d.status = %s")
        params.append(status)

    if keyword:
        conditions.append("(d.title ILIKE %s OR d.content ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    if created_from:
        conditions.append("d.created_at >= %s")
        params.append(created_from)

    if created_to:
        conditions.append("d.created_at <= %s")
        params.append(created_to)

    if updated_from:
        conditions.append("d.updated_at >= %s")
        params.append(updated_from)

    if updated_to:
        conditions.append("d.updated_at <= %s")
        params.append(updated_to)

    if author:
        if author.isdigit():
            conditions.append("d.owner_id = %s")
            params.append(int(author))
        else:
            joins.append("LEFT JOIN users u ON u.id = d.owner_id")
            conditions.append("(u.username ILIKE %s OR u.email ILIKE %s OR u.phone ILIKE %s)")
            like_author = f"%{author}%"
            params.extend([like_author, like_author, like_author])

    order_field = "updated_at"
    if sort == "created_at":
        order_field = "created_at"
    elif sort == "title":
        order_field = "title"

    sql = f"""
        SELECT DISTINCT {fields}
        FROM {TABLE_DOCUMENTS} d
        {' '.join(joins)}
        WHERE {' AND '.join(conditions)}
        ORDER BY d.{order_field} DESC
        LIMIT %s OFFSET %s
    """

    params.extend([limit, skip])
    rows = db.query(sql, tuple(params))
    return [_row_to_document_dict(row) for row in rows]


def add_document_tags(db, document_id: int, tags: List[str]) -> List[str]:
    clean_tags = []
    for t in tags or []:
        if t and isinstance(t, str) and t.strip():
            clean_tags.append(t.strip())

    if not clean_tags:
        return list_document_tags(db, document_id)

    for tag in clean_tags:
        db.execute(
            """
            INSERT INTO document_tags (document_id, tag, created_at)
            SELECT %s, %s, now()
            WHERE NOT EXISTS (
                SELECT 1 FROM document_tags WHERE document_id = %s AND tag = %s
            )
            """,
            (document_id, tag, document_id, tag),
        )

    _refresh_document_tags_cache(db, document_id)
    return list_document_tags(db, document_id)


def list_document_tags(db, document_id: int) -> List[str]:
    rows = db.query(
        "SELECT tag FROM document_tags WHERE document_id = %s ORDER BY tag",
        (document_id,),
    )
    return [row[0] for row in rows] if rows else []


def delete_document_tag(db, document_id: int, tag: str) -> None:
    db.execute(
        "DELETE FROM document_tags WHERE document_id = %s AND tag = %s",
        (document_id, tag),
    )
    _refresh_document_tags_cache(db, document_id)


def get_document(db, document_id: int, owner_id: int) -> Optional[Dict]:
    """
    获取单个文档详情
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 文档所有者ID（用于权限验证）
        
    Returns:
        文档字典，如果文档不存在或不属于该用户则返回 None
    """
    return _get_document_by_id_and_owner(db, document_id, owner_id)


def get_document_with_collaborators(db, document_id: int, user_id: int) -> Optional[Dict]:
    """
    获取文档详情（支持协作权限）
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        user_id: 用户ID
        
    Returns:
        文档字典，如果用户无权限则返回 None
    """
    # 首先检查是否为所有者
    doc = _get_document_by_id_and_owner(db, document_id, user_id)
    if doc:
        return doc
    
    # 检查是否为协作者
    collab_rows = db.query(f"""
        SELECT d.id, d.owner_id, d.title, d.content, d.status, d.folder_name, d.tags, 
               d.is_locked, d.locked_by, d.created_at, d.updated_at 
        FROM {TABLE_DOCUMENTS} d
        INNER JOIN document_collaborators dc ON d.id = dc.document_id
        WHERE d.id = {document_id} AND dc.user_id = {user_id}
    """)
    
    if collab_rows:
        return _row_to_document_dict(collab_rows[0])
    
    return None


def check_document_permission(db, document_id: int, user_id: int) -> Dict[str, bool]:
    """
    检查用户对文档的权限
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        user_id: 用户ID
        
    Returns:
        权限字典: {"can_view": bool, "can_edit": bool, "is_owner": bool}
    """
    # 匿名用户（user_id=0）允许查看，但不允许编辑
    if user_id == 0:
        # 检查文档是否存在
        owner_rows = db.query(f"""
            SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
        """)
        if owner_rows:
            return {"can_view": True, "can_edit": False, "is_owner": False}
        else:
            # 文档不存在，匿名用户也无权限
            return {"can_view": False, "can_edit": False, "is_owner": False}
    
    # 检查是否为所有者
    owner_rows = db.query(f"""
        SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
    """)
    
    if owner_rows and owner_rows[0][0] == user_id:
        return {"can_view": True, "can_edit": True, "is_owner": True}
    
    # 检查协作者权限
    collab_rows = db.query(f"""
        SELECT role FROM document_collaborators 
        WHERE document_id = {document_id} AND user_id = {user_id}
    """)
    
    if collab_rows:
        role = collab_rows[0][0]
        return {
            "can_view": True, 
            "can_edit": role == "editor",
            "is_owner": False
        }
    
    # 无权限
    return {"can_view": False, "can_edit": False, "is_owner": False}


def assert_document_access(db, document_id: int, current_user, required_role: str = "viewer"):
    """统一文档权限校验，基于协作角色和管理员角色。"""
    role_order = {"viewer": 0, "editor": 1, "owner": 2, "admin": 3}
    user_role = getattr(current_user, "role", "user") or "user"
    if user_role == "admin":
        return

    permission = check_document_permission(db, document_id, getattr(current_user, "id", 0))
    required_level = role_order.get(required_role, 0)
    # owner 权限
    if required_level >= role_order["owner"] and not permission.get("is_owner"):
        raise HTTPException(status_code=403, detail="无权访问文档")
    if required_level == role_order["editor"] and not permission.get("can_edit"):
        raise HTTPException(status_code=403, detail="无权编辑文档")
    if required_level == role_order["viewer"] and not permission.get("can_view"):
        raise HTTPException(status_code=403, detail="无权查看文档")


def is_document_owner(db, document_id: int, user_id: int) -> bool:
    """
    检查用户是否为文档所有者
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        user_id: 用户ID
        
    Returns:
        是否为所有者
    """
    owner_rows = db.query(f"""
        SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
    """)
    
    return owner_rows and owner_rows[0][0] == user_id


def add_collaborator(db, document_id: int, owner_id: int, collaborator_user_id: int, role: str = "editor") -> bool:
    """
    添加文档协作者
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 文档所有者ID
        collaborator_user_id: 协作者用户ID
        role: 协作者角色 (editor/viewer)
        
    Returns:
        是否添加成功
    """
    # 验证所有者权限
    owner_rows = db.query(f"""
        SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
    """)
    
    if not owner_rows or owner_rows[0][0] != owner_id:
        return False
    
    # 添加协作者
    try:
        role_safe = _escape(role)
        logger.info(f"尝试添加协作者: document_id={document_id}, user_id={collaborator_user_id}, role={role}")
        
        # 先检查是否已存在
        existing_rows = db.query(f"""
            SELECT 1 FROM document_collaborators 
            WHERE document_id = {document_id} AND user_id = {collaborator_user_id}
        """)
        
        if existing_rows:
            logger.info("协作者已存在，更新角色")
            # 更新现有记录
            db.execute(f"""
                UPDATE document_collaborators 
                SET role = {role_safe}
                WHERE document_id = {document_id} AND user_id = {collaborator_user_id}
            """)
        else:
            logger.info("插入新协作者记录")
            # 插入新记录
            now_sql = _format_datetime(datetime.utcnow())
            db.execute(f"""
                INSERT INTO document_collaborators (document_id, user_id, role, created_at)
                VALUES ({document_id}, {collaborator_user_id}, {role_safe}, {now_sql})
            """)
        
        logger.info("协作者添加成功")
        return True
    except Exception as e:
        logger.error(f"添加协作者失败: {e}", exc_info=True)
        return False


def batch_add_collaborators(db, document_id: int, owner_id: int, users: list) -> list:
    """
    批量添加文档协作者
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 文档所有者ID
        users: 用户列表 [{"username": "xxx", "role": "editor"}, ...]
        
    Returns:
        处理结果列表 [{"username": "xxx", "success": bool, "message": "xxx"}, ...]
    """
    # 验证所有者权限
    owner_rows = db.query(f"""
        SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
    """)
    
    if not owner_rows or owner_rows[0][0] != owner_id:
        return [{"username": user.get("username"), "success": False, "message": "无权限操作"} for user in users]
    
    results = []
    
    for user_data in users:
        username = user_data.get("username")
        role = user_data.get("role", "editor")
        
        if not username:
            results.append({"username": username, "success": False, "message": "用户名不能为空"})
            continue
            
        if role not in ["editor", "viewer"]:
            results.append({"username": username, "success": False, "message": "角色只能是 editor 或 viewer"})
            continue
        
        try:
            # 获取用户ID
            from app.services.user_service import _escape
            username_safe = _escape(username)
            user_rows = db.query("SELECT id FROM users WHERE username = %s LIMIT 1", (username,))
            
            if not user_rows:
                results.append({"username": username, "success": False, "message": "用户不存在"})
                continue
                
            user_id = user_rows[0][0]
            
            # 不能添加自己为协作者
            if user_id == owner_id:
                results.append({"username": username, "success": False, "message": "不能添加自己为协作者"})
                continue
            
            # 添加协作者
            success = add_collaborator(db, document_id, owner_id, user_id, role)
            if success:
                results.append({"username": username, "success": True, "message": "添加成功"})
            else:
                results.append({"username": username, "success": False, "message": "添加失败"})
                
        except Exception as e:
            logger.error(f"批量添加协作者 {username} 失败: {e}")
            results.append({"username": username, "success": False, "message": "处理异常"})
    
    return results


def remove_collaborator(db, document_id: int, owner_id: int, collaborator_user_id: int) -> bool:
    """
    移除文档协作者
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 文档所有者ID
        collaborator_user_id: 协作者用户ID
        
    Returns:
        是否移除成功
    """
    # 验证所有者权限
    owner_rows = db.query(f"""
        SELECT owner_id FROM {TABLE_DOCUMENTS} WHERE id = {document_id}
    """)
    
    if not owner_rows or owner_rows[0][0] != owner_id:
        return False
    
    try:
        db.execute(f"""
            DELETE FROM document_collaborators 
            WHERE document_id = {document_id} AND user_id = {collaborator_user_id}
        """)
        logger.info(f"协作者 {collaborator_user_id} 已从文档 {document_id} 移除")
        return True
    except Exception as e:
        logger.error(f"移除协作者失败: {e}")
        return False


def get_collaborators(db, document_id: int, user_id: int) -> list:
    """
    获取文档协作者列表
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        user_id: 当前用户ID（用于权限验证）
        
    Returns:
        协作者列表 [{"user_id": int, "username": str, "role": str, "created_at": str}, ...]
    """
    # 检查权限（所有者或协作者）
    permission = check_document_permission(db, document_id, user_id)
    
    if not permission["can_view"]:
        return []
    
    try:
        rows = db.query(f"""
            SELECT u.id as user_id, u.username, dc.role, dc.created_at
            FROM document_collaborators dc
            INNER JOIN users u ON dc.user_id = u.id
            WHERE dc.document_id = {document_id}
            ORDER BY dc.created_at ASC
        """)
        
        collaborators = []
        for row in rows:
            collaborators.append({
                "user_id": row[0],
                "username": row[1],
                "role": row[2],
                "created_at": row[3]
            })
        
        return collaborators
    except Exception as e:
        logger.error(f"获取协作者列表失败: {e}")
        return []


def get_shared_documents(db, user_id: int, skip: int = 0, limit: int = 100) -> List[Dict]:
    """
    获取用户共享的文档列表
    
    Args:
        db: 数据库连接对象
        user_id: 用户ID
        skip: 跳过的记录数
        limit: 返回的最大记录数
        
    Returns:
        文档字典列表
    """
    rows = db.query(f"""
        SELECT d.id, d.owner_id, d.title, d.content, d.status, d.folder_name, d.tags, 
               d.is_locked, d.locked_by, d.created_at, d.updated_at 
        FROM {TABLE_DOCUMENTS} d
        INNER JOIN document_collaborators dc ON d.id = dc.document_id
        WHERE dc.user_id = %s
        ORDER BY d.updated_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, limit, skip))
    
    return [_row_to_document_dict(row) for row in rows]


def create_document(db, document_data_or_schema, owner_id: int) -> Optional[Dict]:
    """
    创建新文档
    
    Args:
        db: 数据库连接对象
        document_data_or_schema: DocumentCreate 对象或字典，包含文档数据
        owner_id: 文档所有者ID
        
    Returns:
        创建的文档字典，包含生成的ID和时间戳；如果创建失败则返回 None
        
    Note:
        函数会自动设置 created_at 和 updated_at 为当前时间
    """
    try:
        # 处理输入：可能是 Pydantic 模型或字典
        if hasattr(document_data_or_schema, 'model_dump'):
            doc_data = document_data_or_schema.model_dump()
        elif isinstance(document_data_or_schema, dict):
            doc_data = document_data_or_schema
        else:
            doc_data = document_data_or_schema.__dict__
        
        now = datetime.utcnow()
        title = doc_data.get('title', '')
        content = doc_data.get('content', '')
        status = doc_data.get('status', STATUS_ACTIVE)
        folder_name = doc_data.get('folder_name')
        folder_id = doc_data.get('folder_id')
        tags = doc_data.get('tags')
        
        # 如果 folder_name 为 None 或空字符串，自动设置为 "默认文件夹"
        if not folder_name or folder_name.strip() == '':
            folder_name = "默认文件夹"
        
        # 构造安全的 SQL 值
        title_safe = _escape(title)
        content_safe = _escape(content)
        status_safe = _escape(status)
        folder_safe = _escape(folder_name)
        tags_safe = _escape(tags) if tags is not None else "NULL"
        now_sql = _format_datetime(now)
        folder_value = folder_id if isinstance(folder_id, int) else 'NULL'

        # 执行插入
        db.execute(
            f"INSERT INTO {TABLE_DOCUMENTS} "
            f"(title, content, status, owner_id, folder_name, folder_id, tags, created_at, updated_at) "
            f"VALUES ({title_safe}, {content_safe}, {status_safe}, {owner_id}, {folder_safe}, {folder_value}, {tags_safe}, {now_sql}, {now_sql})"
        )
        
        # 获取刚插入的文档（通过 owner_id 和最新 ID 查询）
        rows = db.query(
            f"SELECT {DOCUMENT_FIELDS} FROM {TABLE_DOCUMENTS} "
            f"WHERE owner_id = {owner_id} ORDER BY id DESC LIMIT 1"
        )

        if rows:
            doc = _row_to_document_dict(rows[0])
            if tags:
                try:
                    add_document_tags(db, doc.get('id'), [t.strip() for t in tags.split(',') if t.strip()])
                except Exception as tag_err:
                    logger.warning("初始化文档标签失败: %s", tag_err)
            try:
                create_revision_if_changed(
                    db,
                    doc.get('id'),
                    doc.get('title'),
                    doc.get('content', ''),
                    owner_id,
                    reason="create",
                )
            except Exception:
                pass
            return doc
        
        logger.warning("创建文档后无法查询到新文档，owner_id=%s", owner_id)
        return None
    except Exception as e:
        logger.error("创建文档失败: %s", e, exc_info=True)
        raise


def update_document(
    db,
    document_id: int,
    document_update,
    user_id: int,
    *,
    revision_reason: str = "update",
    create_revision: bool = True,
) -> Optional[Dict]:
    """
    更新文档（支持所有者或协作者更新）
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        document_update: DocumentUpdate 对象或字典，包含要更新的字段
        user_id: 操作者用户ID（用于获取文档，实际更新权限由调用者验证）
        
    Returns:
        更新后的文档字典；如果文档不存在则返回 None
        
    Note:
        - 函数会自动更新 updated_at 字段
        - 不会更新 id、owner_id、created_at 字段
        - 调用者需要先验证权限（can_edit）
        - 参数名从 owner_id 改为 user_id 以明确表示实际操作者
    """
    # 检查文档是否存在（允许所有者或协作者访问）
    doc = get_document_with_collaborators(db, document_id, user_id)
    if not doc:
        # 如果通过user_id查不到，尝试直接查询文档是否存在
        # 使用参数化查询避免SQL注入
        doc_rows = db.query(f"SELECT {DOCUMENT_FIELDS} FROM {TABLE_DOCUMENTS} WHERE id = %s LIMIT 1", (document_id,))
        if not doc_rows:
            return None
        doc = _row_to_document_dict(doc_rows[0])
    
    try:
        # 提取更新数据
        update_data = _extract_update_data(document_update)
        if not update_data:
            # 没有要更新的字段，直接返回原文档
            return doc
        
        # 构建更新字段
        update_fields = _build_update_clause(update_data, exclude_fields=['id', 'owner_id', 'created_at'])
        
        # 添加更新时间
        update_fields.append(f"updated_at = {_format_datetime(datetime.utcnow())}")
        
        if update_fields:
            # 移除owner_id限制，允许协作者更新（权限已在调用处验证）
            sql = f"UPDATE {TABLE_DOCUMENTS} SET {', '.join(update_fields)} WHERE id = %s"
            db.execute(sql, (document_id,))

        if 'tags' in update_data:
            try:
                db.execute("DELETE FROM document_tags WHERE document_id = %s", (document_id,))
                new_tags = []
                raw_tags = update_data.get('tags')
                if raw_tags:
                    new_tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]
                if new_tags:
                    add_document_tags(db, document_id, new_tags)
                else:
                    _refresh_document_tags_cache(db, document_id)
            except Exception as tag_err:
                logger.warning("同步标签失败: %s", tag_err)

        # 返回更新后的文档
        updated_rows = db.query(f"SELECT {DOCUMENT_FIELDS} FROM {TABLE_DOCUMENTS} WHERE id = %s LIMIT 1", (document_id,))
        if updated_rows:
            updated_doc = _row_to_document_dict(updated_rows[0])
            if create_revision:
                try:
                    create_revision_if_changed(
                        db,
                        document_id,
                        updated_doc.get("title"),
                        updated_doc.get("content", ""),
                        user_id,
                        reason=revision_reason,
                    )
                except Exception:
                    pass
            return updated_doc
        return None
    except Exception as e:
        logger.error("更新文档失败，document_id=%s: %s", document_id, e, exc_info=True)
        raise


def delete_document(db, document_id: int, owner_id: int) -> bool:
    """
    删除文档
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 文档所有者ID（用于权限验证）
        
    Returns:
        True 表示删除成功，False 表示文档不存在或不属于该用户
    """
    # 检查文档是否存在且属于当前用户
    doc = _get_document_by_id_and_owner(db, document_id, owner_id)
    if not doc:
        return False
    
    try:
        db.execute(f"DELETE FROM {TABLE_DOCUMENTS} WHERE id = %s AND owner_id = %s", (document_id, owner_id))
        return True
    except Exception as e:
        logger.error("删除文档失败，document_id=%s: %s", document_id, e, exc_info=True)
        raise


# ==================== 文档锁定/解锁相关函数 ====================

def lock_document(db, document_id: int, owner_id: int) -> bool:
    """
    锁定文档（防止其他用户编辑）
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 执行锁定的用户ID
        
    Returns:
        True 表示锁定成功，False 表示文档已被其他用户锁定
        
    Note:
        - 如果文档未被锁定，或已被当前用户锁定，则执行锁定
        - 锁定后会自动更新 updated_at 字段
    """
    try:
        now = datetime.utcnow()
        affected = db.execute(
            f"UPDATE {TABLE_DOCUMENTS} SET is_locked = TRUE, locked_by = %s, updated_at = %s "
            f"WHERE id = %s AND (is_locked = FALSE OR locked_by = %s)",
            (owner_id, now, document_id, owner_id)
        )
        # affected 可能是 None 或受影响行数
        success = affected is None or affected > 0
        if not success:
            logger.warning("锁定文档失败，文档可能已被其他用户锁定，document_id=%s, user_id=%s", document_id, owner_id)
        return success
    except Exception as e:
        logger.error("锁定文档失败，document_id=%s: %s", document_id, e, exc_info=True)
        raise


def unlock_document(db, document_id: int, owner_id: int) -> bool:
    """
    解锁文档（允许其他用户编辑）
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        owner_id: 执行解锁的用户ID（必须是锁定者）
        
    Returns:
        True 表示解锁成功，False 表示文档未被锁定或不是由该用户锁定
        
    Note:
        - 只有锁定者才能解锁文档
        - 解锁后会自动更新 updated_at 字段
    """
    try:
        now = datetime.utcnow()
        affected = db.execute(
            f"UPDATE {TABLE_DOCUMENTS} SET is_locked = FALSE, locked_by = NULL, updated_at = %s "
            f"WHERE id = %s AND locked_by = %s",
            (now, document_id, owner_id)
        )
        # affected 可能是 None 或受影响行数
        success = affected is None or affected > 0
        if not success:
            logger.warning("解锁文档失败，文档可能未被锁定或不是由该用户锁定，document_id=%s, user_id=%s", document_id, owner_id)
        return success
    except Exception as e:
        logger.error("解锁文档失败，document_id=%s: %s", document_id, e, exc_info=True)
        raise


# ==================== 文档搜索相关函数 ====================

def search_documents(
    db,
    owner_id: int,
    keyword: Optional[str] = None,
    tags: Optional[str] = None,
    folder: Optional[str] = None,
    sort_by: str = "updated_at",
    order: str = "desc",
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    updated_from: Optional[str] = None,
    updated_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> List[Dict]:
    """
    搜索文档（支持多条件组合查询）
    """
    joins = ["LEFT JOIN document_collaborators dc ON d.id = dc.document_id"]
    where_conditions = ["(d.owner_id = %s OR dc.user_id = %s)"]
    params: List = [owner_id, owner_id]

    if keyword:
        where_conditions.append("(d.title ILIKE %s OR d.content ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    if tags:
        joins.append("INNER JOIN document_tags dt ON dt.document_id = d.id")
        where_conditions.append("dt.tag = %s")
        params.append(tags)

    if status:
        where_conditions.append("d.status = %s")
        params.append(status)

    if folder:
        where_conditions.append("d.folder_name = %s")
        params.append(folder)

    if created_from:
        where_conditions.append("d.created_at >= %s")
        params.append(created_from)

    if created_to:
        where_conditions.append("d.created_at <= %s")
        params.append(created_to)

    if updated_from:
        where_conditions.append("d.updated_at >= %s")
        params.append(updated_from)

    if updated_to:
        where_conditions.append("d.updated_at <= %s")
        params.append(updated_to)

    where_clause = " WHERE " + " AND ".join(where_conditions)

    sort_field = sort_by if sort_by in VALID_SORT_FIELDS else "updated_at"
    order_dir = "ASC" if order.lower() == "asc" else "DESC"

    sql = f"""
        SELECT DISTINCT d.id, d.owner_id, d.title, d.content, d.status, d.folder_name, d.tags,
               d.is_locked, d.locked_by, d.created_at, d.updated_at
        FROM {TABLE_DOCUMENTS} d
        {' '.join(joins)}
        {where_clause}
        ORDER BY d.{sort_field} {order_dir}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, skip])
    rows = db.query(sql, tuple(params))

    return [_row_to_document_dict(row) for row in rows]


# ==================== 辅助查询函数（文件夹、标签） ====================

def get_folders(db, owner_id: int) -> List[Dict]:
    rows = db.query(
        "SELECT id, name, created_at, updated_at FROM folders WHERE owner_id = %s ORDER BY name",
        (owner_id,),
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "created_at": row[2],
            "updated_at": row[3],
        }
        for row in rows
    ] if rows else []


def create_folder(db, owner_id: int, name: str) -> Dict:
    now = datetime.utcnow()
    db.execute(
        "INSERT INTO folders (owner_id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
        (owner_id, name, now, now),
    )
    rows = db.query(
        "SELECT id, name, created_at, updated_at FROM folders WHERE owner_id=%s AND name=%s ORDER BY id DESC LIMIT 1",
        (owner_id, name),
    )
    if rows:
        return {"id": rows[0][0], "name": rows[0][1], "created_at": rows[0][2], "updated_at": rows[0][3]}
    return {}


def rename_folder(db, owner_id: int, folder_id: int, name: str) -> Dict:
    db.execute("UPDATE folders SET name=%s, updated_at=now() WHERE id=%s AND owner_id=%s", (name, folder_id, owner_id))
    rows = db.query("SELECT id, name, created_at, updated_at FROM folders WHERE id=%s AND owner_id=%s", (folder_id, owner_id))
    if not rows:
        return {}
    return {"id": rows[0][0], "name": rows[0][1], "created_at": rows[0][2], "updated_at": rows[0][3]}


def delete_folder(db, owner_id: int, folder_id: int):
    db.execute("UPDATE documents SET folder_id = NULL WHERE folder_id = %s", (folder_id,))
    db.execute("DELETE FROM folders WHERE id=%s AND owner_id=%s", (folder_id, owner_id))


def get_tags(db, owner_id: int) -> List[str]:
    """
    获取用户的所有标签列表
    
    Args:
        db: 数据库连接对象
        owner_id: 文档所有者ID
        
    Returns:
        标签列表（去重、排序）
        
    Note:
        标签在数据库中可能以逗号分隔的字符串形式存储，函数会自动拆分并去重
    """
    rows = db.query(
        """
        SELECT DISTINCT dt.tag
        FROM document_tags dt
        INNER JOIN documents d ON dt.document_id = d.id
        WHERE d.owner_id = %s
        ORDER BY dt.tag
        """,
        (owner_id,),
    )

    return [row[0] for row in rows] if rows else []


# ==================== 文档版本相关函数 ====================

def create_document_version(
    db, 
    document_id: int, 
    user_id: int, 
    content: str, 
    summary: str = ""
) -> Optional[Dict]:
    """
    创建文档版本快照
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        user_id: 创建版本的用户ID
        content: 文档内容快照
        summary: 版本变更摘要（可选）
        
    Returns:
        创建的版本字典，包含版本号等信息；如果创建失败则返回 None
        
    Note:
        - 版本号自动递增（基于该文档的最大版本号）
        - 使用事务确保版本号生成的原子性
        - 如果发生并发冲突，会回滚事务并抛出异常
    """
    try:
        now = datetime.utcnow()
        content_safe = _escape(content)
        summary_safe = _escape(summary)
        now_sql = _format_datetime(now)

        # 使用事务确保版本号生成的原子性
        db.execute("BEGIN")
        try:
            # 获取当前最大版本号并加锁
            rows = db.query(
                f"SELECT COALESCE(MAX(version_number), 0) FROM {TABLE_DOCUMENT_VERSIONS} "
                f"WHERE document_id = {document_id} FOR UPDATE"
            )
            next_version = (rows[0][0] if rows else 0) + 1
            
            # 插入新版本
            db.execute(
                f"INSERT INTO {TABLE_DOCUMENT_VERSIONS} "
                f"(document_id, user_id, version_number, content_snapshot, summary, created_at) "
                f"VALUES ({document_id}, {user_id}, {next_version}, {content_safe}, {summary_safe}, {now_sql})"
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

        # 获取刚创建的版本
        rows = db.query(
            f"SELECT {VERSION_FIELDS} FROM {TABLE_DOCUMENT_VERSIONS} "
            f"WHERE document_id = {document_id} ORDER BY version_number DESC LIMIT 1"
        )

        if rows:
            return _row_to_version_dict(rows[0])
        
        logger.warning("创建文档版本后无法查询到新版本，document_id=%s", document_id)
        return None
    except Exception as e:
        logger.error("创建文档版本失败，document_id=%s: %s", document_id, e, exc_info=True)
        raise


def get_document_versions(db, document_id: int) -> List[Dict]:
    """
    获取文档的所有版本列表
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        
    Returns:
        版本字典列表，按版本号降序排列
    """
    rows = db.query(
        f"SELECT {VERSION_FIELDS} FROM {TABLE_DOCUMENT_VERSIONS} "
        f"WHERE document_id = {document_id} ORDER BY version_number DESC"
    )
    
    return [_row_to_version_dict(row) for row in rows]


def get_document_version_count(db, document_id: int) -> int:
    """
    获取文档的版本数量
    
    Args:
        db: 数据库连接对象
        document_id: 文档ID
        
    Returns:
        版本数量（整数），如果文档不存在则返回 0
    """
    rows = db.query(
        f"SELECT COUNT(*) FROM {TABLE_DOCUMENT_VERSIONS} WHERE document_id = %s",
        (document_id,)
    )
    
    if rows:
        return rows[0][0]
    return 0


# ==================== 文档历史版本（修订）相关函数 ====================


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def create_revision_if_changed(
    db,
    document_id: int,
    title: Optional[str],
    content: str,
    user_id: Optional[int],
    reason: Optional[str] = None,
):
    """若内容有变更则记录修订版本，按 content_hash 去重。"""

    content_hash = _compute_content_hash(content)
    try:
        last_row = db.query(
            f"SELECT content_hash FROM {TABLE_DOCUMENT_REVISIONS} WHERE document_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
            (document_id,),
        )
        if last_row and last_row[0][0] == content_hash:
            return None

        db.execute(
            f"""
            INSERT INTO {TABLE_DOCUMENT_REVISIONS} (document_id, created_by, title, content, content_hash, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (document_id, user_id, title, content, content_hash, reason),
        )
        return content_hash
    except Exception as e:
        logger.warning("创建文档修订失败，document_id=%s: %s", document_id, e)
        return None


def list_revisions(db, document_id: int, limit: int = 50, offset: int = 0) -> List[Dict]:
    rows = db.query(
        f"SELECT {REVISION_FIELDS} FROM {TABLE_DOCUMENT_REVISIONS} WHERE document_id = %s ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
        (document_id, limit, offset),
    )
    return [_row_to_revision_dict(row) for row in rows]


def get_revision(db, document_id: int, revision_id: int) -> Optional[Dict]:
    rows = db.query(
        f"SELECT {REVISION_FIELDS} FROM {TABLE_DOCUMENT_REVISIONS} WHERE document_id = %s AND id = %s LIMIT 1",
        (document_id, revision_id),
    )
    if rows:
        return _row_to_revision_dict(rows[0])
    return None


def diff_revisions(db, document_id: int, from_revision_id: int, to_revision_id: int) -> str:
    from_rev = get_revision(db, document_id, from_revision_id)
    to_rev = get_revision(db, document_id, to_revision_id)
    if not from_rev or not to_rev:
        raise HTTPException(status_code=404, detail="修订不存在")

    from_lines = (from_rev.get("content") or "").splitlines()
    to_lines = (to_rev.get("content") or "").splitlines()
    diff_lines = difflib.unified_diff(
        from_lines,
        to_lines,
        fromfile=f"rev_{from_revision_id}",
        tofile=f"rev_{to_revision_id}",
        lineterm="",
    )
    return "\n".join(diff_lines)


def rollback_to_revision(db, document_id: int, revision_id: int, user, request=None) -> Optional[Dict]:
    assert_document_access(db, document_id, user, required_role="editor")

    current_doc = get_document_with_collaborators(db, document_id, getattr(user, "id", 0))
    if not current_doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    target_revision = get_revision(db, document_id, revision_id)
    if not target_revision:
        raise HTTPException(status_code=404, detail="修订不存在")

    create_revision_if_changed(
        db,
        document_id,
        current_doc.get("title"),
        current_doc.get("content", ""),
        getattr(user, "id", None),
        reason="rollback_pre",
    )

    update_data = DocumentUpdate(
        title=target_revision.get("title") or current_doc.get("title"),
        content=target_revision.get("content"),
    )
    updated_document = update_document(
        db,
        document_id,
        update_data,
        getattr(user, "id", 0),
        revision_reason="rollback_applied",
        create_revision=False,
    )

    create_revision_if_changed(
        db,
        document_id,
        updated_document.get("title") if updated_document else target_revision.get("title"),
        target_revision.get("content", ""),
        getattr(user, "id", None),
        reason="rollback_applied",
    )

    try:
        log_action(
            db,
            user_id=getattr(user, "id", None),
            action="document.rollback",
            resource_type="document",
            resource_id=document_id,
            request=request,
            meta={"to_revision": revision_id},
        )
    except Exception:
        pass

    return updated_document


# ==================== 模板相关函数 ====================

def get_templates(db, category: Optional[str] = None, active_only: bool = True) -> List[Dict]:
    """
    获取模板列表
    
    Args:
        db: 数据库连接对象
        category: 模板分类（可选筛选）
        active_only: 是否只返回激活的模板，默认为 True
        
    Returns:
        模板字典列表，按分类和名称排序
    """
    where_conditions = []
    if category:
        category_safe = _escape(category)
        where_conditions.append(f"category = {category_safe}")
    
    if active_only:
        where_conditions.append("is_active = TRUE")
    
    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    rows = db.query(
        f"SELECT {TEMPLATE_FIELDS} FROM {TABLE_DOCUMENT_TEMPLATES}{where_clause} "
        f"ORDER BY category, name"
    )
    
    return [_row_to_template_dict(row) for row in rows]


def get_template(db, template_id: int) -> Optional[Dict]:
    """
    获取单个模板详情
    
    Args:
        db: 数据库连接对象
        template_id: 模板ID
        
    Returns:
        模板字典，如果模板不存在或未激活则返回 None
    """
    return _get_template_by_id(db, template_id, active_only=True)


def create_template(db, template) -> Optional[Dict]:
    """
    创建新模板
    
    Args:
        db: 数据库连接对象
        template: TemplateCreate 对象或字典，包含模板数据
        
    Returns:
        创建的模板字典，包含生成的ID和时间戳；如果创建失败则返回 None
        
    Note:
        函数会自动设置 created_at 和 updated_at 为当前时间
    """
    try:
        # 处理输入：可能是 Pydantic 模型或字典
        if hasattr(template, 'model_dump'):
            tmpl_data = template.model_dump()
        elif isinstance(template, dict):
            tmpl_data = template
        else:
            tmpl_data = template.__dict__
        
        now = datetime.utcnow()
        name = tmpl_data.get('name', '')
        description = tmpl_data.get('description', '')
        content = tmpl_data.get('content', '')
        category = tmpl_data.get('category', '')
        is_active = tmpl_data.get('is_active', True)
        
        # 构造安全的 SQL 值
        name_safe = _escape(name)
        desc_safe = _escape(description)
        content_safe = _escape(content)
        category_safe = _escape(category)
        is_active_sql = _format_bool(is_active)
        now_sql = _format_datetime(now)
        
        # 执行插入
        db.execute(
            f"INSERT INTO {TABLE_DOCUMENT_TEMPLATES} "
            f"(name, description, content, category, is_active, created_at, updated_at) "
            f"VALUES ({name_safe}, {desc_safe}, {content_safe}, {category_safe}, {is_active_sql}, {now_sql}, {now_sql})"
        )
        
        # 获取刚插入的模板
        rows = db.query(
            f"SELECT {TEMPLATE_FIELDS} FROM {TABLE_DOCUMENT_TEMPLATES} ORDER BY id DESC LIMIT 1"
        )
        
        if rows:
            return _row_to_template_dict(rows[0])
        
        logger.warning("创建模板后无法查询到新模板")
        return None
    except Exception as e:
        logger.error("创建模板失败: %s", e, exc_info=True)
        raise


def update_template(db, template_id: int, template_update) -> Optional[Dict]:
    """
    更新模板
    
    Args:
        db: 数据库连接对象
        template_id: 模板ID
        template_update: TemplateUpdate 对象或字典，包含要更新的字段
        
    Returns:
        更新后的模板字典；如果模板不存在或未激活则返回 None
        
    Note:
        - 函数会自动更新 updated_at 字段
        - 不会更新 id、created_at 字段
    """
    # 检查模板是否存在
    template = _get_template_by_id(db, template_id, active_only=True)
    if not template:
        return None
    
    try:
        # 提取更新数据
        update_data = _extract_update_data(template_update)
        if not update_data:
            # 没有要更新的字段，直接返回原模板
            return template
        
        # 构建更新字段
        update_fields = _build_update_clause(update_data, exclude_fields=['id', 'created_at'])
        
        # 构建参数化更新
        set_clauses = []
        params = []
        
        for field in update_fields:
            if '=' in field:
                field_name, _ = field.split('=', 1)
                set_clauses.append(f"{field_name.strip()} = %s")
                # 从原始update_data中获取值
                field_name = field_name.strip()
                if field_name in update_data:
                    params.append(update_data[field_name])
        
        # 添加更新时间
        set_clauses.append("updated_at = %s")
        params.append(datetime.utcnow())
        
        # 添加WHERE条件参数
        params.append(template_id)
        
        if set_clauses:
            sql = f"UPDATE {TABLE_DOCUMENT_TEMPLATES} SET {', '.join(set_clauses)} WHERE id = %s"
            db.execute(sql, tuple(params))
        
        # 返回更新后的模板（允许查询非激活模板）
        return _get_template_by_id(db, template_id, active_only=False)
    except Exception as e:
        logger.error("更新模板失败，template_id=%s: %s", template_id, e, exc_info=True)
        raise


def delete_template(db, template_id: int) -> bool:
    """
    删除模板（软删除，设置 is_active = FALSE）
    
    Args:
        db: 数据库连接对象
        template_id: 模板ID
        
    Returns:
        True 表示删除成功，False 表示模板不存在或未激活
        
    Note:
        这是软删除操作，不会真正从数据库中删除记录
    """
    # 检查模板是否存在
    template = _get_template_by_id(db, template_id, active_only=True)
    if not template:
        return False
    
    try:
        now = datetime.utcnow()
        db.execute(
            f"UPDATE {TABLE_DOCUMENT_TEMPLATES} SET is_active = FALSE, updated_at = %s "
            f"WHERE id = %s",
            (now, template_id)
        )
        return True
    except Exception as e:
        logger.error("删除模板失败，template_id=%s: %s", template_id, e, exc_info=True)
        raise
