"""
文档服务层 - 使用 py-opengauss 直接 SQL 操作
"""
import logging
from app.schemas import DocumentCreate, DocumentUpdate, TemplateCreate, TemplateUpdate
from datetime import datetime

logger = logging.getLogger(__name__)

def _escape(value: str | None) -> str:
    """简单转义单引号，避免 SQL 语法错误（内部使用即可）"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

def _format_bool(value: bool | None) -> str:
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"

def _format_datetime(dt: datetime | None) -> str:
    """格式化日期时间为 SQL 字符串"""
    if dt is None:
        return "NULL"
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"

def get_documents(db, owner_id: int, skip: int = 0, limit: int = 100, folder: str = None, status: str = None, tag: str = None):
    """获取文档列表 - 使用 py-opengauss 的 query 方法"""
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
    
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, owner_id, title, content, status, folder_name, tags, is_locked, locked_by, created_at, updated_at FROM documents{where_clause} ORDER BY updated_at DESC LIMIT {limit} OFFSET {skip}")
    
    documents = []
    for result in rows:
        documents.append({
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'folder_name': result[5],
            'tags': result[6],
            'is_locked': result[7],
            'locked_by': result[8],
            'created_at': result[9],
            'updated_at': result[10]
        })
    return documents

def get_document(db, document_id: int, owner_id: int):
    """获取文档 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, owner_id, title, content, status, folder_name, tags, is_locked, locked_by, created_at, updated_at FROM documents WHERE id = {document_id} AND owner_id = {owner_id} LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'folder_name': result[5],
            'tags': result[6],
            'is_locked': result[7],
            'locked_by': result[8],
            'created_at': result[9],
            'updated_at': result[10]
        }
    return None

def create_document(db, document: DocumentCreate, owner_id: int):
    """
    创建文档 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        document: 文档创建数据
        owner_id: 所有者ID
        
    Returns:
        创建的文档对象
    """
    now = datetime.utcnow()
    status = document.status if document.status else "active"
    
    # 构造安全的 SQL 字符串
    title_safe = _escape(document.title)
    content_safe = _escape(document.content)
    status_safe = _escape(status)
    folder_safe = _escape(document.folder_name) if getattr(document, "folder_name", None) is not None else "NULL"
    tags_safe = _escape(document.tags) if getattr(document, "tags", None) is not None else "NULL"
    now_sql = _format_datetime(now)

    db.execute(
        f"INSERT INTO documents (title, content, status, owner_id, folder_name, tags, created_at, updated_at) "
        f"VALUES ({title_safe}, {content_safe}, {status_safe}, {owner_id}, {folder_safe}, {tags_safe}, {now_sql}, {now_sql})"
    )
    
    # 获取刚插入的文档数据
    rows = db.query(f"SELECT id, owner_id, title, content, status, folder_name, tags, created_at, updated_at FROM documents WHERE owner_id = {owner_id} ORDER BY id DESC LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'folder_name': result[5],
            'tags': result[6],
            'created_at': result[7],
            'updated_at': result[8]
        }
    return None

def update_document(db, document_id: int, document_update: DocumentUpdate, owner_id: int):
    """
    更新文档 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        document_id: 文档ID
        document_update: 更新数据
        owner_id: 所有者ID（用于权限检查）
        
    Returns:
        更新后的文档对象，如果文档不存在返回None
    """
    # 检查文档是否存在且属于当前用户
    doc = get_document(db, document_id, owner_id)
    if not doc:
        return None
    
    # 构建更新语句
    update_fields = []
    
    # 获取更新数据
    update_data = {}
    if hasattr(document_update, 'model_dump'):
        update_data = document_update.model_dump(exclude_unset=True)
    elif hasattr(document_update, '__dict__'):
        update_data = document_update.__dict__
    
    # 构建更新字段
    for field, value in update_data.items():
        if field not in ['id', 'owner_id', 'created_at']:  # 不更新这些字段
            if field in ['title', 'content', 'status']:
                # 字符串字段
                value_safe = _escape(value)
                update_fields.append(f"{field} = {value_safe}")
            else:
                # 其他字段
                value_safe = _escape(str(value))
                update_fields.append(f"{field} = {value_safe}")
    
    # 添加更新时间
    update_fields.append(f"updated_at = {_format_datetime(datetime.utcnow())}")
    
    if update_fields:
        # 使用 py-opengauss 的 execute 方法更新
        sql = f"UPDATE documents SET {', '.join(update_fields)} WHERE id = {document_id} AND owner_id = {owner_id}"
        db.execute(sql)
    
    # 返回更新后的文档数据
    return get_document(db, document_id, owner_id)

