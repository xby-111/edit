const ws = new WebSocket("ws://" + location.host + "/ws");
const editor = document.getElementById("editor");
const cursorLayer = document.getElementById("cursor-layer");

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    // 同步内容
    if (msg.type === "update") {
        editor.innerText = msg.content;
    }

    // 同步光标
    if (msg.type === "cursor") {
        drawCursor(msg.user_id, msg.rect);
    }
};

// 发送文本内容
editor.addEventListener("input", () => {
    ws.send(JSON.stringify({
        type: "edit",
        content: editor.innerText
    }));
});

// 发送光标位置
editor.addEventListener("keyup", sendCursor);
editor.addEventListener("mouseup", sendCursor);

function sendCursor() {
    const rect = getCaretRect();

    ws.send(JSON.stringify({
        type: "cursor",
        rect: rect
    }));
}

// 获取光标像素坐标（精准）
function getCaretRect() {
    const selection = window.getSelection();
    if (!selection.rangeCount) return null;

    const range = selection.getRangeAt(0).cloneRange();
    range.collapse(true);

    const rect = range.getBoundingClientRect();
    const editorRect = editor.getBoundingClientRect();

    return {
        x: rect.x - editorRect.x,
        y: rect.y - editorRect.y,
        height: rect.height
    };
}

// 绘制光标
function drawCursor(user_id, rect) {
    if (!rect) return;

    let cursor = document.getElementById("cursor-" + user_id);
    if (!cursor) {
        cursor = document.createElement("div");
        cursor.id = "cursor-" + user_id;
        cursor.className = "cursor";
        cursor.style.position = "absolute";
        cursor.style.width = "2px";
        cursor.style.background = "red";
        cursorLayer.appendChild(cursor);
    }

    cursor.style.left = rect.x + "px";
    cursor.style.top = rect.y + "px";
    cursor.style.height = rect.height + "px";
}
