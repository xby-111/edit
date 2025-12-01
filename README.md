# 协作文档编辑器 (Collaborative Document Editor)

一个基于 FastAPI 的多人实时协作文档编辑系统，支持 CRDT 增量同步、富文本编辑、权限管理和实时通信。

## ✨ 功能特性

### 核心功能
- 🔄 **实时协作编辑** - 基于 WebSocket 的多人同时编辑，支持光标位置同步
- 📝 **CRDT 增量同步** - 使用 RGA 算法实现冲突自动解决，减少带宽消耗
- 📄 **富文本编辑** - 集成 Quill 编辑器，支持格式化文本
- 💾 **写后持久化** - 内存缓存 + 后台批量保存，提升响应速度

### 用户认证
- 🔐 **JWT 认证** - 安全的 Token 认证机制
- 🔑 **密码重置** - 邮箱验证重置密码
- 📱 **验证码登录** - 支持邮箱/手机验证码登录
- 🌐 **OAuth2 第三方登录** - 支持 GitHub、Google、微信
- 🛡️ **双因素认证 (2FA)** - TOTP 动态令牌 + 备用码

### 文档管理
- 📁 **文件夹组织** - 支持文件夹分类管理
- 🏷️ **标签系统** - 灵活的标签筛选
- 📜 **版本历史** - 文档版本控制与回滚
- 📥 **导入导出** - 支持 PDF、Word、HTML 格式
- 🔒 **文档锁定** - 防止编辑冲突
- 👥 **协作者管理** - 邀请协作者并设置权限

### 协作功能
- 💬 **文档内聊天** - 实时聊天讨论
- 💭 **评论系统** - 文档段落评论
- ✅ **任务管理** - 创建和分配任务
- 🔔 **通知系统** - 实时消息推送

### 系统管理
- 👤 **用户管理** - 管理员用户管理
- 📊 **系统监控** - CPU、内存、数据库状态监控
- 📋 **审计日志** - 操作日志记录
- 💾 **数据备份** - 支持备份与恢复
- ⚙️ **系统设置** - 功能开关配置

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| **后端框架** | FastAPI 0.121.2 |
| **编程语言** | Python 3.10+ |
| **数据库** | OpenGauss (兼容 PostgreSQL) |
| **认证** | JWT (python-jose) + bcrypt |
| **实时通信** | WebSocket |
| **同步算法** | CRDT (RGA) |
| **前端编辑器** | Quill.js |
| **模板引擎** | Jinja2 |

## 📁 项目结构

```
edit/
├── app/                          # 应用主目录
│   ├── main.py                   # FastAPI 应用入口
│   ├── crdt.py                   # CRDT 算法实现
│   ├── api/
│   │   ├── admin_deps.py         # 管理员依赖
│   │   └── routers/              # API 路由
│   │       ├── auth.py           # 认证相关
│   │       ├── users.py          # 用户管理
│   │       ├── documents.py      # 文档管理
│   │       ├── ws.py             # WebSocket 协作
│   │       ├── notify_ws.py      # 通知 WebSocket
│   │       ├── admin.py          # 管理员功能
│   │       ├── chat.py           # 文档聊天
│   │       ├── notifications.py  # 通知系统
│   │       └── feedback.py       # 用户反馈
│   ├── core/
│   │   ├── config.py             # 应用配置
│   │   ├── security.py           # 安全与认证
│   │   └── utils.py              # 公共工具函数
│   ├── db/
│   │   ├── session.py            # 数据库连接 (OpenGauss 兼容层)
│   │   ├── init_db.py            # 数据库初始化
│   │   └── init_permissions.py   # 权限初始化
│   ├── services/                 # 业务逻辑层
│   │   ├── user_service.py
│   │   ├── document_service.py
│   │   ├── websocket_service.py  # WebSocket 服务 (CRDT + 写后持久化)
│   │   ├── audit_service.py
│   │   ├── notification_service.py
│   │   ├── notification_ws_manager.py
│   │   ├── chat_service.py
│   │   ├── comment_service.py
│   │   ├── task_service.py
│   │   ├── oauth_service.py
│   │   ├── totp_service.py
│   │   ├── verification_service.py
│   │   ├── backup_service.py
│   │   ├── monitoring_service.py
│   │   └── settings_service.py
│   └── schemas/                  # Pydantic 数据模型
│       ├── comment.py
│       ├── task.py
│       └── notification.py
├── static/
│   ├── editor.js                 # 协作编辑器前端 (CRDT 客户端)
│   ├── client.js                 # API 客户端
│   └── toast.js                  # 通知提示组件
├── templates/
│   ├── index.html                # 主页面
│   └── test_collab.html          # 协作编辑器页面
├── docs/                         # 项目文档
├── scripts/                      # 工具脚本
├── uploads/                      # 上传文件目录
├── backups/                      # 备份目录
├── requirements.txt              # Python 依赖
└── README.md
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- OpenGauss 数据库 (或 PostgreSQL)
- Node.js (可选，用于前端开发)

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/xby-111/edit.git
cd edit
```

