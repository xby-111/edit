"""
文档服务层 - 不直接提交事务，由调用方控制
"""
import logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from models import Document, DocumentVersion
from schemas import DocumentCreate, DocumentUpdate
from datetime import datetime

logger = logging.getLogger(__name__)

def get_documents(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    """获取文档列表（不提交事务）"""
    return db.query(Document).filter(Document.owner_id == owner_id).offset(skip).limit(limit).all()

def get_document(db: Session, document_id: int, owner_id: int):
    """获取文档（不提交事务）"""
    return db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()

def create_document(db: Session, document: DocumentCreate, owner_id: int, commit: bool = False):
    """
    创建文档
    
    Args:
        db: 数据库会话
        document: 文档创建数据
        owner_id: 所有者ID
        commit: 是否立即提交事务（默认False）
        
    Returns:
        创建的文档对象
    """
    db_document = Document(
        title=document.title,
        content=document.content,
        status=document.status if document.status else "active",
        owner_id=owner_id
    )
    db.add(db_document)
    if commit:
        db.commit()
        db.refresh(db_document)
    return db_document

def update_document(db: Session, document_id: int, document_update: DocumentUpdate, owner_id: int, commit: bool = False):
    """
    更新文档
    
    Args:
        db: 数据库会话
        document_id: 文档ID
        document_update: 更新数据
        owner_id: 所有者ID（用于权限检查）
        commit: 是否立即提交事务（默认False）
        
    Returns:
        更新后的文档对象，如果文档不存在返回None
    """
    db_document = db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()
    if db_document:
        # Update only the fields that are provided in the update request
        for field, value in document_update.model_dump(exclude_unset=True).items():
            setattr(db_document, field, value)
        db_document.updated_at = datetime.utcnow()
        if commit:
            db.commit()
            db.refresh(db_document)
        return db_document
    return None

def delete_document(db: Session, document_id: int, owner_id: int, commit: bool = False):
    """
    删除文档
    
    Args:
        db: 数据库会话
        document_id: 文档ID
        owner_id: 所有者ID（用于权限检查）
        commit: 是否立即提交事务（默认False）
        
    Returns:
        是否删除成功
    """
    db_document = db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()
    if db_document:
        db.delete(db_document)
        if commit:
            db.commit()
        return True
    return False

def get_document_version_count(db: Session, document_id: int) -> int:
    """获取文档版本数量（避免N+1查询）"""
    return db.query(func.count(DocumentVersion.id)).filter(
        DocumentVersion.document_id == document_id
    ).scalar() or 0

def create_document_version(db: Session, document_id: int, user_id: int, content: str, summary: str = "", commit: bool = False):
    """
    创建文档版本
    
    Args:
        db: 数据库会话
        document_id: 文档ID
        user_id: 用户ID
        content: 内容快照
        summary: 变更摘要
        commit: 是否立即提交事务（默认False）
        
    Returns:
        创建的版本对象
    """
    # Get the latest version number for this document (避免N+1查询)
    latest_version = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).order_by(DocumentVersion.version_number.desc()).first()
    
    version_number = 1
    if latest_version:
        version_number = latest_version.version_number + 1
    
    db_version = DocumentVersion(
        document_id=document_id,
        user_id=user_id,
        version_number=version_number,
        content_snapshot=content,
        summary=summary
    )
    db.add(db_version)
    if commit:
        db.commit()
        db.refresh(db_version)
    return db_version

def get_document_versions(db: Session, document_id: int):
    """获取文档的所有版本（不提交事务）"""
    return db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).order_by(DocumentVersion.version_number.desc()).all()