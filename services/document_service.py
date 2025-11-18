from sqlalchemy.orm import Session
from models import Document, DocumentVersion
from schemas import DocumentCreate, DocumentUpdate

def get_documents(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(Document).filter(Document.owner_id == owner_id).offset(skip).limit(limit).all()

def get_document(db: Session, document_id: int, owner_id: int):
    return db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()

def create_document(db: Session, document: DocumentCreate, owner_id: int):
    db_document = Document(
        title=document.title,
        content=document.content,
        status=document.status,
        owner_id=owner_id
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def update_document(db: Session, document_id: int, document_update: DocumentUpdate, owner_id: int):
    db_document = db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()
    if db_document:
        # Update only the fields that are provided in the update request
        for field, value in document_update.model_dump(exclude_unset=True).items():
            setattr(db_document, field, value)
        db.commit()
        db.refresh(db_document)
        return db_document
    return None

def delete_document(db: Session, document_id: int, owner_id: int):
    db_document = db.query(Document).filter(Document.id == document_id, Document.owner_id == owner_id).first()
    if db_document:
        db.delete(db_document)
        db.commit()
        return True
    return False

def create_document_version(db: Session, document_id: int, user_id: int, content: str, summary: str = ""):
    # Get the latest version number for this document
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
    db.commit()
    db.refresh(db_version)
    return db_version