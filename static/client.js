// API 客户端 - 处理用户认证和文档管理
class ApiClient {
    constructor() {
        this.baseURL = '';
        this.token = localStorage.getItem('access_token') || '';
        this.username = localStorage.getItem('username') || '';
    }

    // 设置认证 token
    setToken(token, username, userId) {
        this.token = token;
        this.username = username;
        localStorage.setItem('access_token', token);
        localStorage.setItem('username', username);
        if (userId) {
            localStorage.setItem('user_id', userId);
        }
    }

    // 清除认证信息
    clearAuth() {
        this.token = '';
        this.username = '';
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        localStorage.removeItem('user_id');
    }

    // 通用请求方法
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}/api/v1${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ... options.headers
            },
            ... options
        };

        // 如果有 token，添加到请求头
        if (this.token) {
            config.headers.Authorization = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                // 如果是认证错误，清除本地 token
                if (response.status === 401) {
                    this.clearAuth();
                    showLoginForm();
                    throw new Error('登录已过期，请重新登录');
                }
                throw new Error(data.detail || '请求失败');
            }

            return data;
        } catch (error) {
            console.error('API 请求错误:', error);
            throw error;
        }
    }

    // 用户注册
    async register(username, email, password) {
        return this.request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, email, password })
        });
    }

    // 用户登录
    async login(username, password) {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${this.baseURL}/api/v1/auth/token`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '登录失败');
        }

        const data = await response.json();
        // 传递 user_id 到 setToken 方法，假设后端返回 user_id 字段
        this.setToken(data.access_token, username, data.user_id);
        return data;
    }

    // 获取当前用户信息
    async getCurrentUser() {
        return this.request('/auth/me');
    }

    // 获取文档列表
    async getDocuments() {
        return this.request('/documents');
    }

    // 获取共享文档列表
    async getSharedDocuments() {
        return this.request('/documents/shared');
    }

    // 创建文档
    async createDocument(title, content = '', status = 'active') {
        return this.request('/documents', {
            method: 'POST',
            body: JSON.stringify({ title, content, status })
        });
    }

    // 获取单个文档
    async getDocument(id) {
        return this.request(`/documents/${id}`);
    }

    // 更新文档
    async updateDocument(id, data) {
        return this.request(`/documents/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    // 删除文档
    async deleteDocument(id) {
        return this.request(`/documents/${id}`, {
            method: 'DELETE'
        });
    }

    // 获取模板列表
    async getTemplates(category = null) {
        const url = category ? `/templates?category=${category}` : '/templates';
        return this.request(url);
    }

    // 获取单个模板
    async getTemplate(id) {
        return this.request(`/templates/${id}`);
    }

    // 创建模板
    async createTemplate(template) {
        return this.request('/templates', {
            method: 'POST',
            body: JSON.stringify(template)
        });
    }

    // 更新模板
    async updateTemplate(id, template) {
        return this.request(`/templates/${id}`, {
            method: 'PUT',
            body: JSON.stringify(template)
        });
    }

    // 删除模板
    async deleteTemplate(id) {
        return this.request(`/templates/${id}`, {
            method: 'DELETE'
        });
    }

    // 搜索文档
    async searchDocuments(params) {
        const queryString = new URLSearchParams(params).toString();
        return this.request(`/documents/search?${queryString}`);
    }

    // 获取文件夹列表
    async getFolders() {
        return this.request('/folders');
    }

    // 获取标签列表
    async getTags() {
        return this.request('/tags');
    }

    // 锁定文档
    async lockDocument(id) {
        return this.request(`/documents/${id}/lock`, {
            method: 'POST'
        });
    }

    // 解锁文档
    async unlockDocument(id) {
        return this.request(`/documents/${id}/unlock`, {
            method: 'POST'
        });
    }

    // 导出文档
    async exportDocument(id, format = 'html') {
        // 确保 format 是字符串，防止传入 Promise
        const formatStr = String(format);
        const validFormats = ['html', 'markdown', 'pdf', 'docx'];
        if (!validFormats.includes(formatStr)) {
            throw new Error(`无效的导出格式: ${formatStr}。支持的格式: ${validFormats.join(', ')}`);
        }

        const response = await fetch(`${this.baseURL}/api/v1/documents/${id}/export?format=${formatStr}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        
        if (!response.ok) {
            throw new Error('导出失败');
        }
        
        return response;
    }

    // 导入文档
    async importDocument(title, file) {
        const formData = new FormData();
        formData.append('title', title);
        formData.append('file', file);
        
        const response = await fetch(`${this.baseURL}/api/v1/documents/import`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '导入失败');
        }
        
        return response.json();
    }
}

// 创建 API 客户端实例
const api = new ApiClient();

// UI 控制函数
function showLoginForm() {
    document.getElementById('login-section').style.display = 'block';
    document.getElementById('register-section').style.display = 'none';
    document.getElementById('documents-section').style.display = 'none';
}

function showRegisterForm() {
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('register-section').style.display = 'block';
    document.getElementById('documents-section').style.display = 'none';
}

function showDocumentsSection() {
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('register-section').style.display = 'none';
    document.getElementById('documents-section').style.display = 'block';
}

function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = message;
        element.classList.remove('d-none');
        element.style.display = 'block';
        setTimeout(() => {
            element.classList.add('d-none');
            element.style.display = 'none';
        }, 5000);
    }
    // 同时显示 Toast 通知
    if (typeof Toast !== 'undefined') {
        Toast.error(message);
    }
}

function formatDate(dateString) {
    if (!dateString) return '未知时间';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
}

// 加载文档列表
async function loadDocuments(folder = null) {
    try {
        const [ownedDocuments, sharedDocuments] = await Promise.all([
            api.getDocuments(folder),
            api.getSharedDocuments()
        ]);
        
        // 分别显示我的文档和共享文档
        renderDocumentList(ownedDocuments.map(doc => ({ ...doc, is_shared: false })));
        renderSharedDocumentList(sharedDocuments.map(doc => ({ ...doc, is_shared: true })));
    } catch (error) {
        console.error('加载文档列表失败:', error);
        showError('document-error', '加载文档列表失败: ' + error.message);
    }
}

// 渲染共享文档列表
const renderSharedDocumentList = (documents) => {
    const sharedDocumentList = document.getElementById('shared-document-list');
    const noSharedDocuments = document.getElementById('no-shared-documents');

    if (!sharedDocumentList || !noSharedDocuments) return;

    if (documents.length === 0) {
        sharedDocumentList.innerHTML = '';
        noSharedDocuments.style.display = 'block';
    } else {
        noSharedDocuments.style.display = 'none';
        sharedDocumentList.innerHTML = documents.map(doc => {
            const tags = doc.tags ? doc.tags.split(',').map(tag => 
                `<span class="badge bg-info text-dark tag me-1">${tag.trim()}</span>`
            ).join('') : '<span class="text-muted small">无标签</span>';
            const lockBadge = doc.is_locked ? '<span class="badge bg-danger ms-2"><i class="bi bi-lock-fill"></i> 已锁定</span>' : '';
            
            return `
                <div class="col-md-6 col-lg-4">
                    <div class="card document-card h-100 shadow-sm">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="bi bi-file-earmark-text text-primary me-1"></i>
                                ${doc.title}
                                ${lockBadge}
                                <span class="badge bg-success ms-2">共享</span>
                            </h5>
                            <div class="document-meta mb-2">
                                <div><i class="bi bi-folder me-1"></i>${doc.folder_name || '未分类'}</div>
                                <div class="mt-1">${tags}</div>
                                <div class="mt-1"><i class="bi bi-person me-1"></i>所有者ID: ${doc.owner_id}</div>
                            </div>
                            <p class="card-text small text-muted">
                                <i class="bi bi-clock me-1"></i>更新于 ${formatDate(doc.updated_at)}
                            </p>
                        </div>
                        <div class="card-footer bg-transparent border-top-0">
                            <div class="btn-group btn-group-sm w-100">
                                <button class="btn btn-primary" onclick="openDocument(${doc.id})" ${doc.is_locked ? 'disabled' : ''}>
                                    <i class="bi bi-pencil-square me-1"></i>编辑
                                </button>
                                <button class="btn btn-outline-secondary" onclick="exportDocument(${doc.id})">
                                    <i class="bi bi-download me-1"></i>导出
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
};

const renderDocumentList = (documents) => {
    const documentList = document.getElementById('document-list');
    const noDocuments = document.getElementById('no-documents');

    if (documents.length === 0) {
        documentList.innerHTML = '';
        noDocuments.style.display = 'block';
    } else {
        noDocuments.style.display = 'none';
        documentList.innerHTML = documents.map(doc => {
            const tags = doc.tags ? doc.tags.split(',').map(tag => 
                `<span class="badge bg-info text-dark tag me-1">${tag.trim()}</span>`
            ).join('') : '<span class="text-muted small">无标签</span>';
            const lockBadge = doc.is_locked ? '<span class="badge bg-danger ms-2"><i class="bi bi-lock-fill"></i> 已锁定</span>' : '';
            const sharedBadge = doc.is_shared ? '<span class="badge bg-success ms-2">共享</span>' : '';
            
            return `
                <div class="col-md-6 col-lg-4">
                    <div class="card document-card h-100 shadow-sm">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="bi bi-file-earmark-text text-primary me-1"></i>
                                ${doc.title}
                                ${lockBadge}
                                ${sharedBadge}
                            </h5>
                            <div class="document-meta mb-2">
                                <div><i class="bi bi-folder me-1"></i>${doc.folder_name || '未分类'}</div>
                                <div class="mt-1">${tags}</div>
                            </div>
                            <p class="card-text small text-muted">
                                <i class="bi bi-clock me-1"></i>更新于 ${formatDate(doc.updated_at)}
                            </p>
                        </div>
                        <div class="card-footer bg-transparent border-top-0">
                            <div class="d-flex flex-wrap gap-1">
                                <button class="btn btn-primary btn-sm" onclick="openDocument(${doc.id})" ${doc.is_locked ? 'disabled' : ''}>
                                    <i class="bi bi-pencil-square me-1"></i>编辑
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="exportDocument(${doc.id})">
                                    <i class="bi bi-download"></i>
                                </button>
                                ${!doc.is_shared && !doc.is_locked ? `
                                    <button class="btn btn-outline-warning btn-sm" onclick="lockDocument(${doc.id})">
                                        <i class="bi bi-lock"></i>
                                    </button>
                                ` : ''}
                                ${!doc.is_shared && doc.is_locked && doc.locked_by === getCurrentUserId() ? `
                                    <button class="btn btn-outline-success btn-sm" onclick="unlockDocument(${doc.id})">
                                        <i class="bi bi-unlock"></i>
                                    </button>
                                ` : ''}
                                ${!doc.is_shared ? `
                                    <button class="btn btn-outline-danger btn-sm" onclick="deleteDocument(${doc.id})">
                                        <i class="bi bi-trash"></i>
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
};

// 搜索文档
async function searchDocuments() {
    const keyword = document.getElementById('search-keyword').value.trim();
    const tags = document.getElementById('search-tags').value.trim();
    const folder = document.getElementById('search-folder').value;
    const sortBy = document.getElementById('search-sort').value;
    const order = document.getElementById('search-order').value;
    
    const params = {};
    if (keyword) params.keyword = keyword;
    if (tags) params.tags = tags;
    if (folder) params.folder = folder;
    if (sortBy) params.sort_by = sortBy;
    if (order) params.order = order;
    
    try {
        const documents = await api.searchDocuments(params);
        renderDocumentList(documents);
        
        // 显示搜索结果数量
        const documentList = document.getElementById('document-list');
        const resultCount = document.createElement('div');
        resultCount.style.cssText = 'margin-bottom: 15px; padding: 10px; background-color: #e3f2fd; border-radius: 5px; color: #1976d2;';
        resultCount.textContent = `找到 ${documents.length} 个文档`;
        documentList.insertBefore(resultCount, documentList.firstChild);
    } catch (error) {
        console.error('搜索文档失败:', error);
        showError('search-error', '搜索文档失败: ' + error.message);
    }
}

// 加载文件夹和标签
async function loadFilters() {
    try {
        const [folders, tags] = await Promise.all([
            api.getFolders(),
            api.getTags()
        ]);
        
        // 更新文件夹下拉框
        const folderSelect = document.getElementById('search-folder');
        if (folderSelect) {
            folderSelect.innerHTML = '<option value="">所有文件夹</option>' + 
                folders.map(folder => `<option value="${folder}">${folder}</option>`).join('');
        }
        
        // 显示标签列表
        const tagsContainer = document.getElementById('tags-container');
        if (tagsContainer && tags.length > 0) {
            tagsContainer.innerHTML = '<h4>标签:</h4>' + 
                tags.map(tag => `<span class="tag clickable-tag" onclick="addTagToSearch('${tag}')">${tag}</span>`).join('');
        }
    } catch (error) {
        console.error('加载过滤器失败:', error);
    }
}

// 添加标签到搜索
function addTagToSearch(tag) {
    const tagsInput = document.getElementById('search-tags');
    const currentTags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t);
    
    if (!currentTags.includes(tag)) {
        currentTags.push(tag);
        tagsInput.value = currentTags.join(', ');
    }
}

// 锁定文档
async function lockDocument(documentId) {
    try {
        await api.lockDocument(documentId);
        await loadDocuments(); // 重新加载文档列表
    } catch (error) {
        console.error('锁定文档失败:', error);
        Toast.error('锁定文档失败: ' + error.message);
    }
}

// 解锁文档
async function unlockDocument(documentId) {
    try {
        await api.unlockDocument(documentId);
        await loadDocuments(); // 重新加载文档列表
    } catch (error) {
        console.error('解锁文档失败:', error);
        Toast.error('解锁文档失败: ' + error.message);
    }
}

// 获取当前用户ID
function getCurrentUserId() {
    // 从 localStorage 获取 user_id，并转换为整数以确保与后端返回的 locked_by 字段类型一致
    const userId = localStorage.getItem('user_id');
    if (userId) {
        const parsedId = parseInt(userId, 10);
        return isNaN(parsedId) ? null : parsedId;
    }
    return null;
}

// 导出文档
async function exportDocument(documentId) {
    try {
        // 显示格式选择对话框
        const format = await showExportDialog();
        if (!format) return;
        
        const response = await api.exportDocument(documentId, format);
        
        // 创建下载链接
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // 从响应头获取文件名
        const contentDisposition = response.headers.get('content-disposition');
        let filename = 'document';
        if (contentDisposition) {
            const matches = contentDisposition.match(/filename=(. +)/);
            if (matches) filename = matches[1];
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        console.error('导出文档失败:', error);
        Toast.error('导出文档失败: ' + error.message);
    }
}

// 显示导出格式选择对话框
function showExportDialog() {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            z-index: 1000;
            display: flex;
            justify-content: center;
            align-items: center;
        `;
        
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        `;
        
        dialog.innerHTML = `
            <h3 style="margin-top: 0;">选择导出格式</h3>
            <div style="margin: 20px 0;">
                <button id="export-html" style="margin: 0 10px; padding: 10px 20px;">HTML</button>
                <button id="export-markdown" style="margin: 0 10px; padding: 10px 20px;">Markdown</button>
                <button id="export-pdf" style="margin: 0 10px; padding: 10px 20px;">PDF</button>
                <button id="export-word" style="margin: 0 10px; padding: 10px 20px;">Word</button>
                <button id="export-cancel" style="margin: 0 10px; padding: 10px 20px; background-color: #6c757d;">取消</button>
            </div>
        `;
        
        modal.appendChild(dialog);
        document.body.appendChild(modal);
        
        document.getElementById('export-html').addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve('html');
        });
        
        document.getElementById('export-markdown').addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve('markdown');
        });
        
        document.getElementById('export-pdf').addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve('pdf');
        });
        
        document.getElementById('export-word').addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve('docx');
        });
        
        document.getElementById('export-cancel').addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve(null);
        });
        
        // 点击背景关闭
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                document.body.removeChild(modal);
                resolve(null);
            }
        });
    });
}