def delete_document(db, document_id: int, owner_id: int):
    """
    删除文档 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        document_id: 文档ID
        owner_id: 所有者ID（用于权限检查）
        
    Returns:
        是否删除成功
    """
    # 检查文档是否存在且属于当前用户
    doc = get_document(db, document_id, owner_id)
    if not doc:
        return False
    
    # 使用 py-opengauss 的 execute 方法删除文档
    db.execute(f"DELETE FROM documents WHERE id = {document_id} AND owner_id = {owner_id}")
    return True

def get_document_version_count(db, document_id: int) -> int:
    """获取文档版本数量 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT COUNT(*) FROM document_versions WHERE document_id = {document_id}")
    
    if rows:
        return rows[0][0]
    return 0

def create_document_version(db, document_id: int, user_id: int, content: str, summary: str = ""):
    """
    创建文档版本 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        document_id: 文档ID
        user_id: 用户ID
        content: 内容快照
        summary: 变更摘要
        
    Returns:
        创建的版本对象
    """
    now = datetime.utcnow()

    content_safe = _escape(content)
    summary_safe = _escape(summary)
    now_sql = _format_datetime(now)

    try:
        db.execute("BEGIN")
        rows = db.query(
            f"SELECT COALESCE(MAX(version_number), 0) FROM document_versions WHERE document_id = {document_id} FOR UPDATE"
        )
        next_version = (rows[0][0] if rows else 0) + 1
        db.execute(
            f"INSERT INTO document_versions (document_id, user_id, version_number, content_snapshot, summary, created_at) "
            f"VALUES ({document_id}, {user_id}, {next_version}, {content_safe}, {summary_safe}, {now_sql})"
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        logger.exception("创建文档版本失败，可能存在并发冲突")
        raise

    rows = db.query(
        f"SELECT id, document_id, user_id, version_number, content_snapshot, summary, created_at "
        f"FROM document_versions WHERE document_id = {document_id} ORDER BY version_number DESC LIMIT 1"
    )

    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'document_id': result[1],
            'user_id': result[2],
            'version_number': result[3],
            'content_snapshot': result[4],
            'summary': result[5],
            'created_at': result[6]
        }
    return None

def get_document_versions(db, document_id: int):
    """获取文档的所有版本 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, document_id, user_id, version_number, content_snapshot, summary, created_at FROM document_versions WHERE document_id = {document_id} ORDER BY version_number DESC")
    
    versions = []
    for result in rows:
        versions.append({
            'id': result[0],
            'document_id': result[1],
            'user_id': result[2],
            'version_number': result[3],
            'content_snapshot': result[4],
            'summary': result[5],
            'created_at': result[6]
        })
    return versions

# 模板相关服务函数
def get_templates(db, category: str = None, active_only: bool = True):
    """获取模板列表 - 使用 py-opengauss 的 query 方法"""
    where_conditions = []
    if category:
        category_safe = _escape(category)
        where_conditions.append(f"category = {category_safe}")
    
    if active_only:
        where_conditions.append("is_active = TRUE")
    
    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, name, description, content, category, is_active, created_at, updated_at FROM document_templates{where_clause} ORDER BY category, name")
    
    templates = []
    for result in rows:
        templates.append({
            'id': result[0],
            'name': result[1],
            'description': result[2],
            'content': result[3],
            'category': result[4],
            'is_active': result[5],
            'created_at': result[6],
            'updated_at': result[7]
        })
    return templates

