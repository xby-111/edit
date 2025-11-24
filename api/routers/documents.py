"""
文档管理路由 - 统一使用 Service 层
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from core.security import get_current_user
from db.session import get_db
from schemas import Document, DocumentCreate, DocumentUpdate
from services.document_service import (
    get_documents, get_document, create_document, update_document, 
    delete_document, create_document_version, get_document_versions,
    get_document_version_count
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/documents", response_model=List[Document])
async def get_documents_endpoint(
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取当前用户的文档列表"""
    documents = get_documents(db, current_user.id, skip=skip, limit=limit)
    return documents

@router.post("/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
async def create_document_endpoint(
    document: DocumentCreate,
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """创建文档"""
    try:
        new_document = create_document(db, document, current_user.id, commit=False)
        db.commit()
        db.refresh(new_document)
        return new_document
    except Exception as e:
        db.rollback()
        logger.error(f"创建文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档失败")

@router.get("/documents/{document_id}", response_model=Document)
async def get_document_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """获取文档详情"""
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@router.put("/documents/{document_id}", response_model=Document)
async def update_document_endpoint(
    document_id: int,
    document_update: DocumentUpdate,
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """更新文档"""
    try:
        updated_document = update_document(db, document_id, document_update, current_user.id, commit=False)
        if not updated_document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        db.commit()
        db.refresh(updated_document)
        return updated_document
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新文档失败")

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    document_id: int,
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """删除文档"""
    try:
        success = delete_document(db, document_id, current_user.id, commit=False)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除文档失败")

@router.get("/documents/{document_id}/versions", response_model=List[dict])
async def get_document_versions_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """获取文档版本列表"""
    # 先检查文档是否存在且用户有权限
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    versions = get_document_versions(db, document_id)
    return [{
        "id": version.id,
        "version_number": version.version_number,
        "user_id": version.user_id,
        "summary": version.summary,
        "created_at": version.created_at
    } for version in versions]

@router.post("/documents/{document_id}/versions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_document_version_endpoint(
    document_id: int, 
    content: str, 
    summary: str = "",
    current_user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """创建文档版本"""
    # 先检查文档是否存在且用户有权限
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        new_version = create_document_version(
            db, document_id, current_user.id, content, summary, commit=False
        )
        db.commit()
        db.refresh(new_version)
        return {
            "id": new_version.id,
            "version_number": new_version.version_number,
            "summary": new_version.summary,
            "created_at": new_version.created_at
        }
    except Exception as e:
        db.rollback()
        logger.error(f"创建文档版本失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档版本失败")