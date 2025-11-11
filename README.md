# edit

## 第 0 步｜项目骨架与环境

Flask Web 应用项目，使用 SQLite 进行本地开发。

### 项目结构

```
edit/
├── app.py              # Flask 应用主文件
├── models.py           # 数据库模型
├── templates/          # HTML 模板
│   └── base.html      # 基础模板
├── .env               # 环境配置（不提交到 Git）
├── .gitignore         # Git 忽略文件
└── requirements.txt   # Python 依赖
```

### 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量（可选）：
编辑 `.env` 文件设置数据库 URI 和调试模式

3. 运行应用：
```bash
python app.py
```

4. 访问应用：
打开浏览器访问 `http://localhost:5000/`

### 功能

- ✅ Flask 应用框架搭建完成
- ✅ SQLite 数据库配置（开发环境）
- ✅ 支持 PostgreSQL（生产环境）
- ✅ 基础 HTML 模板
- ✅ 根路由返回 "项目运行成功"
- ✅ 通过环境变量控制调试模式

### 环境变量

在 `.env` 文件中配置：

- `DB_URI`: 数据库连接 URI
  - 开发环境：`sqlite:///app.db`
  - 生产环境：`postgresql://user:password@host:port/database`
- `FLASK_DEBUG`: 是否启用调试模式（`True` 或 `False`）