def get_template(db, template_id: int):
    """获取单个模板 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, name, description, content, category, is_active, created_at, updated_at FROM document_templates WHERE id = {template_id} AND is_active = TRUE LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'name': result[1],
            'description': result[2],
            'content': result[3],
            'category': result[4],
            'is_active': result[5],
            'created_at': result[6],
            'updated_at': result[7]
        }
    return None

def create_template(db, template: TemplateCreate):
    """
    创建模板 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        template: 模板创建数据
        
    Returns:
        创建的模板对象
    """
    now = datetime.utcnow()
    
    # 构造安全的 SQL 字符串
    name_safe = _escape(template.name)
    desc_safe = _escape(template.description)
    content_safe = _escape(template.content)
    category_safe = _escape(template.category)
    is_active_sql = _format_bool(template.is_active)
    now_sql = _format_datetime(now)
    
    # 使用 py-opengauss 的 execute 方法插入模板数据
    db.execute(f"INSERT INTO document_templates (name, description, content, category, is_active, created_at, updated_at) VALUES ({name_safe}, {desc_safe}, {content_safe}, {category_safe}, {is_active_sql}, {now_sql}, {now_sql})")
    
    # 获取刚插入的模板数据
    rows = db.query(f"SELECT id, name, description, content, category, is_active, created_at, updated_at FROM document_templates ORDER BY id DESC LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'name': result[1],
            'description': result[2],
            'content': result[3],
            'category': result[4],
            'is_active': result[5],
            'created_at': result[6],
            'updated_at': result[7]
        }
    return None

def update_template(db, template_id: int, template_update: TemplateUpdate):
    """
    更新模板 - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        template_id: 模板ID
        template_update: 更新数据
        
    Returns:
        更新后的模板对象，如果模板不存在返回None
    """
    # 检查模板是否存在
    template = get_template(db, template_id)
    if not template:
        return None
    
    # 构建更新语句
    update_fields = []
    
    # 获取更新数据
    update_data = {}
    if hasattr(template_update, 'model_dump'):
        update_data = template_update.model_dump(exclude_unset=True)
    elif hasattr(template_update, '__dict__'):
        update_data = template_update.__dict__
    
    # 构建更新字段
    for field, value in update_data.items():
        if field not in ['id', 'created_at']:  # 不更新这些字段
            if field in ['name', 'description', 'content', 'category']:
                # 字符串字段
                value_safe = _escape(value)
                update_fields.append(f"{field} = {value_safe}")
            else:
                # 其他字段
                value_safe = _escape(str(value))
                update_fields.append(f"{field} = {value_safe}")
    
    # 添加更新时间
    update_fields.append(f"updated_at = {_format_datetime(datetime.utcnow())}")
    
    if update_fields:
        # 使用 py-opengauss 的 execute 方法更新
        sql = f"UPDATE document_templates SET {', '.join(update_fields)} WHERE id = {template_id}"
        db.execute(sql)
    
    # 返回更新后的模板数据
    return get_template(db, template_id)

def delete_template(db, template_id: int):
    """
    删除模板（软删除，设置 is_active = FALSE） - 使用 py-opengauss 的 execute 方法
    
    Args:
        db: 数据库连接
        template_id: 模板ID
        
    Returns:
        是否删除成功
    """
    # 检查模板是否存在
    template = get_template(db, template_id)
    if not template:
        return False
    
    # 使用 py-opengauss 的 execute 方法软删除模板
    db.execute(f"UPDATE document_templates SET is_active = FALSE, updated_at = {_format_datetime(datetime.utcnow())} WHERE id = {template_id}")
    return True

# 搜索和分类相关服务函数
def search_documents(db, owner_id: int, keyword: str = None, tags: str = None,
                   folder: str = None, sort_by: str = "updated_at", order: str = "desc",
                   created_from: str = None, created_to: str = None,
                   updated_from: str = None, updated_to: str = None,
                   skip: int = 0, limit: int = 100, status: str = None):
    """搜索文档 - 使用 py-opengauss 的 query 方法"""
    where_conditions = [f"owner_id = {owner_id}"]
    
    # 关键词搜索
    if keyword:
        keyword_safe = _escape(f"%{keyword}%")
        where_conditions.append(f"(title ILIKE {keyword_safe} OR content ILIKE {keyword_safe})")
    
    # 标签搜索
    if tags:
        tag_query = _escape(tags)
        where_conditions.append(f"to_tsvector('simple', tags) @@ plainto_tsquery({tag_query})")

    # 状态筛选
    if status:
        status_safe = _escape(status)
        where_conditions.append(f"status = {status_safe}")
    
    # 文件夹搜索
    if folder:
        folder_safe = _escape(folder)
        where_conditions.append(f"folder_name = {folder_safe}")

    # 排序字段兜底
    if sort_by and sort_by not in ["title", "created_at", "updated_at"]:
        sort_by = "updated_at"
    
    # 日期范围搜索
    if created_from:
        from_safe = _format_datetime(created_from)
        where_conditions.append(f"created_at >= {from_safe}")
    
    if created_to:
        to_safe = _format_datetime(created_to)
        where_conditions.append(f"created_at <= {to_safe}")
    
    if updated_from:
        from_safe = _format_datetime(updated_from)
        where_conditions.append(f"updated_at >= {from_safe}")
    
    if updated_to:
        to_safe = _format_datetime(updated_to)
        where_conditions.append(f"updated_at <= {to_safe}")
    
    where_clause = " WHERE " + " AND ".join(where_conditions)
    
    # 排序
    valid_sort_fields = ["title", "created_at", "updated_at"]
    sort_field = sort_by if sort_by in valid_sort_fields else "updated_at"
    order_dir = "ASC" if order.lower() == "asc" else "DESC"
    
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"""
        SELECT id, owner_id, title, content, status, folder_name, tags, 
               is_locked, locked_by, created_at, updated_at
        FROM documents{where_clause} 
        ORDER BY {sort_field} {order_dir} 
        LIMIT {limit} OFFSET {skip}
    """)
    
    documents = []
    for result in rows:
        documents.append({
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'folder_name': result[5],
            'tags': result[6],
            'is_locked': result[7],
            'locked_by': result[8],
            'created_at': result[9],
            'updated_at': result[10]
        })
    return documents

def get_folders(db, owner_id: int):
    """获取用户的所有文件夹 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(f"""
        SELECT DISTINCT folder_name 
        FROM documents 
        WHERE owner_id = {owner_id} AND folder_name IS NOT NULL 
        ORDER BY folder_name
    """)
    
    folders = [row[0] for row in rows if row[0]]
    return folders

