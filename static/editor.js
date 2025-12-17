// static/editor.js - 增强版协同编辑器（支持富文本、CRDT 增量同步和自动保存）
let ws;
let documentId = 1;
let localContent = ""; // 本地内容缓存，用于增量同步
let autoSaveTimer = null;
let lastSaveTime = 0;

// WebSocket 重连配置
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_INTERVAL = 1000; // 基础重连间隔 1 秒
const MAX_RECONNECT_INTERVAL = 30000; // 最大重连间隔 30 秒
let currentToken = ""; // 保存当前 token 用于重连

// 内容发送防抖定时器
let contentSendTimer = null;
const CONTENT_SEND_DEBOUNCE = 150; // 150ms 防抖，平衡实时性和稳定性

// 标志：是否正在接收远程更新，防止循环
let isReceivingRemoteUpdate = false;

// CRDT 状态
let crdtVersion = 0; // 当前 CRDT 版本
let pendingOps = []; // 待确认的操作
let useCRDT = false; // 暂时禁用 CRDT 模式，使用全量同步确保实时同步正常工作

// 客户端 ID（用于 CRDT 操作标识）
const clientId = 'client_' + Math.random().toString(36).substr(2, 9);
// 本地用户的数字 user_id（从服务器获取，用于过滤自己的消息）
let localUserId = null;
const AUTH_FAILURE_CODE = 1008;

function clearStoredAuth() {
    if (window.api && typeof window.api.clearAuth === 'function') {
        window.api.clearAuth();
    } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        localStorage.removeItem('user_id');
    }
}

function redirectToLogin() {
    const redirectDelay = 1200;
    setTimeout(() => {
        window.location.href = '/';
    }, redirectDelay);
}

/**
 * 将 Quill Delta 转换为 CRDT 操作序列
 * @param {Object} delta - Quill delta 对象
 * @param {number} baseIndex - 起始索引
 * @returns {Array} CRDT 操作数组
 */
function deltaToOps(delta, baseIndex = 0) {
    const ops = [];
    let index = baseIndex;
    const timestamp = Date.now();
    
    if (!delta || !delta.ops) return ops;
    
    for (const op of delta.ops) {
        if (op.retain !== undefined) {
            // retain：保持位置不变，移动索引
            index += op.retain;
        } else if (op.insert !== undefined) {
            // insert：插入文本或嵌入对象
            const text = typeof op.insert === 'string' ? op.insert : '\n';
            for (let i = 0; i < text.length; i++) {
                ops.push({
                    type: 'insert',
                    position: index + i,
                    char: text[i],
                    client_id: clientId,
                    timestamp: timestamp + i * 0.001, // 确保顺序
                    op_id: `${clientId}:${timestamp}:${index + i}`
                });
            }
            index += text.length;
        } else if (op.delete !== undefined) {
            // delete：删除字符
            for (let i = 0; i < op.delete; i++) {
                ops.push({
                    type: 'delete',
                    position: index, // 删除时位置不变（后面的字符会前移）
                    client_id: clientId,
                    timestamp: timestamp + i * 0.001,
                    op_id: `${clientId}:${timestamp}:del:${i}`
                });
            }
            // 删除操作不移动 index（因为字符被删除了）
        }
    }
    
    return ops;
}

/**
 * 将 CRDT 操作应用到 Quill 编辑器
 * @param {Array} ops - CRDT 操作数组
 */
function applyOpsToEditor(ops) {
    if (!window.quillEditor || !ops || ops.length === 0) return;
    
    // 按位置和时间戳排序操作
    const sortedOps = [...ops].sort((a, b) => {
        if (a.position !== b.position) return a.position - b.position;
        return a.timestamp - b.timestamp;
    });
    
    // 转换为 Quill delta
    const delta = { ops: [] };
    let currentPos = 0;
    
    for (const op of sortedOps) {
        if (op.type === 'insert') {
            if (op.position > currentPos) {
                delta.ops.push({ retain: op.position - currentPos });
                currentPos = op.position;
            }
            delta.ops.push({ insert: op.char });
            currentPos += 1;
        } else if (op.type === 'delete') {
            if (op.position > currentPos) {
                delta.ops.push({ retain: op.position - currentPos });
                currentPos = op.position;
            }
            delta.ops.push({ delete: 1 });
        }
    }
    
    // 应用 delta
    if (delta.ops.length > 0) {
        window.quillEditor.updateContents(delta, 'silent');
    }
}

