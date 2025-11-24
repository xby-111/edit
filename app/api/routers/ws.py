from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_service import ConnectionManager
from app.db.session import get_db
from datetime import datetime

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
     },
     "user_id": <int>  # 发送光标的用户ID
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
    # 生成唯一的用户ID
    import time
    user_id = int(time.time() * 1000000) % 1000000  # 使用时间戳的微秒部分生成唯一ID

    # 获取数据库连接以获取文档内容
    db = next(get_db())
    try:
        # 获取文档内容用于初始化新连接的用户 - 使用 py-opengauss 的 query 方法
        rows = db.query(f"SELECT content FROM documents WHERE id = {document_id} LIMIT 1")
        
        initial_content = rows[0][0] if rows else ""
        
        await manager.connect(websocket, document_id, user_id, initial_content)
        
        try:
            while True:
                data = await websocket.receive_json()
                print("WS recv:", data, "from user", user_id, "in doc", document_id)

                # 处理内容更新消息
                if data["type"] == "content":
                    # 更新数据库中的文档内容 - 使用 websocket_service 处理
                    await manager.handle_message(document_id, user_id, data, websocket, db)
                    
                    
            
                elif data["type"] == "cursor":
                    # 广播光标位置更新给房间内的其他用户，包含用户ID - 使用 websocket_service 处理
                    await manager.handle_message(document_id, user_id, data, websocket, db)

        except WebSocketDisconnect:
            manager.disconnect(websocket, document_id, user_id)
        except Exception as e:
            print(f"WebSocket error: {e}")
            manager.disconnect(websocket, document_id, user_id)
    except Exception as e:
        print(f"WebSocket setup error: {e}")
    finally:
        # 注意：对于全局连接，可能不需要关闭，但这里仅保持逻辑一致性
        pass