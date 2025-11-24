"""
文档服务层 - 使用 py-opengauss 直接 SQL 操作
"""
import logging
from app.schemas import DocumentCreate, DocumentUpdate
from datetime import datetime

logger = logging.getLogger(__name__)

def _escape(value: str | None) -> str:
    """简单转义单引号，避免 SQL 语法错误（内部使用即可）"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

def _format_datetime(dt: datetime | None) -> str:
    """格式化日期时间为 SQL 字符串"""
    if dt is None:
        return "NULL"
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"

def get_documents(db, owner_id: int, skip: int = 0, limit: int = 100):
    """获取文档列表 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, owner_id, title, content, status, created_at, updated_at FROM documents WHERE owner_id = {owner_id} ORDER BY id LIMIT {limit} OFFSET {skip}")
    
    documents = []
    for result in rows:
        documents.append({
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'created_at': result[5],
            'updated_at': result[6]
        })
    return documents

def get_document(db, document_id: int, owner_id: int):
    """获取文档 - 使用 py-opengauss 的 query 方法"""
    # 使用 py-opengauss 的 query 方法查询
    rows = db.query(f"SELECT id, owner_id, title, content, status, created_at, updated_at FROM documents WHERE id = {document_id} AND owner_id = {owner_id} LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'created_at': result[5],
            'updated_at': result[6]
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
    now_sql = _format_datetime(now)
    
    # 使用 py-opengauss 的 execute 方法插入文档数据
    db.execute(f"INSERT INTO documents (title, content, status, owner_id, created_at, updated_at) VALUES ({title_safe}, {content_safe}, {status_safe}, {owner_id}, {now_sql}, {now_sql})")
    
    # 获取刚插入的文档数据
    rows = db.query(f"SELECT id, owner_id, title, content, status, created_at, updated_at FROM documents WHERE owner_id = {owner_id} ORDER BY id DESC LIMIT 1")
    
    if rows:
        result = rows[0]
        return {
            'id': result[0],
            'owner_id': result[1],
            'title': result[2],
            'content': result[3],
            'status': result[4],
            'created_at': result[5],
            'updated_at': result[6]
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
    # 获取当前文档的最新版本号
    rows = db.query(f"SELECT version_number FROM document_versions WHERE document_id = {document_id} ORDER BY version_number DESC LIMIT 1")
    
    version_number = 1
    if rows:
        version_number = rows[0][0] + 1
    
    now = datetime.utcnow()
    
    # 构造安全的 SQL 字符串
    content_safe = _escape(content)
    summary_safe = _escape(summary)
    now_sql = _format_datetime(now)
    
    # 使用 py-opengauss 的 execute 方法插入版本数据
    db.execute(f"INSERT INTO document_versions (document_id, user_id, version_number, content_snapshot, summary, created_at) VALUES ({document_id}, {user_id}, {version_number}, {content_safe}, {summary_safe}, {now_sql})")
    
    # 获取刚插入的版本数据
    rows = db.query(f"SELECT id, document_id, user_id, version_number, content_snapshot, summary, created_at FROM document_versions WHERE document_id = {document_id} AND user_id = {user_id} ORDER BY version_number DESC LIMIT 1")
    
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