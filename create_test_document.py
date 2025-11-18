from sqlalchemy.orm import Session
from db.session import SessionLocal
from models import Document, User
import os

# 设置数据库URL
os.environ["DATABASE_URL"] = "postgresql://omm:Guass000@localhost:5432/postgres"

def create_test_document():
    db: Session = SessionLocal()
    try:
        # 创建一个测试用户（如果不存在）
        user = db.query(User).filter(User.username == "testuser").first()
        if not user:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=User.get_password_hash("password123")
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # 创建一个测试文档（如果不存在）
        doc = db.query(Document).filter(Document.title == "Test Document").first()
        if not doc:
            doc = Document(
                title="Test Document",
                content="Welcome to the collaborative editor!\nStart typing here...",
                owner_id=user.id
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            print(f"Created test document with ID: {doc.id}")
        else:
            print(f"Test document already exists with ID: {doc.id}")
    finally:
        db.close()

if __name__ == "__main__":
    create_test_document()