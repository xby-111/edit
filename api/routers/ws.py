from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.websocket_service import ConnectionManager
from sqlalchemy.orm import Session
from db.session import get_db
from models import Document
from sqlalchemy import func

"""
WebSocket 协作编辑器协议文档

连接URL: ws://<host>/api/v1/ws/documents/{document_id}

支持的消息类型:
1. 内容更新消息:
   {
     "type": "content",
     "content": "文档内容"
   }

2. 光标位置消息:
   {
     "type": "cursor",
     "cursor": {
       "position": <int>  # 光标在文本中的位置
     }
   }

3. 初始化消息 (服务器发送):
   {
     "type": "init",
     "content": "文档初始内容"
   }

4. 用户加入消息 (服务器发送):
   {
     "type": "user_joined",
     "user_id": <int>
   }
"""

router = APIRouter()
manager = ConnectionManager()

@router.websocket("/documents/{document_id}")
async def websocket_document_endpoint(websocket: WebSocket, document_id: int):
    # 用匿名用户ID 0
    user_id = 0
    
    # 获取数据库会话以获取文档内容
    db: Session = next(get_db())
    try:
        # 获取文档内容用于初始化新连接的用户
        document = db.query(Document).filter(Document.id == document_id).first()
        initial_content = document.content if document else ""
        
        await manager.connect(websocket, document_id, user_id, initial_content)
        
        try:
            while True:
                data = await websocket.receive_json()
                print("WS recv:", data, "from user", user_id, "in doc", document_id)

                # 处理内容更新消息
                if data["type"] == "content":
                    # 更新数据库中的文档内容
                    document = db.query(Document).filter(Document.id == document_id).first()
                    if document:
                        document.content = data["content"]
                        document.updated_at = func.now()  # 更新时间
                        db.commit()
                        db.refresh(document)
                    
                    # 广播内容更新给房间内的其他用户
                    broadcast_data = {
                        "type": "content",
                        "content": data["content"]
                    }
                    print("WS broadcast:", broadcast_data, "to room", document_id)
                    await manager.broadcast_to_room(
                        document_id,
                        broadcast_data,
                        user_id,
                        websocket
                    )
            
                elif data["type"] == "cursor":
                    # 广播光标位置更新给房间内的其他用户
                    broadcast_data = {
                        "type": "cursor",
                        "cursor": data["cursor"]
                    }
                    print("WS broadcast:", broadcast_data, "to room", document_id)
                    await manager.broadcast_to_room(
                        document_id,
                        broadcast_data,
                        user_id,
                        websocket
                    )

        except WebSocketDisconnect:
            manager.disconnect(websocket, document_id, user_id)
        except Exception as e:
            print(f"WebSocket error: {e}")
            manager.disconnect(websocket, document_id, user_id)
    finally:
        db.close()