"""
文档管理路由 - 统一使用 Service 层
"""
import io
import logging
import re
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.comment import Comment, CommentCreate
from app.schemas.task import Task, TaskCreate, TaskUpdate
from app.schemas import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    Template,
    TemplateCreate,
    TemplateUpdate,
)
from app.services.document_service import (
    create_document,
    create_document_version,
    create_template,
    delete_document,
    delete_template,
    get_document,
    get_document_versions,
    get_documents,
    get_folders,
    get_tags,
    get_template,
    get_templates,
    lock_document,
    search_documents,
    unlock_document,
    update_document,
    update_template,
    add_collaborator,
    batch_add_collaborators,
    remove_collaborator,
    get_collaborators,
    get_shared_documents,
    check_document_permission,
    is_document_owner,
)
from app.services.audit_service import log_action
from app.services.settings_service import is_feature_enabled
from app.services.comment_service import create_comment, list_comments
from app.services.task_service import create_task, list_tasks, update_task

# PDF/Word 导入导出依赖
from xhtml2pdf import pisa
from docx import Document as DocxDocument
from docx.shared import Pt
import pdfplumber

logger = logging.getLogger(__name__)

router = APIRouter(tags=["文档管理"])


# ==================== 工具函数 ====================

def htmlToMarkdown(html: str) -> str:
    """简单的 HTML 到 Markdown 转换"""
    if not html:
        return ""
    
    try:
        markdown = html
        # 标题
        markdown = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', markdown, flags=re.DOTALL)
        # 强调
        markdown = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', markdown, flags=re.DOTALL)
        # 链接
        markdown = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', markdown, flags=re.DOTALL)
        # 图片
        markdown = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>', r'![\2](\1)', markdown, flags=re.DOTALL)
        # 引用
        markdown = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'> \1', markdown, flags=re.DOTALL)
        # 代码
        markdown = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```', markdown, flags=re.DOTALL)
        # 列表
        markdown = re.sub(r'<ul[^>]*>(.*?)</ul>', lambda m: re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', m.group(1), flags=re.DOTALL), markdown, flags=re.DOTALL)
        markdown = re.sub(r'<ol[^>]*>(.*?)</ol>', lambda m: re.sub(r'<li[^>]*>(.*?)</li>', r'1. \1', m.group(1), flags=re.DOTALL), markdown, flags=re.DOTALL)
        # 换行和段落
        markdown = re.sub(r'<br[^>]*>', '\n', markdown)
        markdown = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n', markdown, flags=re.DOTALL)
        # 移除所有剩余标签
        markdown = re.sub(r'<[^>]+>', '', markdown)
        return markdown.strip()
    except Exception:
        # 如果转换失败,返回空字符串
        return ""


def markdownToHtml(markdown: str) -> str:
    """简单的 Markdown 到 HTML 转换"""
    if not markdown:
        return ""
    
    try:
        html = markdown
        # 标题
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # 强调和斜体
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        # 链接
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
        # 图片
        html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', html)
        # 引用
        html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
        # 代码
        html = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        # 列表
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)
        # 段落和换行
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'
        html = re.sub(r'<p></p>', '', html)
        html = re.sub(r'<p>(.+?)</p>\s*<p>', r'<p>\1</p>', html)
        return html
    except Exception:
        # 如果转换失败,返回原始内容包装在段落中
        return f"<p>{markdown}</p>"


# ==================== 文档列表 / 搜索 / 标签 / 文件夹相关路由 ====================

@router.get("/documents", response_model=List[Document], summary="获取文档列表", description="获取当前用户拥有的文档列表")
async def get_documents_endpoint(
    current_user = Depends(get_current_user), 
    db = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    folder: Optional[str] = None
):
    """获取当前用户拥有的文档列表"""
    documents = get_documents(db, current_user.id, skip=skip, limit=limit, folder=folder)
    return documents


@router.get("/documents/search", response_model=List[Document], summary="搜索文档", description="根据关键词、标签、日期等条件搜索文档")
async def search_documents_endpoint(
    keyword: Optional[str] = None,
    tags: Optional[str] = None,
    folder: Optional[str] = None,
    sort_by: str = "updated_at",
    order: str = "desc",
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    updated_from: Optional[str] = None,
    updated_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """搜索文档"""
    documents = search_documents(
        db, current_user.id, keyword, tags, folder, sort_by, order,
        created_from, created_to, updated_from, updated_to, skip, limit
    )
    return documents


@router.get("/folders", response_model=List[str], summary="获取文件夹列表", description="获取用户的所有文件夹")
async def get_folders_endpoint(
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文件夹列表"""
    folders = get_folders(db, current_user.id)
    return folders


@router.get("/tags", response_model=List[str], summary="获取标签列表", description="获取用户的所有标签")
async def get_tags_endpoint(
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取标签列表"""
    tags = get_tags(db, current_user.id)
    return tags


# ==================== 文档锁定/解锁相关路由 ====================

@router.post("/documents/{document_id}/lock", summary="锁定文档", description="锁定文档，禁止其他用户编辑")
async def lock_document_endpoint(
    document_id: int,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """锁定文档"""
    # 检查文档权限（需要编辑权限才能锁定）
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_edit"]:
        raise HTTPException(status_code=403, detail="无编辑权限，无法锁定文档")
    
    # 获取文档信息检查锁定状态
    document = get_document_with_collaborators(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if document.get('is_locked'):
        raise HTTPException(status_code=400, detail="文档已被锁定")
    
    try:
        lock_document(db, document_id, current_user.id)
        return {"message": "文档已锁定"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("锁定文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="锁定文档失败")


@router.post("/documents/{document_id}/unlock", summary="解锁文档", description="解锁文档，允许其他用户编辑")
async def unlock_document_endpoint(
    document_id: int,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """解锁文档"""
    # 检查文档权限（需要编辑权限才能解锁）
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_edit"]:
        raise HTTPException(status_code=403, detail="无编辑权限，无法解锁文档")
    
    # 获取文档信息检查锁定状态
    document = get_document_with_collaborators(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if not document.get('is_locked'):
        raise HTTPException(status_code=400, detail="文档未被锁定")
    
    if document.get('locked_by') != current_user.id:
        raise HTTPException(status_code=403, detail="只有锁定者才能解锁文档")
    
    try:
        unlock_document(db, document_id, current_user.id)
        return {"message": "文档已解锁"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("解锁文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="解锁文档失败")


# ==================== 导出/导入相关路由 ====================

@router.get("/documents/{document_id}/export", summary="导出文档", description="将文档导出为指定格式")
async def export_document_endpoint(
    document_id: int,
    format: str = "html",
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    request: Request = None,
):
    """导出文档"""
    if not is_feature_enabled(db, "feature.export.enabled", True):
        raise HTTPException(status_code=403, detail="导出功能已禁用")

    # 先检查文档是否存在且用户有权限
    document = get_document(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    try:
        content = document.get('content', '')
        title = document.get('title', '文档')
        
        if format.lower() == 'markdown':
            # 简单的 HTML 到 Markdown 转换
            markdown_content = htmlToMarkdown(content)
            log_action(
                db,
                user_id=current_user.id,
                action="export.request",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"format": "markdown"},
            )
            ascii_name = f"document_{document_id}.md"
            cd = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(ascii_name)}'
            return Response(
                content=markdown_content,
                media_type="text/markdown",
                headers={"Content-Disposition": cd}
            )
        elif format.lower() == 'html':
            log_action(
                db,
                user_id=current_user.id,
                action="export.request",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"format": "html"},
            )
            ascii_name = f"document_{document_id}.html"
            cd = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(ascii_name)}'
            return Response(
                content=content,
                media_type="text/html",
                headers={"Content-Disposition": cd}
            )
        elif format.lower() == 'pdf':
            # PDF 导出：使用 xhtml2pdf 将 HTML 转换为 PDF
            
            # 包装 HTML 内容，确保正确的编码和样式
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{title}</title>
                <style>
                    body {{ font-family: SimSun, Arial, sans-serif; }}
                </style>
            </head>
            <body>
                {content}
            </body>
            </html>
            """
            
            pdf_buffer = io.BytesIO()
            pisa_status = pisa.CreatePDF(html_template, dest=pdf_buffer, encoding='utf-8')
            
            if pisa_status.err:
                raise HTTPException(status_code=500, detail="PDF 转换失败")
            
            pdf_buffer.seek(0)
            pdf_content = pdf_buffer.read()
            
            log_action(
                db,
                user_id=current_user.id,
                action="export.request",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"format": "pdf"},
            )
            ascii_name = f"document_{document_id}.pdf"
            cd = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(ascii_name)}'
            return Response(
                content=pdf_content,
                media_type="application/pdf",
                headers={"Content-Disposition": cd}
            )
        elif format.lower() == 'docx' or format.lower() == 'word':
            # Word 导出：使用 python-docx 将 HTML 转换为 DOCX
            
            doc = DocxDocument()
            
            # 将 HTML 转换为纯文本（简化处理）
            text_content = htmlToMarkdown(content)
            
            # 按段落添加内容
            paragraphs = text_content.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    # 处理标题
                    if para.startswith('# '):
                        doc.add_heading(para[2:].strip(), level=1)
                    elif para.startswith('## '):
                        doc.add_heading(para[3:].strip(), level=2)
                    elif para.startswith('### '):
                        doc.add_heading(para[4:].strip(), level=3)
                    else:
                        doc.add_paragraph(para.strip())
            
            docx_buffer = io.BytesIO()
            doc.save(docx_buffer)
            docx_buffer.seek(0)
            docx_content = docx_buffer.read()
            
            log_action(
                db,
                user_id=current_user.id,
                action="export.request",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"format": "docx"},
            )
            ascii_name = f"document_{document_id}.docx"
            cd = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(ascii_name)}'
            return Response(
                content=docx_content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": cd}
            )
        else:
            raise HTTPException(status_code=400, detail="不支持的导出格式")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="导出文档失败")


@router.post("/documents/import", summary="导入文档", description="从上传的文件创建新文档")
async def import_document_endpoint(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """导入文档"""
    try:
        # 读取文件内容
        content = await file.read()
        
        # 根据文件类型处理内容
        if file.filename.endswith('.md') or file.filename.endswith('.txt'):
            # Markdown 或纯文本文件，直接使用
            text_content = content.decode('utf-8')
            html_content = markdownToHtml(text_content)
        elif file.filename.endswith('.html'):
            # HTML 文件，直接使用
            html_content = content.decode('utf-8')
        elif file.filename.endswith('.docx'):
            # Word 文档导入：使用 python-docx 读取
            
            docx_buffer = io.BytesIO(content)
            doc = DocxDocument(docx_buffer)
            
            # 提取段落内容并转换为 HTML
            html_parts = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    # 检查段落样式判断标题级别
                    if para.style.name.startswith('Heading 1'):
                        html_parts.append(f'<h1>{text}</h1>')
                    elif para.style.name.startswith('Heading 2'):
                        html_parts.append(f'<h2>{text}</h2>')
                    elif para.style.name.startswith('Heading 3'):
                        html_parts.append(f'<h3>{text}</h3>')
                    else:
                        html_parts.append(f'<p>{text}</p>')
            
            html_content = '\n'.join(html_parts)
        elif file.filename.endswith('.pdf'):
            # PDF 文档导入：使用 pdfplumber 提取文本
            
            pdf_buffer = io.BytesIO(content)
            html_parts = []
            
            with pdfplumber.open(pdf_buffer) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        # 按行分割并转换为段落
                        lines = text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line:
                                html_parts.append(f'<p>{line}</p>')
            
            html_content = '\n'.join(html_parts)
        else:
            # 其他文件类型，作为纯文本处理
            text_content = content.decode('utf-8')
            html_content = f"<p>{text_content.replace(chr(10), '<br>')}</p>"
        
        # 创建文档
        document_data = {
            'title': title,
            'content': html_content,
            'status': 'active'
        }
        
        new_document = create_document(db, document_data, current_user.id)
        
        return {
            "id": new_document['id'],
            "title": new_document['title'],
            "message": "文档导入成功"
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8 编码的文件")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导入文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="导入文档失败")


# ==================== 文档 CRUD 相关路由 ====================

@router.post("/documents", response_model=Document, status_code=status.HTTP_201_CREATED, summary="创建文档", description="创建新的协作文档")
async def create_document_endpoint(
    document: DocumentCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    request: Request = None,
):
    """创建文档"""
    try:
        new_document = create_document(db, document, current_user.id)
        try:
            log_action(
                db,
                user_id=current_user.id,
                action="document.create",
                resource_type="document",
                resource_id=new_document.get("id"),
                request=request,
            )
        except Exception:
            pass

        return Document(
            id=new_document['id'],
            owner_id=new_document['owner_id'],
            title=new_document['title'],
            content=new_document['content'],
            status=new_document['status'],
            folder_name=new_document.get('folder_name'),
            tags=new_document.get('tags'),
            is_locked=new_document.get('is_locked', False),
            created_at=new_document['created_at'],
            updated_at=new_document['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档失败")


@router.get("/documents/shared", response_model=List[Document], summary="获取共享文档列表", description="获取当前用户作为协作者的文档列表")
async def get_shared_documents_endpoint(
    current_user = Depends(get_current_user), 
    db = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取共享文档列表"""
    try:
        documents = get_shared_documents(db, current_user.id, skip=skip, limit=limit)
        return [
            Document(
                id=doc['id'],
                owner_id=doc['owner_id'],
                title=doc['title'],
                content=doc['content'],
                status=doc['status'],
                folder_name=doc.get('folder_name'),
                tags=doc.get('tags'),
                is_locked=doc.get('is_locked', False),
                locked_by=doc.get('locked_by'),
                created_at=doc['created_at'],
                updated_at=doc['updated_at']
            )
            for doc in documents
        ]
    except Exception as e:
        logger.error("获取共享文档列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取共享文档列表失败")


@router.get("/documents/{document_id}", response_model=Document, summary="获取文档详情", description="根据文档ID获取文档详细内容")
async def get_document_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文档详情"""
    from app.services.document_service import get_document_with_collaborators, check_document_permission
    # 先检查权限
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="文档不存在或无权限")
    
    document = get_document_with_collaborators(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    return Document(
        id=document['id'],
        owner_id=document['owner_id'],
        title=document['title'],
        content=document['content'],
        status=document['status'],
        folder_name=document.get('folder_name'),
        tags=document.get('tags'),
        is_locked=document.get('is_locked', False),
        locked_by=document.get('locked_by'),
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
    from app.services.document_service import get_document_with_collaborators, check_document_permission
    
    # 检查文档权限
    document = get_document_with_collaborators(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    
    # 检查编辑权限
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_edit"]:
        raise HTTPException(status_code=403, detail="无编辑权限")
    
    # 检查文档是否被锁定
    if document.get('is_locked') and document.get('locked_by') != current_user.id:
        raise HTTPException(status_code=403, detail="文档已被锁定，无法编辑")
    
    try:
        # 使用实际操作者ID进行更新（update_document函数参数已改为user_id）
        updated_document = update_document(db, document_id, document_update, current_user.id)
        if not updated_document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return Document(
            id=updated_document['id'],
            owner_id=updated_document['owner_id'],
            title=updated_document['title'],
            content=updated_document['content'],
            status=updated_document['status'],
            folder_name=updated_document.get('folder_name'),
            tags=updated_document.get('tags'),
            is_locked=updated_document.get('is_locked', False),
            locked_by=updated_document.get('locked_by'),
            created_at=updated_document['created_at'],
            updated_at=updated_document['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新文档失败: %s", e, exc_info=True)
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
        logger.error("删除文档失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="删除文档失败")


# ==================== 文档版本相关路由 ====================

@router.get("/documents/{document_id}/versions", response_model=List[dict], summary="获取文档版本列表", description="获取文档的所有历史版本")
async def get_document_versions_endpoint(
    document_id: int, 
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文档版本列表"""
    # 检查文档权限（允许所有者或协作者查看）
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="无权限查看此文档")
    
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
    # 检查文档权限（需要编辑权限才能创建版本）
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_edit"]:
        raise HTTPException(status_code=403, detail="无编辑权限，无法创建版本")
    
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文档版本失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="创建文档版本失败")


# ==================== 模板相关路由 ====================

@router.get("/templates", response_model=List[Template], summary="获取模板列表", description="获取所有可用的文档模板")
async def get_templates_endpoint(
    category: Optional[str] = None,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取模板列表"""
    templates = get_templates(db, category, active_only=True)
    return templates


@router.get("/templates/{template_id}", response_model=Template, summary="获取模板详情", description="根据模板ID获取模板详细内容")
async def get_template_endpoint(
    template_id: int, 
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取模板详情"""
    template = get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return Template(
        id=template['id'],
        name=template['name'],
        description=template['description'],
        content=template['content'],
        category=template['category'],
        is_active=template['is_active'],
        created_at=template['created_at'],
        updated_at=template['updated_at']
    )


@router.post("/templates", response_model=Template, status_code=status.HTTP_201_CREATED, summary="创建模板", description="创建新的文档模板")
async def create_template_endpoint(
    template: TemplateCreate,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """创建模板"""
    try:
        new_template = create_template(db, template)
        return Template(
            id=new_template['id'],
            name=new_template['name'],
            description=new_template['description'],
            content=new_template['content'],
            category=new_template['category'],
            is_active=new_template['is_active'],
            created_at=new_template['created_at'],
            updated_at=new_template['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建模板失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="创建模板失败")


@router.put("/templates/{template_id}", response_model=Template, summary="更新模板", description="更新模板内容")
async def update_template_endpoint(
    template_id: int,
    template_update: TemplateUpdate,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """更新模板"""
    try:
        updated_template = update_template(db, template_id, template_update)
        if not updated_template:
            raise HTTPException(status_code=404, detail="模板不存在")
        
        return Template(
            id=updated_template['id'],
            name=updated_template['name'],
            description=updated_template['description'],
            content=updated_template['content'],
            category=updated_template['category'],
            is_active=updated_template['is_active'],
            created_at=updated_template['created_at'],
            updated_at=updated_template['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新模板失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="更新模板失败")


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除模板", description="删除指定的模板")
async def delete_template_endpoint(
    template_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """删除模板"""
    try:
        success = delete_template(db, template_id)
        if not success:
            raise HTTPException(status_code=404, detail="模板不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除模板失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="删除模板失败")


# ==================== 评论与任务基础接口 ====================


@router.get("/documents/{document_id}/comments", response_model=List[Comment], summary="获取文档评论")
async def get_document_comments(
    document_id: int,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    # 先校验文档存在且用户有权限
    from app.services.document_service import check_document_permission
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="文档不存在或无权访问")
    
    try:
        return list_comments(db, document_id)
    except Exception as e:
        logger.error("获取评论失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取评论失败")


@router.post("/documents/{document_id}/comments", response_model=Comment, summary="创建评论")
async def create_document_comment(
    document_id: int,
    comment_in: CommentCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    request: Request = None,
):
    # 先校验文档存在且用户有权限
    from app.services.document_service import check_document_permission
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="文档不存在或无权访问")
        
    try:
        comment = create_comment(
            db,
            document_id,
            current_user.id,
            comment_in.content,
            comment_in.line_no,
            None,
            None,
            None,
        )
        try:
            log_action(
                db,
                user_id=current_user.id,
                action="comment.create",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"comment_id": getattr(comment, 'id', None) if hasattr(comment, 'id') else comment.get("id") if isinstance(comment, dict) else None},
            )
        except Exception:
            pass
        return comment
    except Exception as e:
        logger.error("创建评论失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="创建评论失败")


@router.get("/documents/{document_id}/tasks", response_model=List[Task], summary="获取文档任务")
async def get_document_tasks(document_id: int, current_user=Depends(get_current_user), db=Depends(get_db)):
    # 先校验文档存在且用户有权限
    from app.services.document_service import check_document_permission
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="文档不存在或无权访问")
        
    try:
        return list_tasks(db, document_id)
    except Exception as e:
        logger.error("获取任务失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务失败")


@router.post("/documents/{document_id}/tasks", response_model=Task, summary="创建任务")
async def create_document_task(
    document_id: int,
    task_in: TaskCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    request: Request = None,
):
    # 先校验文档存在且用户有权限（需要编辑权限才能创建任务）
    from app.services.document_service import check_document_permission
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_edit"]:
        raise HTTPException(status_code=403, detail="无编辑权限，无法创建任务")

    try:
        assignee_id = getattr(task_in, 'assignee_id', None) or getattr(task_in, 'assigned_to', None)
        due = getattr(task_in, "due_at", None) or getattr(task_in, "due_date", None) or getattr(task_in, "deadline", None)
        task = create_task(
            db,
            document_id,
            current_user.id,
            task_in.title,
            task_in.description,
            assignee_id,
            due,
        )
        try:
            log_action(
                db,
                user_id=current_user.id,
                action="task.create",
                resource_type="document",
                resource_id=document_id,
                request=request,
                meta={"task_id": task.get("id") if isinstance(task, dict) else getattr(task, "id", None)},
            )
        except Exception:
            pass
        try:
            if task.get("assignee_id"):
                from app.services.notification_service import create_notification
                from app.services.notification_ws_manager import notification_ws_manager
                notification = create_notification(
                    db,
                    user_id=task["assignee_id"],
                    type="task",
                    title="你有新的任务",
                    content=task_in.title,
                    payload={"task_id": task.get("id"), "document_id": document_id},
                )
                # 确保WebSocket推送（在异步上下文中）
                if notification:
                    import asyncio
                    try:
                        asyncio.create_task(notification_ws_manager.async_send_notification(task["assignee_id"], notification))
                    except Exception as ws_err:
                        logger.warning("WebSocket推送失败: %s", ws_err)
        except Exception as notify_err:
            logger.warning("创建任务通知失败: %s", notify_err)
        return task
    except Exception as e:
        logger.error("创建任务失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="创建任务失败")


@router.patch("/tasks/{task_id}", response_model=Task, summary="更新任务")
async def update_task_endpoint(
    task_id: int,
    task_in: TaskUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    # 先获取任务信息以检查所属文档
    from app.services.task_service import list_tasks
    # 查询任务获取document_id
    task_rows = db.query("SELECT document_id FROM tasks WHERE id = %s LIMIT 1", (task_id,))
    if not task_rows:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    document_id = task_rows[0][0]
    
    # 检查文档权限
    from app.services.document_service import check_document_permission
    permission = check_document_permission(db, document_id, current_user.id)
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="无权访问该任务所属的文档")
        
    try:
        due = getattr(task_in, "due_at", None) or getattr(task_in, "due_date", None) or getattr(task_in, "deadline", None)
        return update_task(db, task_id, status=task_in.status, due_at=due, assignee_id=task_in.assigned_to)
    except Exception as e:
        logger.error("更新任务失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="更新任务失败")


# ==================== 文档共享相关路由 ====================

@router.post("/documents/{document_id}/collaborators", summary="添加文档协作者", description="为文档添加协作者")
async def add_collaborator_endpoint(
    document_id: int,
    collaborator_data: dict,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """添加文档协作者"""
    # 验证请求数据
    username = collaborator_data.get("username")
    role = collaborator_data.get("role", "editor")
    
    if not username:
        raise HTTPException(status_code=400, detail="缺少用户名")
    
    if role not in ["editor", "viewer"]:
        raise HTTPException(status_code=400, detail="角色只能是 editor 或 viewer")
    
    # 检查文档是否存在且用户为所有者
    if not is_document_owner(db, document_id, current_user.id):
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    
    # 获取协作者用户ID
    try:
        user_rows = db.query("SELECT id FROM users WHERE username = %s LIMIT 1", (username,))
        
        if not user_rows:
            raise HTTPException(status_code=404, detail="协作用户不存在")
            
        collaborator_user_id = user_rows[0][0]
        
        # 不能添加自己为协作者
        if collaborator_user_id == current_user.id:
            raise HTTPException(status_code=400, detail="不能添加自己为协作者")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取协作用户信息失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取用户信息失败")
    
    # 添加协作者
    try:
        success = add_collaborator(db, document_id, current_user.id, collaborator_user_id, role)
        if not success:
            raise HTTPException(status_code=500, detail="添加协作者失败")
            
        return {"message": f"已成功添加 {username} 为文档协作者", "role": role}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("添加协作者失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="添加协作者失败")


@router.post("/documents/{document_id}/collaborators/batch", summary="批量添加文档协作者", description="批量添加多个协作者")
async def batch_add_collaborators_endpoint(
    document_id: int,
    batch_data: dict,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """批量添加文档协作者"""
    users = batch_data.get("users", [])
    
    if not users:
        raise HTTPException(status_code=400, detail="用户列表不能为空")
    
    # 检查文档是否存在且用户为所有者
    if not is_document_owner(db, document_id, current_user.id):
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    
    # 批量添加协作者
    try:
        results = batch_add_collaborators(db, document_id, current_user.id, users)
        
        # 统计成功和失败数量
        success_count = sum(1 for r in results if r["success"])
        failed_count = len(results) - success_count
        
        return {
            "message": f"批量添加完成：成功 {success_count} 个，失败 {failed_count} 个",
            "success": success_count,
            "failed": failed_count,
            "results": results
        }
        
    except Exception as e:
        logger.error("批量添加协作者失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="批量添加协作者失败")


@router.get("/documents/{document_id}/collaborators", summary="获取文档协作者列表", description="获取文档的所有协作者")
async def get_collaborators_endpoint(
    document_id: int,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """获取文档协作者列表"""
    # 检查文档权限
    permission = check_document_permission(db, document_id, current_user.id)
    
    if not permission["can_view"]:
        raise HTTPException(status_code=403, detail="无权限查看此文档")
    
    try:
        collaborators = get_collaborators(db, document_id, current_user.id)
        return {"collaborators": collaborators}
        
    except Exception as e:
        logger.error("获取协作者列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取协作者列表失败")


@router.delete("/documents/{document_id}/collaborators/{username}", summary="移除文档协作者（通过用户名）", description="从文档中移除指定协作者")
async def remove_collaborator_by_username_endpoint(
    document_id: int,
    username: str,
    current_user = Depends(get_current_user), 
    db = Depends(get_db)
):
    """移除文档协作者（通过用户名）"""
    # 检查文档是否存在且用户为所有者
    if not is_document_owner(db, document_id, current_user.id):
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    
    # 获取协作者用户ID
    try:
        user_rows = db.query("SELECT id FROM users WHERE username = %s LIMIT 1", (username,))
        
        if not user_rows:
            raise HTTPException(status_code=404, detail="协作用户不存在")
            
        collaborator_user_id = user_rows[0][0]
        
        # 不能移除自己
        if collaborator_user_id == current_user.id:
            raise HTTPException(status_code=400, detail="不能移除自己")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取协作用户信息失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取用户信息失败")
    
    # 移除协作者
    try:
        success = remove_collaborator(db, document_id, current_user.id, collaborator_user_id)
        if not success:
            raise HTTPException(status_code=500, detail="移除协作者失败")
            
        return {"message": f"已成功移除协作者 {username}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("移除协作者失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="移除协作者失败")