/**
 * 智能应用远程内容更新
 * 使用 diff 算法找出差异，只更新变化的部分，保留用户正在编辑的位置
 */
function applyRemoteContent(remoteHtml) {
    if (!window.quillEditor) return;
    
    // 获取当前状态
    const selection = window.quillEditor.getSelection();
    const currentText = window.quillEditor.getText();
    
    // 将远程 HTML 转换为 Delta
    const remoteDelta = window.quillEditor.clipboard.convert(remoteHtml);
    
    // 获取远程内容的纯文本（用于比较）
    let remoteText = '';
    remoteDelta.ops.forEach(op => {
        if (typeof op.insert === 'string') {
            remoteText += op.insert;
        } else if (op.insert) {
            remoteText += '\n'; // 嵌入对象算一个字符
        }
    });
    
    // 如果文本完全相同，可能只是格式变化，直接应用
    if (currentText === remoteText) {
        window.quillEditor.setContents(remoteDelta, 'silent');
        if (selection) {
            window.quillEditor.setSelection(selection.index, selection.length, 'silent');
        }
        return;
    }
    
    // 找出差异位置
    const diff = findTextDiff(currentText, remoteText);
    
    if (diff) {
        // 计算光标偏移
        let newCursorPos = selection ? selection.index : 0;
        
        // 如果修改发生在光标之前，需要调整光标位置
        if (selection && diff.start < selection.index) {
            const lengthDiff = diff.newText.length - diff.oldText.length;
            newCursorPos = Math.max(0, selection.index + lengthDiff);
        }
        
        // 应用差异：删除旧内容，插入新内容
        const delta = {
            ops: []
        };
        
        if (diff.start > 0) {
            delta.ops.push({ retain: diff.start });
        }
        if (diff.oldText.length > 0) {
            delta.ops.push({ delete: diff.oldText.length });
        }
        if (diff.newText.length > 0) {
            delta.ops.push({ insert: diff.newText });
        }
        
        window.quillEditor.updateContents(delta, 'silent');
        
        // 恢复光标位置
        if (selection) {
            setTimeout(() => {
                const maxPos = window.quillEditor.getLength() - 1;
                window.quillEditor.setSelection(
                    Math.min(newCursorPos, maxPos), 
                    selection.length, 
                    'silent'
                );
            }, 0);
        }
    } else {
        // 差异太大，回退到全量更新
        window.quillEditor.setContents(remoteDelta, 'silent');
        if (selection) {
            setTimeout(() => {
                const maxPos = window.quillEditor.getLength() - 1;
                window.quillEditor.setSelection(
                    Math.min(selection.index, maxPos), 
                    selection.length, 
                    'silent'
                );
            }, 0);
        }
    }
}

/**
 * 找出两个字符串之间的差异
 * 返回 { start, oldText, newText } 或 null（如果差异太复杂）
 */
function findTextDiff(oldText, newText) {
    // 找到第一个不同的位置
    let start = 0;
    const minLen = Math.min(oldText.length, newText.length);
    
    while (start < minLen && oldText[start] === newText[start]) {
        start++;
    }
    
    // 从末尾找到最后一个不同的位置
    let oldEnd = oldText.length;
    let newEnd = newText.length;
    
    while (oldEnd > start && newEnd > start && 
           oldText[oldEnd - 1] === newText[newEnd - 1]) {
        oldEnd--;
        newEnd--;
    }
    
    // 提取差异部分
    const oldPart = oldText.substring(start, oldEnd);
    const newPart = newText.substring(start, newEnd);
    
    // 如果差异太大（超过一半内容），返回 null 使用全量更新
    if (oldPart.length > oldText.length / 2 && newPart.length > newText.length / 2) {
        return null;
    }
    
    return {
        start: start,
        oldText: oldPart,
        newText: newPart
    };
}