// 导入文档
async function importDocument() {
    try {
        // 创建文件输入元素
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.md,. txt,.html,. docx,. pdf';
        fileInput.style.display = 'none';
        
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            
            const title = prompt('请输入文档标题:', file.name.replace(/\.[^/.]+$/, ''));
            if (!title) return;
            
            try {
                const result = await api.importDocument(title, file);
                Toast.success(`文档 "${result.title}" 导入成功！`);
                await loadDocuments(); // 重新加载文档列表
            } catch (error) {
                console.error('导入文档失败:', error);
                Toast.error('导入文档失败: ' + error.message);
            }
        });
        
        document.body.appendChild(fileInput);
        fileInput.click();
        document.body.removeChild(fileInput);
        
    } catch (error) {
        console.error('导入文档失败:', error);
        Toast.error('导入文档失败: ' + error.message);
    }
}

// 打开文档进行协同编辑
function openDocument(documentId) {
    const token = api.token;
    const username = api.username;
    window.location.href = `/test_collab.html?doc_id=${documentId}&token=${encodeURIComponent(token)}&username=${encodeURIComponent(username)}`;
}

// 删除文档
async function deleteDocument(documentId) {
    if (typeof Toast !== 'undefined' && Toast.confirm) {
        if (!await Toast.confirm('确定要删除这个文档吗？此操作不可恢复。')) {
            return;
        }
    } else if (!confirm('确定要删除这个文档吗？此操作不可恢复。')) {
        return;
    }

    try {
        await api.deleteDocument(documentId);
        await loadDocuments(); // 重新加载文档列表
        if (typeof Toast !== 'undefined') Toast.success('文档已删除');
    } catch (error) {
        console.error('删除文档失败:', error);
        if (typeof Toast !== 'undefined') {
            Toast.error('删除文档失败: ' + error.message);
        } else {
            alert('删除文档失败: ' + error.message);
        }
    }
}

