// API 客户端 - 处理用户认证和文档管理
class ApiClient {
    constructor() {
        this.baseURL = '';
        this.token = localStorage.getItem('access_token') || '';
        this.username = localStorage.getItem('username') || '';
    }

    // 设置认证 token
    setToken(token, username) {
        this.token = token;
        this.username = username;
        localStorage.setItem('access_token', token);
        localStorage.setItem('username', username);
    }

    // 清除认证信息
    clearAuth() {
        this.token = '';
        this.username = '';
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
    }

    // 通用请求方法
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}/api/v1${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
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
        this.setToken(data.access_token, username);
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
    element.textContent = message;
    element.style.display = 'block';
    setTimeout(() => {
        element.style.display = 'none';
    }, 5000);
}

function formatDate(dateString) {
    if (!dateString) return '未知时间';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
}

// 加载文档列表
async function loadDocuments() {
    try {
        const documents = await api.getDocuments();
        const documentList = document.getElementById('document-list');
        const noDocuments = document.getElementById('no-documents');

        if (documents.length === 0) {
            documentList.innerHTML = '';
            noDocuments.style.display = 'block';
        } else {
            noDocuments.style.display = 'none';
            documentList.innerHTML = documents.map(doc => `
                <div class="document-item">
                    <div class="document-info">
                        <h3>${doc.title}</h3>
                        <p>创建时间: ${formatDate(doc.created_at)} | 更新时间: ${formatDate(doc.updated_at)}</p>
                    </div>
                    <div class="document-actions">
                        <button class="btn-small btn-primary" onclick="openDocument(${doc.id})">打开协同编辑</button>
                        <button class="btn-small btn-danger" onclick="deleteDocument(${doc.id})">删除</button>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('加载文档列表失败:', error);
        showError('document-error', '加载文档列表失败: ' + error.message);
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
    if (!confirm('确定要删除这个文档吗？此操作不可恢复。')) {
        return;
    }

    try {
        await api.deleteDocument(documentId);
        await loadDocuments(); // 重新加载文档列表
    } catch (error) {
        console.error('删除文档失败:', error);
        alert('删除文档失败: ' + error.message);
    }
}

// 创建新文档
async function createNewDocument() {
    const title = prompt('请输入文档标题:', '新文档');
    if (!title) return;

    try {
        await api.createDocument(title);
        await loadDocuments(); // 重新加载文档列表
    } catch (error) {
        console.error('创建文档失败:', error);
        alert('创建文档失败: ' + error.message);
    }
}

// 检查登录状态
async function checkAuthStatus() {
    const token = localStorage.getItem('access_token');
    const username = localStorage.getItem('username');

    if (token && username) {
        try {
            // 验证 token 是否有效
            await api.getCurrentUser();
            api.setToken(token, username);
            document.getElementById('current-username').textContent = username;
            showDocumentsSection();
            await loadDocuments();
        } catch (error) {
            // token 无效，清除并显示登录表单
            api.clearAuth();
            showLoginForm();
        }
    } else {
        showLoginForm();
    }
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
    document.getElementById('logout-btn').addEventListener('click', function() {
        if (confirm('确定要退出登录吗？')) {
            api.clearAuth();
            showLoginForm();
        }
    });

    // 创建文档
    document.getElementById('create-document-btn').addEventListener('click', createNewDocument);

    // 检查登录状态
    checkAuthStatus();
});