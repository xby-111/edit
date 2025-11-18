# 协作编辑器项目代码库文档

## 项目概述

这是一个基于 FastAPI 框架的多人实时协作编辑器项目，支持用户认证、文档管理、版本控制以及实时协同编辑功能。项目使用 openGauss (通过 PostgreSQL 协议) 作为数据库，采用 WebSocket 实现实时通信。

## 项目架构

### 核心组件

1. **app/main.py** - FastAPI 应用入口点
2. **core/** - 核心功能模块 (配置、安全)
3. **db/** - 数据库相关模块 (会话管理、初始化)
4. **models/** - SQLAlchemy 数据模型
5. **schemas/** - Pydantic 数据验证模型
6. **api/routers/** - API 路由定义
7. **services/** - 业务逻辑服务
8. **utils/** - 工具函数

## 详细模块说明

### 1. app/main.py
- FastAPI 应用实例创建
- CORS 中间件配置
- 静态文件和模板服务
- API 路由注册
- 数据库初始化

### 2. core/config.py
- 应用配置管理
- 数据库连接 URL 配置 (支持 openGauss)
- JWT 认证配置
- CORS 域名配置

### 3. core/security.py
- 密码哈希和验证
- JWT 令牌创建和解码
- 安全相关工具函数

### 4. db/session.py
- SQLAlchemy 引擎创建
- 数据库会话工厂
- get_db 依赖注入器

### 5. db/init_db.py
- 数据库表初始化
- 模型元数据创建

### 6. models/__init__.py
包含以下数据库模型：
- **User**: 用户模型，包含用户名、邮箱、密码哈希等字段
- **Document**: 文档模型，关联用户，包含标题、内容等字段
- **DocumentVersion**: 文档版本模型，存储文档历史版本

### 7. schemas/__init__.py
包含以下 Pydantic 模型：
- **User**: 用户数据模型
- **UserCreate/UserUpdate**: 用户创建/更新模型
- **Document**: 文档数据模型
- **DocumentCreate/DocumentUpdate**: 文档创建/更新模型
- **DocumentVersion**: 文档版本模型

### 8. api/routers/

#### auth.py - 认证路由
- `/register`: 用户注册
- `/token`: 用户登录获取 JWT 令牌
- `/me`: 获取当前用户信息

#### users.py - 用户管理路由
- `/users/{user_id}`: 获取用户信息
- `/users/{user_id}`: 更新用户信息 (PUT)
- `/users/{user_id}`: 删除用户 (DELETE)

#### documents.py - 文档管理路由
- `/documents`: 获取用户文档列表
- `/documents`: 创建新文档
- `/documents/{document_id}`: 获取特定文档
- `/documents/{document_id}/versions`: 获取文档版本历史
- `/documents/{document_id}/versions`: 创建文档新版本

#### ws.py - WebSocket 路由
- `/ws/documents/{document_id}`: 文档实时协同编辑 WebSocket 连接

### 9. services/

#### user_service.py
- 用户创建、查询、更新、删除
- 用户认证相关辅助功能

#### document_service.py
- 文档创建、查询、更新、删除
- 文档版本管理
- 文档相关业务逻辑

#### websocket_service.py
- WebSocket 连接管理
- 消息广播功能
- 连接状态管理

### 10. utils/
- **exceptions.py**: 自定义异常类
- **response.py**: 响应格式化工具

## 技术栈

- **后端框架**: FastAPI
- **数据库**: openGauss (通过 PostgreSQL 协议)
- **ORM**: SQLAlchemy 2.0
- **认证**: JWT (JSON Web Token)
- **密码哈希**: bcrypt
- **异步支持**: asyncio, Starlette
- **模板引擎**: Jinja2
- **实时通信**: WebSocket

## 安全特性

1. 使用 JWT 进行身份验证
2. 密码使用 bcrypt 进行哈希处理
3. CORS 配置限制 (已配置为生产环境安全实践)
4. 输入验证使用 Pydantic 模型

## 实时协作功能

通过 WebSocket 实现实时文档协作：
- 内容同步功能
- 光标位置同步
- 多用户同时编辑支持
- 消息广播机制

## 部署和运行

运行命令：
```bash
uvicorn app.main:app --reload
```

环境变量配置：
- `DATABASE_URL`: 数据库连接字符串
- `SECRET_KEY`: JWT 密钥
- `ACCESS_TOKEN_EXPIRE_MINUTES`: 令牌过期时间

## 项目特点

1. **模块化架构**: 清晰的分层架构，便于维护和扩展
2. **类型安全**: 使用 Python 类型提示和 Pydantic 验证
3. **异步支持**: 基于 FastAPI 的异步处理能力
4. **RESTful API**: 符合 REST 设计原则的 API
5. **实时协作**: 支持多用户同时编辑文档
6. **版本控制**: 文档版本历史记录功能

该项目为协作编辑应用提供了完整的后端解决方案，包括用户认证、文档管理、版本控制以及实时协作功能。