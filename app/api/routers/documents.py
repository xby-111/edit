"""
文档管理路由 - 统一使用 Service 层
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas import Document, DocumentCreate, DocumentUpdate
from app.services.document_service import (
    get_documents, get_document, create_document, update_document, 
    delete_document, create_document_version, get_document_versions,
    get_document_version_count
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["文档管理"])

@router.get("/documents", response_model=List[Document], summary="获取文档列表", description="获取当前用户有权限访问的所有文档")
async def get_documents_endpoint(
    current_user = Depends(get_current_user), 
    db = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取当前用户的文档列表"""
    documents = get_documents(db, current_user.id, skip=skip, limit=limit)
    return documents

@router.post("/documents", response_model=Document, status_code=status.HTTP_201_CREATED, summary="创建文档", description="创建新的协作文档")
async def create_document_endpoint(
    document: DocumentCreate,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """创建文档"""
    try:
        new_document = create_document(db, document, current_user.id)
        return Document(
            id=new_document['id'],
            owner_id=new_document['owner_id'],
            title=new_document['title'],
            content=new_document['content'],
            status=new_document['status'],
            created_at=new_document['created_at'],
            updated_at=new_document['updated_at']
        )
    except Exception as e:
        logger.error(f"创建文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档失败")

@router.get("/documents/{document_id}", response_model=Document, summary="获取文档详情", description="根据文档ID获取文档详细内容")
async def get_document_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文档详情"""
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return Document(
        id=document['id'],
        owner_id=document['owner_id'],
        title=document['title'],
        content=document['content'],
        status=document['status'],
        created_at=document['created_at'],
        updated_at=document['updated_at']
    )

@router.put("/documents/{document_id}", response_model=Document, summary="更新文档", description="更新文档的标题、内容和状态")
async def update_document_endpoint(
    document_id: int,
    document_update: DocumentUpdate,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """更新文档"""
    try:
        updated_document = update_document(db, document_id, document_update, current_user.id)
        if not updated_document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return Document(
            id=updated_document['id'],
            owner_id=updated_document['owner_id'],
            title=updated_document['title'],
            content=updated_document['content'],
            status=updated_document['status'],
            created_at=updated_document['created_at'],
            updated_at=updated_document['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新文档失败")

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除文档", description="删除指定的文档")
async def delete_document_endpoint(
    document_id: int,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """删除文档"""
    try:
        success = delete_document(db, document_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="文档不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除文档失败")

@router.get("/documents/{document_id}/versions", response_model=List[dict], summary="获取文档版本列表", description="获取文档的所有历史版本")
async def get_document_versions_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文档版本列表"""
    # 先检查文档是否存在且用户有权限
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    versions = get_document_versions(db, document_id)
    return [{
        "id": version['id'],
        "version_number": version['version_number'],
        "user_id": version['user_id'],
        "summary": version['summary'],
        "created_at": version['created_at']
    } for version in versions]

@router.post("/documents/{document_id}/versions", response_model=dict, status_code=status.HTTP_201_CREATED, summary="创建文档版本", description="为文档创建新的历史版本")
async def create_document_version_endpoint(
    document_id: int, 
    content: str, 
    summary: str = "",
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """创建文档版本"""
    # 先检查文档是否存在且用户有权限
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    try:
        new_version = create_document_version(
            db, document_id, current_user.id, content, summary
        )
        return {
            "id": new_version['id'],
            "version_number": new_version['version_number'],
            "summary": new_version['summary'],
            "created_at": new_version['created_at']
        }
    except Exception as e:
        logger.error(f"创建文档版本失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档版本失败")