2. **创建虚拟环境**
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置环境变量**
```bash
# 创建 .env 文件
cp .env.example .env
# 编辑配置
```

主要配置项：
```env
DATABASE_URL=opengauss://user:password@localhost:5432/editdb
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

5. **初始化数据库**
```bash
python -c "from app.db.init_db import init_db; init_db()"
```

6. **启动服务**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

7. **访问应用**
- 主页：http://localhost:8000
- API 文档：http://localhost:8000/api/docs
- ReDoc：http://localhost:8000/api/redoc

## 📡 API 概览

### 认证接口 `/api/v1/auth`
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /register | 用户注册 |
| POST | /token | 用户登录 |
| GET | /me | 获取当前用户 |
| POST | /password-reset/request | 请求密码重置 |
| POST | /2fa/setup | 设置双因素认证 |
| GET | /oauth/{provider}/authorize | OAuth2 授权 |

### 文档接口 `/api/v1`
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /documents | 获取文档列表 |
| POST | /documents | 创建文档 |
| GET | /documents/{id} | 获取文档详情 |
| PUT | /documents/{id} | 更新文档 |
| DELETE | /documents/{id} | 删除文档 |
| POST | /documents/{id}/collaborators | 添加协作者 |
| GET | /documents/{id}/versions | 获取版本历史 |

### WebSocket `/api/v1/ws`
| 路径 | 描述 |
|------|------|
| /ws/documents/{id}?token=xxx | 文档协作连接 |
| /ws/notifications?token=xxx | 通知推送连接 |

### 管理接口 `/api/v1/admin`
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /users | 用户列表 |
| GET | /audit | 审计日志 |
| GET | /monitoring/dashboard | 监控面板 |
| POST | /backup/create | 创建备份 |

## 🔄 CRDT 同步机制

项目使用 **RGA (Replicated Growable Array)** 算法实现无冲突协作编辑：

```
用户 A 输入 "Hello"     用户 B 输入 "World"
        ↓                      ↓
   生成 CRDT 操作           生成 CRDT 操作
        ↓                      ↓
   WebSocket 发送          WebSocket 发送
        ↓                      ↓
      ┌─────────服务端合并─────────┐
      │  CRDT 自动解决冲突         │
      │  标记为脏数据              │
      └────────────────────────────┘
        ↓                      ↓
   广播给用户 B            广播给用户 A
        ↓                      ↓
   应用增量更新            应用增量更新
        ↓                      ↓
   最终一致：同时显示 "HelloWorld"
```

### 写后持久化策略
- 协作期间数据保存在内存 CRDT 中
- 后台任务每 5 秒批量持久化脏数据
- 房间最后一人离开时强制保存
- 大幅降低数据库写入压力

## 🔒 安全特性

- **JWT 认证** - 所有 API 和 WebSocket 均需 Token
- **参数化查询** - 防止 SQL 注入
- **权限控制** - RBAC + ACL 细粒度权限
- **2FA 支持** - TOTP + 备用码
- **密码加密** - bcrypt 哈希存储
- **指数退避** - 重连防雷群效应

## 📊 监控与运维

### 健康检查
```bash
curl http://localhost:8000/api/v1/admin/monitoring/health
```

### 系统指标
```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/admin/monitoring/dashboard
```

### 数据备份
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/admin/backup/create
```

## 🧪 测试

```bash
# 运行导入冒烟测试
python -c "from app.main import app; print('OK')"

# 验证 WebSocket 服务
python scripts/ws_notifications_smoke.py
```

## 📝 开发指南

### 添加新路由
1. 在 `app/api/routers/` 创建路由文件
2. 在 `app/main.py` 注册路由
3. 在 `app/services/` 添加业务逻辑

### 添加新数据模型
1. 在 `models/__init__.py` 定义 ORM 模型
2. 在 `schemas/__init__.py` 定义 Pydantic Schema
3. 运行数据库迁移

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**项目版本**: 1.1.0  
**最后更新**: 2025年11月