/**
 * 计算指数退避重连间隔
 * @param {number} attempt - 当前重连尝试次数
 * @returns {number} 重连间隔（毫秒）
 */
function getReconnectInterval(attempt) {
    // 指数退避 + 随机抖动
    const interval = Math.min(
        BASE_RECONNECT_INTERVAL * Math.pow(2, attempt - 1),
        MAX_RECONNECT_INTERVAL
    );
    // 添加 0-1000ms 的随机抖动，避免雷群效应
    return interval + Math.random() * 1000;
}

// 通过 WebSocket 发送内容更新（支持 CRDT 增量和全量回退）
function sendContentUpdate(delta = null) {
    // 如果正在接收远程更新，不发送，防止循环
    if (isReceivingRemoteUpdate) {
        console.log('正在接收远程更新，跳过发送');
        return;
    }
    
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    
    // 防抖处理
    clearTimeout(contentSendTimer);
    contentSendTimer = setTimeout(() => {
        // 再次检查，防止在防抖期间状态改变
        if (isReceivingRemoteUpdate) {
            console.log('防抖期间收到远程更新，跳过发送');
            return;
        }
        
        // 如果有 delta 且启用 CRDT，发送增量操作
        if (useCRDT && delta && delta.ops && delta.ops.length > 0) {
            const ops = deltaToOps(delta);
            if (ops.length > 0) {
                pendingOps.push(...ops);
                ws.send(JSON.stringify({
                    type: "crdt_ops",
                    ops: ops,
                    version: crdtVersion
                }));
                console.log('CRDT 增量操作已发送:', ops.length, '个操作');
                return;
            }
        }
        
        // 回退到全量同步
        const currentContent = window.getCurrentContent ? window.getCurrentContent() : 
            (window.quillEditor ? window.quillEditor.root.innerHTML : 
            (document.getElementById("editor")?.value || ""));
        
        // 内容没有变化则不发送
        if (currentContent === localContent) return;
        
        // 更新本地内容缓存
        localContent = currentContent;
        
        // 通过 WebSocket 发送全量内容更新
        ws.send(JSON.stringify({
            type: "content_update",
            payload: { html: currentContent }
        }));
        
        console.log('WebSocket 全量内容更新已发送');
    }, CONTENT_SEND_DEBOUNCE);
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
    
    // 从 localStorage 获取当前用户的 user_id
    // 强制转换为数字，防止类型不匹配导致的比较问题
    const storedUserId = localStorage.getItem('user_id');
    localUserId = storedUserId ? Number(storedUserId) : null;
    // 如果转换失败（NaN），设置为 null
    if (localUserId !== null && isNaN(localUserId)) {
        localUserId = null;
    }
    console.log('当前本地用户 ID:', localUserId, typeof localUserId);
    
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenPart = token ? `?token=${token}` : '';
    ws = new WebSocket(`${protocol}//${location.host}/api/v1/ws/documents/${doc_id}${tokenPart}`);

    ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        console.log('收到WebSocket消息:', msg.type, msg);
        
        // 处理心跳消息
        if (msg.type === "ping") {
            ws.send(JSON.stringify({ type: "pong" }));
            return;
        }
        
        // 处理 CRDT 操作确认
        if (msg.type === "crdt_ack") {
            crdtVersion = msg.version || crdtVersion;
            // 清理已确认的操作
            const appliedCount = msg.applied || 0;
            pendingOps.splice(0, appliedCount);
            console.log('CRDT 确认，版本:', crdtVersion);
            return;
        }
        
        // 处理远程 CRDT 操作
        if (msg.type === "crdt_ops") {
            const ops = msg.ops || [];
            // 确保用数字类型进行比较，过滤自己发送的操作
            const msgUserId = Number(msg.user_id);
            if (ops.length > 0 && msgUserId !== localUserId) {
                isReceivingRemoteUpdate = true;
                applyOpsToEditor(ops);
                crdtVersion = msg.version || crdtVersion;
                // 更新本地内容缓存
                if (window.quillEditor) {
                    localContent = window.quillEditor.root.innerHTML;
                }
                setTimeout(() => {
                    isReceivingRemoteUpdate = false;
                }, 50);
                console.log('应用远程 CRDT 操作:', ops.length, '个');
            }
            return;
        }
        
        if (msg.type === "init") {
            // 初始化内容 - 支持新旧两种格式
            const serverContent = msg.payload?.html || msg.content || "";
            const serverTimestamp = Date.now();
            
            // 设置标志：正在接收远程更新
            isReceivingRemoteUpdate = true;
            
            // 🎯 Smart Draft Recovery Logic
            const draftKey = `draft_${doc_id}`;
            const draftDataStr = localStorage.getItem(draftKey);
            
            let shouldPromptUser = false;
            let draftContent = "";
            let draftTimestamp = 0;
            
            if (draftDataStr) {
                try {
                    const draftData = JSON.parse(draftDataStr);
                    draftContent = draftData.content || "";
                    draftTimestamp = draftData.timestamp || 0;
                    
                    // 计算草稿年龄（毫秒）
                    const draftAge = Date.now() - draftTimestamp;
                    const ONE_HOUR = 60 * 60 * 1000;
                    
                    // 🧹 Silent Cleanup Scenarios (The "Happy Path")
                    if (draftAge > ONE_HOUR) {
                        // Scenario 1: 草稿过期
                        console.log('🧹 草稿已过期（>1小时），静默清理');
                        localStorage.removeItem(draftKey);
                    } else if (!draftContent || draftContent.trim() === '' || draftContent === '<p><br></p>') {
                        // Scenario 2: 草稿为空
                        console.log('🧹 草稿为空，静默清理');
                        localStorage.removeItem(draftKey);
                    } else if (draftContent === serverContent) {
                        // Scenario 3: 草稿与服务器内容完全一致（最常见的场景）
                        console.log('✅ 本地草稿与服务器内容一致，静默清理冗余备份');
                        localStorage.removeItem(draftKey);
                    } else {
                        // ⚠️ Conflict Detected: 草稿与服务器内容不同
                        shouldPromptUser = true;
                    }
                } catch (e) {
                    console.error('⚠️ 解析本地草稿失败:', e);
                    // 错误时保留草稿，不删除（避免数据丢失）
                }
            }
            
            // 🚨 Conflict Handling (The "Rescue Path")
            if (shouldPromptUser) {
                const confirmMessage = `⚠️ 检测到本地存在未同步的草稿\n` +
                    `保存时间: ${new Date(draftTimestamp).toLocaleString()}\n` +
                    `草稿大小: ${Math.round(draftContent.length / 1024)}KB\n` +
                    `服务器内容: ${Math.round(serverContent.length / 1024)}KB\n\n` +
                    `是否使用本地草稿？`;
                
                let useDraft = false;
                if (typeof Toast !== 'undefined' && Toast.confirm) {
                    useDraft = await Toast.confirm(confirmMessage, { 
                        confirmText: '✅ 使用草稿', 
                        cancelText: '❌ 使用服务器内容' 
                    });
                } else {
                    useDraft = confirm(confirmMessage);
                }
                
                if (useDraft) {
                    // 用户选择草稿：应用 → 同步 → 删除
                    console.log('📝 用户选择使用本地草稿，开始恢复流程...');
                    
                    try {
                        // Step 1: 应用草稿到编辑器
                        if (window.quillEditor) {
                            window.quillEditor.setContents(
                                window.quillEditor.clipboard.convert(draftContent), 
                                'silent'
                            );
                        } else {
                            const editor = document.getElementById("editor");
                            if (editor) editor.value = draftContent;
                        }
                        localContent = draftContent;
                        console.log('✅ 步骤1: 草稿已应用到编辑器');
                        
                        // Step 2: 立即同步到服务器
                        isReceivingRemoteUpdate = false;
                        
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: "content_update",
                                payload: { html: draftContent }
                            }));
                            console.log('✅ 步骤2: 草稿内容已同步到服务器');
                            
                            // Step 3: 同步成功后才删除草稿
                            setTimeout(() => {
                                localStorage.removeItem(draftKey);
                                console.log('✅ 步骤3: 草稿已安全删除');
                            }, 500);
                        } else {
                            console.warn('⚠️ WebSocket 未连接，草稿保留，将在下次连接时重试');
                        }
                        
                        setTimeout(() => {
                            isReceivingRemoteUpdate = false;
                        }, 200);
                        
                        // 早期返回，跳过后面的服务器内容加载
                        return;
                    } catch (err) {
                        console.error('❌ 恢复草稿失败:', err);
                        // 失败时不删除草稿，保留数据
                    }
                } else {
                    // 用户选择服务器内容：清理草稿
                    console.log('🗑️ 用户选择服务器内容，清理草稿');
                    localStorage.removeItem(draftKey);
                }
            }
            
            // 📥 Load Server Content (Default Path)
            if (window.quillEditor) {
                window.quillEditor.setContents(
                    window.quillEditor.clipboard.convert(serverContent), 
                    'silent'
                );
            } else {
                const editor = document.getElementById("editor");
                if (editor) editor.value = serverContent;
            }
            localContent = serverContent;
            
            // 重置标志
            setTimeout(() => {
                isReceivingRemoteUpdate = false;
            }, 100);
            
            // 保存服务器时间戳
            localStorage.setItem(`server_time_${doc_id}`, serverTimestamp.toString());
        }
        if (msg.type === "content" || msg.type === "content_update") {
            // 过滤自己发送的内容更新，防止回环
            // 确保用数字类型进行比较
            const msgUserId = Number(msg.user_id);
            if (msgUserId === localUserId) {
                console.log('跳过自己发送的内容更新');
                return;
            }
            
            // 获取收到的内容
            const remoteContent = msg.payload?.html || msg.content || "";
            
            // 获取当前本地内容
            const currentLocalContent = window.quillEditor ? 
                window.quillEditor.root.innerHTML : 
                (document.getElementById("editor")?.value || "");
            
            // 如果内容完全相同，跳过
            if (remoteContent === currentLocalContent) {
                console.log('收到的内容与本地相同，跳过更新');
                return;
            }
            
            // 设置标志：正在接收远程更新
            isReceivingRemoteUpdate = true;
            
            if (window.quillEditor) {
                // 使用增量更新而不是全量替换
                applyRemoteContent(remoteContent);
            } else {
                const editor = document.getElementById("editor");
                if (editor) {
                    const selectionStart = editor.selectionStart;
                    const selectionEnd = editor.selectionEnd;
                    editor.value = remoteContent;
                    editor.setSelectionRange(selectionStart, selectionEnd);
                }
            }
            
            localContent = remoteContent;
            console.log('已更新远程内容');
            
            // 重置标志（延迟重置，给更多缓冲时间避免立即发送造成冲突）
            setTimeout(() => {
                isReceivingRemoteUpdate = false;
            }, 200);
        }
        if (msg.type === "cursor") {
            const cursorData = msg.cursor || { position: msg.payload?.index || 0 };
            drawCursor(msg.user_id, msg.username || msg.user || "匿名", cursorData, msg.color);
        }
        if (msg.type === "user_joined" || (msg.type === "presence" && msg.action === "join")) {
            console.log("用户加入:", msg.username || msg.user);
            // 刷新在线用户列表
            if (typeof updateOnlineUsersList === 'function') {
                updateOnlineUsersList(msg.online_users_info || []);
            }
        }
        if (msg.type === "presence" && msg.action === "init") {
            // 初始化在线用户列表
            console.log("在线用户:", msg.online_users_info || msg.online_users);
            if (typeof updateOnlineUsersList === 'function') {
                updateOnlineUsersList(msg.online_users_info || []);
            }
        }
        if (msg.type === "presence" && msg.action === "leave") {
            console.log("用户离开:", msg.username || msg.user_id);
            // 刷新在线用户列表
            if (typeof updateOnlineUsersList === 'function') {
                updateOnlineUsersList(msg.online_users_info || []);
            }
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
        
        // 连接断开时保存本地草稿作为备份
        if (documentId) {
            const currentContent = window.quillEditor ? 
                window.quillEditor.root.innerHTML : 
                (document.getElementById("editor")?.value || "");
            if (currentContent) {
                saveLocalDraft(documentId, currentContent);
                console.log('连接断开，已保存本地草稿');
            }
        }
        
        if (event.code === AUTH_FAILURE_CODE) {
            console.warn('WebSocket 鉴权失败，停止重连');
            clearStoredAuth();
            if (typeof Toast !== 'undefined') {
                Toast.error('登录状态已过期，请重新登录');
            }
            redirectToLogin();
            return;
        }
        
        // 尝试自动重连（指数退避）
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            updateConnectionStatus('reconnecting');
            const interval = getReconnectInterval(reconnectAttempts);
            console.log(`尝试重连... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})，等待 ${Math.round(interval/1000)}s`);
            setTimeout(() => {
                connect(documentId, currentToken);
            }, interval);
        } else {
            console.log("已达到最大重连次数");
            if (typeof Toast !== 'undefined') {
                Toast.error('连接已断开，请刷新页面重新连接', { duration: 0 }); // 0 表示不自动关闭
            }
        }
    };
}

