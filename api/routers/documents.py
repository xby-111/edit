from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from core.security import get_current_user
from db.session import get_db
from schemas import Document, DocumentCreate, DocumentUpdate
from services.document_service import get_documents, get_document, create_document, update_document, delete_document
from models import Document as DocumentModel, DocumentVersion as DocumentVersionModel, User
from datetime import timedelta

router = APIRouter()

@router.get("/documents", response_model=List[dict])
async def get_documents_endpoint(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    documents = db.query(DocumentModel).filter(DocumentModel.owner_id == current_user.id).all()
    return [{
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at
    } for doc in documents]

@router.post("/documents", response_model=dict)
async def create_document_endpoint(title: str, content: str = "", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_document = DocumentModel(
        title=title,
        content=content,
        owner_id=current_user.id
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)
    return {
        "id": new_document.id,
        "title": new_document.title,
        "status": new_document.status,
        "created_at": new_document.created_at,
        "updated_at": new_document.updated_at
    }

@router.get("/documents/{document_id}", response_model=dict)
async def get_document_endpoint(document_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(DocumentModel).filter(DocumentModel.id == document_id, DocumentModel.owner_id == current_user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": document.id,
        "title": document.title,
        "content": document.content,
        "status": document.status,
        "created_at": document.created_at,
        "updated_at": document.updated_at
    }

@router.get("/documents/{document_id}/versions", response_model=List[dict])
async def get_document_versions(document_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document_versions = db.query(DocumentVersionModel).filter(DocumentVersionModel.document_id == document_id).all()
    return [{
        "id": version.id,
        "version_number": version.version_number,
        "user_id": version.user_id,
        "summary": version.summary,
        "created_at": version.created_at
    } for version in document_versions]

@router.post("/documents/{document_id}/versions", response_model=dict)
async def create_document_version(document_id: int, content: str, summary: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(DocumentModel).filter(DocumentModel.id == document_id, DocumentModel.owner_id == current_user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    new_version = DocumentVersionModel(
        document_id=document_id,
        user_id=current_user.id,
        version_number=len(document.versions) + 1,
        content_snapshot=content,
        summary=summary
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    return {
        "id": new_version.id,
        "version_number": new_version.version_number,
        "summary": new_version.summary,
        "created_at": new_version.created_at
    }