def get_tags(db, owner_id: int):
    """获取用户的所有标签 - 使用 py-opengauss 的 query 方法"""
    rows = db.query(f"""
        SELECT DISTINCT tags 
        FROM documents 
        WHERE owner_id = {owner_id} AND tags IS NOT NULL AND tags != ''
        ORDER BY tags
    """)
    
    # 合并所有标签并去重
    all_tags = set()
    for row in rows:
        if row[0]:
            tags = row[0].split(',')
            all_tags.update(tag.strip() for tag in tags if tag.strip())
    
    return sorted(list(all_tags))

def lock_document(db, document_id: int, user_id: int):
    """锁定文档 - 使用 py-opengauss 的 execute 方法"""
    now_sql = _format_datetime(datetime.utcnow())
    affected = db.execute(
        f"UPDATE documents SET is_locked = TRUE, locked_by = {user_id}, updated_at = {now_sql} "
        f"WHERE id = {document_id} AND (is_locked = FALSE OR locked_by = {user_id})"
    )
    return affected is None or affected > 0

def unlock_document(db, document_id: int, user_id: int):
    """解锁文档 - 使用 py-opengauss 的 execute 方法"""
    now_sql = _format_datetime(datetime.utcnow())
    affected = db.execute(
        f"UPDATE documents SET is_locked = FALSE, locked_by = NULL, updated_at = {now_sql} "
        f"WHERE id = {document_id} AND locked_by = {user_id}"
    )
    return affected is None or affected > 0