// static/editor.js   ←←← 直接全替换成这个！！！
let ws;
let documentId = 1;
let localContent = ""; // 本地内容缓存，用于增量同步

function connect(doc_id, token) {
    documentId = doc_id;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenPart = token ? `?token=${token}` : '';
    ws = new WebSocket(`${protocol}//${location.host}/api/v1/ws/documents/${doc_id}${tokenPart}`);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const editor = document.getElementById("editor");
        const cursorLayer = document.getElementById("cursor-layer") || document.body;

        if (msg.type === "init") {
            editor.value = msg.content;
            localContent = msg.content;
        }
        if (msg.type === "content") {
            // 只有当内容来自其他用户时才更新，避免循环更新
            if (msg.user_id !== undefined) {
                editor.value = msg.content;
                localContent = msg.content;
            }
        }
        if (msg.type === "cursor") {
            drawCursor(msg.user_id, msg.username || "匿名", msg.cursor.position, msg.color);
        }
        if (msg.type === "user_joined") {
            console.log("用户加入:", msg.username);
            // 可选：这里加一个在线用户列表
        }
    };

    // 下面这些函数保持不变，只改了 drawCursor
    ws.onopen = () => console.log("WS 已连接");
    ws.onerror = (e) => console.error(e);
    ws.onclose = () => console.log("WS 断开");
}

function setupEditor() {
    const editor = document.getElementById("editor");

    // 发送内容变化（使用增量同步策略）
    let timeout;
    editor.addEventListener("input", () => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            const newContent = editor.value;
            // 只有当内容发生变化时才发送
            if (newContent !== localContent) {
                ws.send(JSON.stringify({
                    type: "content",
                    content: newContent
                }));
                localContent = newContent;
            }
        }, 100); // 简单防抖
    });

    // 发送光标位置
    editor.addEventListener("keyup", sendCursor);
    editor.addEventListener("click", sendCursor);
    editor.addEventListener("selectionchange", () => setTimeout(sendCursor, 50));

    function sendCursor() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "cursor",
                cursor: { position: editor.selectionStart }
            }));
        }
    }
}

// 完美光标绘制（支持换行、中文、用户名标签）
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
        cursor.innerHTML = `<div style="position:absolute; top:-20px; left:-2px; background:${color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px; white-space:nowrap;">${username}</div>`;
        document.getElementById("cursor-layer").appendChild(cursor);
    }

    // 精确计算光标位置（支持中文、换行、任意字体）
    const editor = document.getElementById("editor");
    const textBefore = editor.value.substring(0, position);
    const lines = textBefore.split("\n");
    const lineNum = lines.length - 1;
    const colNum = lines[lines.length - 1].length;

    const style = getComputedStyle(editor);
    const lineHeight = parseInt(style.lineHeight || style.fontSize) + 2;
    const charWidth = measureTextWidth("测", editor); // 用中文最宽的测

    cursor.style.top = (lineNum * lineHeight + 10) + "px"; // +10 是 padding
    cursor.style.left = (colNum * charWidth + 15) + "px"; // +15 是左边距
    cursor.style.height = lineHeight + "px";
}

// 精确测量字符宽度（解决中英文混排问题）
function measureTextWidth(text, element) {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const style = getComputedStyle(element);
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return ctx.measureText(text).width;
}

// 初始化
function init(doc_id, token = "") {
    documentId = doc_id;
    connect(doc_id, token);
    setupEditor();
}
