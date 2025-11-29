// static/editor.js - 增强版协同编辑器（支持富文本和自动保存）
let ws;
let documentId = 1;
let localContent = ""; // 本地内容缓存，用于增量同步
let autoSaveTimer = null;
let lastSaveTime = 0;
let apiClient = null;

// WebSocket 重连配置
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_INTERVAL = 3000; // 3 秒
let currentToken = ""; // 保存当前 token 用于重连

// 初始化 API 客户端
function initApiClient() {
    if (!apiClient) {
        // 简单的 API 调用封装
        apiClient = {
            updateDocument: async function(documentId, content) {
                const token = localStorage.getItem('access_token');
                if (!token) {
                    throw new Error('未登录');
                }
                
                const response = await fetch(`/api/v1/documents/${documentId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ content })
                });
                
                if (!response.ok) {
                    throw new Error('保存失败');
                }
                
                return response.json();
            }
        };
    }
}

// 更新连接状态显示
function updateConnectionStatus(status) {
    const indicator = document.getElementById('connection-status');
    if (indicator) {
        switch(status) {
            case 'connected':
                indicator.className = 'status-connected';
                indicator.textContent = '● 已连接';
                break;
            case 'disconnected':
                indicator.className = 'status-disconnected';
                indicator.textContent = '● 已断开';
                break;
            case 'reconnecting':
                indicator.className = 'status-reconnecting';
                indicator.textContent = '● 重连中...';
                break;
        }
    }
    
    // 同时更新编辑器状态提示
    const statusText = document.getElementById('status-text');
    if (statusText) {
        switch(status) {
            case 'connected':
                statusText.textContent = '已连接';
                break;
            case 'disconnected':
                statusText.textContent = '已断开';
                break;
            case 'reconnecting':
                statusText.textContent = '重连中...';
                break;
        }
    }
}

function connect(doc_id, token) {
    documentId = doc_id;
    currentToken = token; // 保存 token 用于重连
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenPart = token ? `?token=${token}` : '';
    ws = new WebSocket(`${protocol}//${location.host}/api/v1/ws/documents/${doc_id}${tokenPart}`);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        // 处理心跳消息
        if (msg.type === "ping") {
            ws.send(JSON.stringify({ type: "pong" }));
            return;
        }
        
        if (msg.type === "init") {
            // 初始化内容 - 支持新旧两种格式
            const content = msg.payload?.html || msg.content || "";
            if (window.quillEditor) {
                window.quillEditor.root.innerHTML = content;
            } else {
                const editor = document.getElementById("editor");
                if (editor) editor.value = content;
            }
            localContent = content;
            
            // 保存服务器时间戳
            localStorage.setItem(`server_time_${doc_id}`, Date.now().toString());
        }
        if (msg.type === "content" || msg.type === "content_update") {
            // 只有当内容来自其他用户时才更新，避免循环更新
            const content = msg.payload?.html || msg.content || "";
            if (msg.user_id !== undefined || msg.user !== undefined) {
                if (window.quillEditor) {
                    window.quillEditor.root.innerHTML = content;
                } else {
                    const editor = document.getElementById("editor");
                    if (editor) editor.value = content;
                }
                localContent = content;
            }
        }
        if (msg.type === "cursor") {
            const position = msg.payload?.index || msg.cursor?.position || 0;
            drawCursor(msg.user_id, msg.username || msg.user || "匿名", position, msg.color);
        }
        if (msg.type === "user_joined" || (msg.type === "presence" && msg.action === "join")) {
            console.log("用户加入:", msg.username || msg.user);
        }
        if (msg.type === "error") {
            console.error("服务器错误:", msg.payload?.message || msg.message);
        }
    };

    ws.onopen = () => {
        console.log("WS 已连接");
        reconnectAttempts = 0; // 重置重连计数
        updateConnectionStatus('connected');
    };
    
    ws.onerror = (e) => {
        console.error("WebSocket 错误:", e);
        updateConnectionStatus('disconnected');
    };
    
    ws.onclose = (event) => {
        console.log("WS 断开", event.code, event.reason);
        updateConnectionStatus('disconnected');
        
        // 尝试自动重连
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            updateConnectionStatus('reconnecting');
            console.log(`尝试重连... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
            setTimeout(() => {
                connect(documentId, currentToken);
            }, RECONNECT_INTERVAL);
        } else {
            console.log("已达到最大重连次数");
            alert('连接已断开，请刷新页面重新连接');
        }
    };
}

function setupEditor() {
    // 自动保存功能
    window.autoSave = function() {
        if (!documentId) return;
        
        const currentContent = window.getCurrentContent ? window.getCurrentContent() : 
            (window.quillEditor ? window.quillEditor.root.innerHTML : 
            (document.getElementById("editor")?.value || ""));
        
        // 内容没有变化则不保存
        if (currentContent === localContent) return;
        
        // 防抖：避免频繁保存
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(async () => {
            try {
                await apiClient.updateDocument(documentId, currentContent);
                localContent = currentContent;
                lastSaveTime = Date.now();
                
                // 显示保存指示器
                if (window.showSaveIndicator) {
                    window.showSaveIndicator();
                }
                
                // 保存本地草稿
                saveLocalDraft(documentId, currentContent);
                
            } catch (error) {
                console.error('自动保存失败:', error);
                // 保存到本地草稿，稍后重试
                saveLocalDraft(documentId, currentContent);
            }
        }, 3000); // 3秒后保存
    };
    
    // 监听编辑器内容变化
    if (window.quillEditor) {
        // Quill 编辑器已经在 HTML 中设置了监听器
    } else {
        const editor = document.getElementById("editor");
        if (editor) {
            let timeout;
            editor.addEventListener("input", () => {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    window.autoSave();
                }, 1000); // 1秒后触发自动保存
            });
        }
    }
    
    // 发送光标位置
    function sendCursor() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        
        let position = 0;
        if (window.quillEditor) {
            position = window.quillEditor.getSelection()?.index || 0;
        } else {
            const editor = document.getElementById("editor");
            if (editor) position = editor.selectionStart || 0;
        }
        
        ws.send(JSON.stringify({
            type: "cursor",
            cursor: { position }
        }));
    }
    
    // 绑定光标事件
    if (window.quillEditor) {
        window.quillEditor.on('selection-change', function(range) {
            if (range) sendCursor();
        });
    } else {
        const editor = document.getElementById("editor");
        if (editor) {
            editor.addEventListener("keyup", sendCursor);
            editor.addEventListener("click", sendCursor);
            editor.addEventListener("selectionchange", () => setTimeout(sendCursor, 50));
        }
    }
}

// 保存本地草稿
function saveLocalDraft(documentId, content) {
    const draftKey = `draft_${documentId}`;
    const draftData = {
        content: content,
        timestamp: Date.now()
    };
    localStorage.setItem(draftKey, JSON.stringify(draftData));
}

// 光标绘制功能
function drawCursor(user_id, username, position, color = "#FF5733") {
    let cursor = document.getElementById(`cursor-${user_id}`);
    if (!cursor) {
        cursor = document.createElement("div");
        cursor.id = `cursor-${user_id}`;
        cursor.className = "remote-cursor";
        cursor.style.position = "absolute";
        cursor.style.width = "2px";
        cursor.style.backgroundColor = color;
        cursor.style.zIndex = "10";
        cursor.style.pointerEvents = "none";
        cursor.innerHTML = `<div class="cursor-label">${username}</div>`;
        document.getElementById("cursor-layer").appendChild(cursor);
    }

    // 对于富文本编辑器，使用简化的位置计算
    if (window.quillEditor) {
        const bounds = window.quillEditor.getBounds(position);
        cursor.style.top = `${bounds.top + 10}px`; // +10 是 padding
        cursor.style.left = `${bounds.left + 15}px`; // +15 是左边距
        cursor.style.height = `${bounds.height}px`;
    } else {
        // 原有的 textarea 光标位置计算
        const editor = document.getElementById("editor");
        if (editor) {
            const textBefore = editor.value.substring(0, position);
            const lines = textBefore.split("\n");
            const lineNum = lines.length - 1;
            const colNum = lines[lines.length - 1].length;

            const style = getComputedStyle(editor);
            const lineHeight = parseInt(style.lineHeight || style.fontSize) + 2;
            const charWidth = measureTextWidth("测", editor);

            cursor.style.top = (lineNum * lineHeight + 10) + "px";
            cursor.style.left = (colNum * charWidth + 15) + "px";
            cursor.style.height = lineHeight + "px";
        }
    }
}

// 精确测量字符宽度
function measureTextWidth(text, element) {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const style = getComputedStyle(element);
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return ctx.measureText(text).width;
}

// 导出初始化函数
window.initEditor = function(doc_id, token = "") {
    documentId = doc_id;
    
    // 如果没有传入 token，尝试从 localStorage 获取
    if (!token) {
        token = localStorage.getItem('access_token') || '';
    }
    
    // 初始化 API 客户端
    initApiClient();
    
    // 连接 WebSocket
    connect(doc_id, token);
    
    // 设置编辑器
    setupEditor();
};

// 保持向后兼容的 init 函数
function init(doc_id, token = "") {
    window.initEditor(doc_id, token);
}