// 创建新文档
async function createNewDocument() {
    // 先加载模板列表
    try {
        const templates = await api.getTemplates();
        showTemplateDialog(templates);
    } catch (error) {
        console.error('加载模板失败:', error);
        // 如果加载模板失败，直接创建空白文档
        createDocumentFromTemplate(null);
    }
}

// 显示模板选择对话框
function showTemplateDialog(templates) {
    // 创建模态对话框
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0,0,0,0.5);
        z-index: 1000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background-color: white;
        padding: 30px;
        border-radius: 8px;
        max-width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    `;
    
    dialog.innerHTML = `
        <h2 style="margin-top: 0; color: #333;">选择文档模板</h2>
        <div id="template-list" style="margin: 20px 0;">
            <div style="text-align: center; color: #666;">加载中...</div>
        </div>
        <div style="text-align: right; margin-top: 20px;">
            <button id="cancel-template" style="background-color: #6c757d; margin-right: 10px;">取消</button>
        </div>
    `;
    
    modal.appendChild(dialog);
    document.body.appendChild(modal);
    
    // 渲染模板列表
    const templateList = document.getElementById('template-list');
    const categories = {};
    
    // 按分类组织模板
    templates.forEach(template => {
        if (!categories[template.category]) {
            categories[template.category] = [];
        }
        categories[template.category].push(template);
    });
    
    let html = '';
    Object.keys(categories).forEach(category => {
        html += `<h3 style="color: #666; margin-bottom: 10px;">${getCategoryName(category)}</h3>`;
        html += '<div style="margin-bottom: 20px;">';
        
        categories[category].forEach(template => {
            html += `
                <div class="template-item" style="
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 15px;
                    margin-bottom: 10px;
                    cursor: pointer;
                    transition: background-color 0.2s;
                " data-template-id="${template.id}" data-template-content="${encodeURIComponent(template.content)}">
                    <h4 style="margin: 0 0 5px 0; color: #333;">${template.name}</h4>
                    <p style="margin: 0; color: #666; font-size: 14px;">${template.description || '无描述'}</p>
                </div>
            `;
        });
        
        html += '</div>';
    });
    
    // 添加空白文档选项
    html += `
        <h3 style="color: #666; margin-bottom: 10px;">其他</h3>
        <div class="template-item" style="
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: background-color 0.2s;
        " data-template-id="blank">
            <h4 style="margin: 0 0 5px 0; color: #333;">空白文档</h4>
            <p style="margin: 0; color: #666; font-size: 14px;">创建一个空白文档，自由发挥</p>
        </div>
    `;
    
    templateList.innerHTML = html;
    
    // 添加交互效果
    document.querySelectorAll('.template-item').forEach(item => {
        item.addEventListener('mouseenter', function() {
            this.style.backgroundColor = '#f8f9fa';
        });
        
        item.addEventListener('mouseleave', function() {
            this.style.backgroundColor = 'white';
        });
        
        item.addEventListener('click', function() {
            const templateId = this.dataset.templateId;
            const templateContent = this.dataset.templateContent ?  decodeURIComponent(this.dataset.templateContent) : '';
            createDocumentFromTemplate(templateId, templateContent);
            document.body.removeChild(modal);
        });
    });
    
    // 取消按钮
    document.getElementById('cancel-template').addEventListener('click', function() {
        document.body.removeChild(modal);
    });
    
    // 点击背景关闭
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
}

// 获取分类的中文名称
function getCategoryName(category) {
    const names = {
        'general': '通用',
        'business': '商务',
        'project': '项目',
        'technical': '技术'
    };
    return names[category] || category;
}

// 从模板创建文档
async function createDocumentFromTemplate(templateId, templateContent) {
    const title = prompt('请输入文档标题:', '新文档');
    if (!title) return;

    try {
        await api.createDocument(title, templateContent || '');
        await loadDocuments(); // 重新加载文档列表
    } catch (error) {
        console.error('创建文档失败:', error);
        Toast.error('创建文档失败: ' + error.message);
    }
}

// 检查登录状态
async function checkAuthStatus() {
    const token = localStorage.getItem('access_token');
    const username = localStorage.getItem('username');
    const userId = localStorage.getItem('user_id');

    if (token && username) {
        try {
            // 验证 token 是否有效
            await api.getCurrentUser();
            api.setToken(token, username, userId);
            document.getElementById('current-username').textContent = username;
            showDocumentsSection();
            await loadDocuments();
            await loadFilters(); // 加载过滤器
        } catch (error) {
            // token 无效，清除并显示登录表单
            api.clearAuth();
            showLoginForm();
        }
    } else {
        showLoginForm();
    }
}

// 切换高级搜索
function toggleAdvancedSearch() {
    const advancedSearch = document.getElementById('advanced-search');
    advancedSearch.style.display = advancedSearch.style.display === 'none' ? 'block' : 'none';
}

// 切换文件夹
function switchFolder(folder) {
    // 更新标签状态
    document.querySelectorAll('.folder-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.textContent === folder || '全部') {
            tab.classList.add('active');
        }
    });
    
    // 加载对应文件夹的文档
    loadDocuments(folder === '全部' ?  null : folder);
}

// 事件监听器
document.addEventListener('DOMContentLoaded', function() {
    // 登录表单
    document.getElementById('login-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        try {
            await api.login(username, password);
            document.getElementById('current-username').textContent = username;
            showDocumentsSection();
            await loadDocuments();
            await loadFilters(); // 加载过滤器
        } catch (error) {
            showError('login-error', error.message);
        }
    });

    // 注册表单
    document.getElementById('register-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        const username = document.getElementById('reg-username').value;
        const email = document.getElementById('reg-email').value;
        const password = document.getElementById('reg-password').value;

        try {
            await api.register(username, email, password);
            // 注册成功后自动登录
            await api.login(username, password);
            document.getElementById('current-username').textContent = username;
            showDocumentsSection();
            await loadDocuments();
        } catch (error) {
            showError('register-error', error.message);
        }
    });

    // 切换表单
    document.getElementById('show-register').addEventListener('click', showRegisterForm);
    document.getElementById('show-login').addEventListener('click', showLoginForm);

    // 退出登录
    document.getElementById('logout-btn').addEventListener('click', async function() {
        let shouldLogout = false;
        if (typeof Toast !== 'undefined' && Toast.confirm) {
            shouldLogout = await Toast.confirm('确定要退出登录吗？');
        } else {
            shouldLogout = confirm('确定要退出登录吗？');
        }
        
        if (shouldLogout) {
            api.clearAuth();
            showLoginForm();
        }
    });

    // 创建文档
    document.getElementById('create-document-btn').addEventListener('click', createNewDocument);

    // 导入文档
    document.getElementById('import-document-btn').addEventListener('click', importDocument);

    // 检查登录状态
    checkAuthStatus();
});
