from sqlalchemy import Column, Integer, String, Boolean, create_engine, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
import os
from datetime import datetime

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://user:password@localhost:5432/mydb"
)

# Create engine and session
engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(100))
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="viewer")  # 用户角色：admin/editor/viewer
    created_at = Column(DateTime, default=datetime.utcnow)  # 用户创建时间

    def verify_password(self, plain_password: str):
        return pwd_context.verify(plain_password, self.hashed_password)
        
    @staticmethod
    def get_password_hash(password: str):
        return pwd_context.hash(password)
        
    @classmethod
    def create_user(cls, username: str, email: str, password: str):
        hashed_password = cls.get_password_hash(password)
        return cls(
            username=username,
            email=email,
            hashed_password=hashed_password
        )
    
    # 关系：一个用户可以有多个账户
    accounts = relationship("Account", back_populates="user")
    # 更新关系：一个用户可以有多个文档
    documents = relationship("Document", back_populates="owner")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(200), nullable=False, index=True)  # 文档标题
    content = Column(Text, nullable=False, default="")       # 文档内容
    status = Column(String(50), default="active")            # 文档状态：normal/archived

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系：一个文档属于一个用户
    owner = relationship("User", back_populates="documents")
    # 关系：一个文档可以有多个版本
    versions = relationship("DocumentVersion", back_populates="document")


# Dependency to get DB session
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables
Base.metadata.create_all(bind=engine)
