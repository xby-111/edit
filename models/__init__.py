"""
统一的数据库模型定义
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
from datetime import datetime

# 统一的 Base 定义
Base = declarative_base()

# 密码加密上下文（用于模型方法）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)  # 手机号
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="viewer")  # 用户角色：admin/editor/viewer
    
    # 个人信息
    avatar_url = Column(String(500), nullable=True)  # 头像URL
    full_name = Column(String(100), nullable=True)  # 全名
    bio = Column(Text, nullable=True)  # 个人简介
    
    # 联系信息
    address = Column(String(500), nullable=True)  # 地址
    phone_secondary = Column(String(20), nullable=True)  # 备用电话
    
    # 密码重置相关
    password_reset_token = Column(String(255), nullable=True)  # 密码重置令牌
    password_reset_expires = Column(DateTime, nullable=True)  # 密码重置过期时间
    
    # 验证码相关（用于密码重置）
    verification_code = Column(String(10), nullable=True)  # 验证码
    verification_code_expires = Column(DateTime, nullable=True)  # 验证码过期时间
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系：一个用户可以有多个文档
    documents = relationship("Document", back_populates="owner")
    # 关系：一个用户可以有多个操作日志
    operation_logs = relationship("OperationLog", back_populates="user")
    
    def verify_password(self, plain_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, self.hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """生成密码哈希"""
        return pwd_context.hash(password)


class Document(Base):
    """文档模型"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String(200), nullable=False, index=True)  # 文档标题
    content = Column(Text, nullable=False, default="")       # 文档内容
    status = Column(String(50), default="active")            # 文档状态：active/archived
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系：一个文档属于一个用户
    owner = relationship("User", back_populates="documents")
    # 关系：一个文档可以有多个版本
    versions = relationship("DocumentVersion", back_populates="document")


class DocumentVersion(Base):
    """文档版本模型"""
    __tablename__ = "document_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    version_number = Column(Integer, nullable=False)
    content_snapshot = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)  # 可选的变更摘要
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系：一个版本属于一个文档
    document = relationship("Document", back_populates="versions")


class OperationLog(Base):
    """操作日志模型"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    action = Column(String(100), nullable=False)  # 操作类型：login, logout, create_document等
    resource_type = Column(String(50), nullable=True)  # 资源类型：document, user等
    resource_id = Column(Integer, nullable=True)  # 资源ID
    description = Column(Text, nullable=True)  # 操作描述
    ip_address = Column(String(50), nullable=True)  # IP地址
    user_agent = Column(String(500), nullable=True)  # 用户代理
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系：一个日志属于一个用户
    user = relationship("User", back_populates="operation_logs")


class Permission(Base):
    """权限模型"""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # 权限名称：read_document等
    description = Column(Text, nullable=True)  # 权限描述
    resource_type = Column(String(50), nullable=True)  # 资源类型
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RolePermission(Base):
    """角色权限关联表"""
    __tablename__ = "role_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(20), nullable=False)  # 角色：admin, editor, viewer
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ACL(Base):
    """访问控制列表"""
    __tablename__ = "acls"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(50), nullable=False)  # 资源类型：document等
    resource_id = Column(Integer, nullable=False)  # 资源ID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 用户ID（如果为空则对所有用户）
    role = Column(String(20), nullable=True)  # 角色（如果为空则对所有角色）
    
    permission = Column(String(100), nullable=False)  # 权限：read, write, delete等
    granted = Column(Boolean, default=True)  # 是否授予权限
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
