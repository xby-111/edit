from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.crdt import CRDT

router = APIRouter()
docs = {}   # {doc_id: CRDT instance}
sockets = {}  # {doc_id: set(websocket)}

@router.websocket("/ws/{doc_id}/{client_id}")
async def ws_endpoint(websocket: WebSocket, doc_id: int, client_id: str):
    await websocket.accept()

    if doc_id not in docs:
        docs[doc_id] = CRDT()
    if doc_id not in sockets:
        sockets[doc_id] = set()

    sockets[doc_id].add(websocket)

    # 初次同步文本
    await websocket.send_json({
        "type": "init",
        "content": docs[doc_id].to_text()
    })

    try:
        while True:
            op = await websocket.receive_json()

            # 本地应用操作
            if op["type"] == "insert":
                new_op = docs[doc_id].insert(op["index"], op["char"], client_id)
            elif op["type"] == "delete":
                new_op = docs[doc_id].delete(op["index"])
            else:
                continue

            # 广播给所有用户
            for ws in sockets[doc_id]:
                if ws != websocket:
                    await ws.send_json(new_op)

    except WebSocketDisconnect:
        sockets[doc_id].remove(websocket)