function setupEditor() {
    // 🔥 修复 Issue A: 自动保存功能 - 始终保存到 localStorage 作为热备份
    // 这是针对服务器崩溃、网络中断、浏览器崩溃的最后一道防线
    window.autoSave = function() {
        if (!documentId) return;
        
        const currentContent = window.getCurrentContent ? window.getCurrentContent() : 
            (window.quillEditor ? window.quillEditor.root.innerHTML : 
            (document.getElementById("editor")?.value || ""));
        
        // 内容没有变化则不保存
        if (currentContent === localContent) return;
        
        // 防抖：避免频繁保存本地草稿 (降低到 500ms 以提高备份频率)
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveLocalDraft(documentId, currentContent);
            lastSaveTime = Date.now();
            
            // 根据连接状态提供不同的日志信息
            if (ws && ws.readyState === WebSocket.OPEN) {
                console.log('💾 热备份已保存 (在线状态)');
            } else {
                console.log('💾 离线备份已保存 (断线状态)');
            }
        }, 500); // 从 1000ms 降低到 500ms
    };
    
    // 页面关闭或刷新前保存草稿（仅当连接断开时）
    let beforeUnloadSaved = false; // 防止重复保存标志
    window.addEventListener('beforeunload', function() {
        // 🔥 修复: 避免与 onclose 重复保存
        if (beforeUnloadSaved) return;
        
        if (ws && ws.readyState !== WebSocket.OPEN && documentId) {
            const currentContent = window.quillEditor ? 
                window.quillEditor.root.innerHTML : 
                (document.getElementById("editor")?.value || "");
            if (currentContent && currentContent !== localContent) {
                saveLocalDraft(documentId, currentContent);
                beforeUnloadSaved = true;
            }
        }
    });
    
    // 监听编辑器内容变化
    if (window.quillEditor) {
        // Quill 编辑器 - 监听 text-change 事件，传递 delta 以支持 CRDT
        window.quillEditor.on('text-change', function(delta, oldDelta, source) {
            // 只处理用户输入，忽略程序化更改
            if (source === 'user') {
                sendContentUpdate(delta); // 传递 delta 用于 CRDT 转换
                // 仅在断开连接时保存草稿
                window.autoSave();
            }
        });
    } else {
        const editor = document.getElementById("editor");
        if (editor) {
            editor.addEventListener("input", () => {
                sendContentUpdate();
                window.autoSave();
            });
        }
    }
    
    // 发送光标位置
    function sendCursor() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        
        let position = 0;
        let length = 0;
        
        if (window.quillEditor) {
            const selection = window.quillEditor.getSelection();
            if (selection) {
                position = selection.index;
                length = selection.length;
            }
        } else {
            const editor = document.getElementById("editor");
            if (editor) {
                position = editor.selectionStart || 0;
                length = (editor.selectionEnd || 0) - position;
            }
        }
        
        ws.send(JSON.stringify({
            type: "cursor",
            cursor: { position, length }
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
    // 🔥 关键修复: 拒绝保存空内容或无效内容
    if (!content || content.trim() === '' || content === '<p><br></p>') {
        console.warn('⚠️ 拒绝保存空草稿，跳过');
        return;
    }
    
    const draftKey = `draft_${documentId}`;
    const draftData = {
        content: content,
        timestamp: Date.now()
    };
    localStorage.setItem(draftKey, JSON.stringify(draftData));
    console.log(`💾 已保存草稿 (${Math.round(content.length / 1024)}KB)`);
}

// 光标绘制功能
function drawCursor(user_id, username, cursorData, color = "#FF5733") {
    // cursorData 可能是数字（位置）或对象 {position, length}
    const position = typeof cursorData === 'object' ? (cursorData.position || 0) : (cursorData || 0);
    const length = typeof cursorData === 'object' ? (cursorData.length || 0) : 0;
    
    // 跳过自己的光标
    if (user_id === localUserId) return;
    
    let cursor = document.getElementById(`cursor-${user_id}`);
    let selection = document.getElementById(`selection-${user_id}`);
    
    if (!cursor) {
        cursor = document.createElement("div");
        cursor.id = `cursor-${user_id}`;
        cursor.className = "remote-cursor";
        
        // 🔒 安全修复: 使用 textContent 防止 XSS 攻击
        const label = document.createElement("div");
        label.className = "cursor-label";
        label.style.backgroundColor = color;
        label.textContent = username; // 安全地设置文本，不解析 HTML
        cursor.appendChild(label);
        
        const cursorLayer = document.getElementById("cursor-layer");
        if (cursorLayer) cursorLayer.appendChild(cursor);
    }
    
    // 选区高亮
    if (!selection) {
        selection = document.createElement("div");
        selection.id = `selection-${user_id}`;
        selection.className = "remote-selection";
        selection.style.backgroundColor = color;
        selection.style.opacity = "0.3";
        selection.style.position = "absolute";
        selection.style.pointerEvents = "none";
        selection.style.zIndex = "5";
        
        const cursorLayer = document.getElementById("cursor-layer");
        if (cursorLayer) cursorLayer.appendChild(selection);
    }

    // 对于 Quill 编辑器，使用 getBounds 获取精确位置
    if (window.quillEditor) {
        try {
            const editorContainer = document.querySelector('.ql-editor');
            if (!editorContainer) return;
            
            const containerRect = editorContainer.getBoundingClientRect();
            const bounds = window.quillEditor.getBounds(position, length || 1);
            
            // 设置光标位置（相对于编辑器容器）
            cursor.style.position = "absolute";
            cursor.style.top = `${bounds.top}px`;
            cursor.style.left = `${bounds.left}px`;
            cursor.style.height = `${bounds.height}px`;
            cursor.style.width = "2px";
            cursor.style.backgroundColor = color;
            cursor.style.zIndex = "10";
            cursor.style.pointerEvents = "none";
            
            // 如果有选区，显示选区高亮
            if (length > 0) {
                selection.style.display = "block";
                selection.style.top = `${bounds.top}px`;
                selection.style.left = `${bounds.left}px`;
                selection.style.width = `${bounds.width}px`;
                selection.style.height = `${bounds.height}px`;
            } else {
                selection.style.display = "none";
            }
        } catch (e) {
            console.warn('获取光标位置失败:', e);
        }
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
    
    // 连接 WebSocket
    connect(doc_id, token);
    
    // 设置编辑器
    setupEditor();
};

// 保持向后兼容的 init 函数
function init(doc_id, token = "") {
    window.initEditor(doc_id, token);
}
