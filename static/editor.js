let ws;
let client_id = Math.random().toString(36).substring(2);
let documentId;

let currentUserId = null; // 用于存储当前用户的ID

function connect(doc_id) {
    // 连接到WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/documents/${doc_id}`;
    console.log("Attempting to connect to:", wsUrl); // 添加连接日志
    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        console.log("WS message raw:", event.data); // 添加接收消息日志
        const msg = JSON.parse(event.data);
        console.log("WS message parsed:", msg); // 添加解析后消息日志
        const editor = document.getElementById("editor");

        if (msg.type === "init") {
            // 初始化内容（从后端获取的当前文档内容）
            editor.value = msg.content;
        }

        if (msg.type === "content") {
            // 更新内容（收到的消息不包含user_id，直接更新）
            editor.value = msg.content;
        }

        if (msg.type === "cursor") {
            // 显示其他用户的光标位置
            // 后端消息格式: {type: "cursor", cursor: {position: number}}
            console.log("Received cursor update:", msg.cursor);
            drawCursor('remote_user', msg.cursor);
        }

        if (msg.type === "user_joined") {
            console.log("新用户加入: ", msg.user_id);
        }
    };

    ws.onopen = () => {
        console.log("WS connected");
    };

    ws.onerror = (error) => {
        console.error("WS error:", error);
    };

    ws.onclose = () => {
        console.log("WS closed");
    };
}

function setupEditor() {
    const editor = document.getElementById("editor");

    editor.addEventListener("input", (e) => {
        // 发送内容更新到服务器
        const content = editor.value;
        console.log("Sending content update:", {type: "content", content: content}); // 添加发送内容日志
        ws.send(JSON.stringify({
            type: "content",
            content: content
        }));
    });

    // 发送光标位置
    editor.addEventListener("keyup", sendCursor);
    editor.addEventListener("mouseup", sendCursor);
    editor.addEventListener("click", sendCursor);
}

// 发送光标位置
function sendCursor() {
    const editor = document.getElementById("editor");
    const selectionStart = editor.selectionStart;

    // 计算光标位置（简化版，实际可能需要更复杂的计算）
    const text = editor.value;
    const textBeforeCursor = text.substring(0, selectionStart);
    const lines = textBeforeCursor.split('\n');
    const currentLine = lines.length - 1;
    const currentColumn = lines[lines.length - 1].length;

    const cursorInfo = {
        position: selectionStart,
        line: currentLine,
        column: currentColumn
    };

    console.log("Sending cursor update:", {type: "cursor", cursor: {position: cursorInfo.position}}); // 添加发送光标日志
    ws.send(JSON.stringify({
        type: "cursor",
        cursor: {
            position: cursorInfo.position
        }
    }));
}

// 绘制其他用户的光标
function drawCursor(user_id, cursor) {
    const editor = document.getElementById("editor");
    const cursorLayer = document.getElementById("cursor-layer");
    
    // 为每个用户创建或更新光标元素 - 使用固定ID避免重复创建
    let userCursor = document.getElementById(`cursor-remote`);
    if (!userCursor) {
        userCursor = document.createElement("div");
        userCursor.id = `cursor-remote`;
        userCursor.className = "remote-cursor";
        userCursor.style.position = "absolute";
        userCursor.style.width = "2px";
        userCursor.style.backgroundColor = getRandomColor();
        userCursor.style.zIndex = "10";
        userCursor.innerHTML = `<div style="position: absolute; top: -18px; left: -10px; background: #000; color: white; padding: 2px 5px; border-radius: 3px; font-size: 12px; white-space: nowrap;">Remote User</div>`;
        cursorLayer.appendChild(userCursor);
    }

    // 这里需要根据行和列信息计算像素位置
    // 简化实现，直接使用position信息
    if (cursor && cursor.position !== undefined) {
        // 获取编辑器的位置信息
        const editorRect = editor.getBoundingClientRect();
        const textBeforeCursor = editor.value.substring(0, cursor.position);
        const lines = textBeforeCursor.split('\n');
        const currentLine = lines.length - 1;
        const currentColumn = lines[lines.length - 1].length;

        // 计算光标的大致像素位置（这是一个简化实现，实际可能需要更精确的计算）
        const lineHeight = 20; // 假设行高为20px
        const charWidth = 8;   // 假设字符宽度为8px
        const top = currentLine * lineHeight;
        const left = currentColumn * charWidth;

        userCursor.style.top = `${top}px`;
        userCursor.style.left = `${left}px`;
        userCursor.style.height = `${lineHeight}px`;
    }
}

// 生成随机颜色
function getRandomColor() {
    const colors = ['#FF5733', '#33FF57', '#3357FF', '#F333FF', '#FF33A1', '#33FFF0'];
    return colors[Math.floor(Math.random() * colors.length)];
}

function init(doc_id) {
    documentId = doc_id;
    // 为当前用户生成一个随机ID，用于区分不同用户
    currentUserId = Date.now(); // 使用时间戳作为用户ID
    connect(doc_id);
    setupEditor();
}