# IFLOW.md - 项目上下文

## 项目概述

这是一个基于 FastAPI 的多人实时协作编辑器项目。该项目允许多个用户同时在线编辑文档，并提供内容同步和光标同步功能。主要技术栈包括：

- **后端**: FastAPI 框架
- **数据库**: PostgreSQL (通过 SQLAlchemy ORM)
- **前端**: HTML + JavaScript
- **实时通信**: WebSocket
- **认证**: JWT (JSON Web Token)

## 项目架构

### 核心组件

1. **app.py**: 主应用文件，包含所有 API 路由、WebSocket 连接处理、用户认证逻辑
2. **models.py**: 数据库模型定义，包括 User、Document、DocumentVersion 等实体
3. **templates/index.html**: 前端页面模板，提供编辑器界面
4. **static/client.js**: 前端 JavaScript 代码，处理 WebSocket 通信和光标同步
5. **requirements.txt**: 项目依赖列表

### 数据模型

- **User**: 用户模型，包含用户名、邮箱、密码哈希、角色等信息
- **Document**: 文档模型，关联到用户，包含标题、内容、状态等
- **DocumentVersion**: 文档版本模型，用于版本控制和历史记录

### 功能特性

1. **用户认证系统**: 
   - 用户注册/登录
   - JWT 令牌认证
   - 密码哈希存储 (bcrypt)

2. **文档管理**:
   - 创建、读取、更新文档
   - 文档版本控制
   - 用户文档权限管理

3. **实时协作**:
   - WebSocket 连接处理
   - 多人同时编辑内容同步
   - 光标位置同步

## 构建和运行

### 环境准备

1. 确保已安装 Python 3.8+
2. 安装依赖包:
   ```bash
   pip install -r requirements.txt
   ```

### 数据库配置

项目使用 PostgreSQL 数据库，连接字符串在 `models.py` 中定义:
```
postgresql+psycopg2://omm:Guass000@localhost:5432/postgres
```

### 运行应用

使用 uvicorn 启动应用:
```bash
uvicorn app:app --reload
```

应用将在 `http://localhost:8000` 启动。

## 开发约定

### 安全性

- 密码使用 bcrypt 哈希
- JWT 令牌认证
- 防止时间攻击的密码验证

### API 设计

- RESTful API 设计
- WebSocket 用于实时通信
- JSON 格式数据交换

### 代码结构

- 使用 FastAPI 的依赖注入系统
- SQLAlchemy ORM 用于数据库操作
- Pydantic 模型用于数据验证