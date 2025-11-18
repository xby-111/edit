from typing import List, Dict
from fastapi import WebSocket
from app.crdt import CRDT


class ConnectionManager:
    def __init__(self):
        # Store connections by document ID
        self.active_connections: Dict[int, List[Dict]] = {}
        # Store CRDT instances for each document
        self.document_crtds: Dict[int, CRDT] = {}

    def get_crdt(self, document_id: int) -> CRDT:
        if document_id not in self.document_crtds:
            self.document_crtds[document_id] = CRDT()
        return self.document_crtds[document_id]

    async def connect(self, websocket: WebSocket, document_id: int, user_id: int, initial_content: str = ""):
        await websocket.accept()
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []
        
        # Add the connection with user info
        self.active_connections[document_id].append({
            "websocket": websocket,
            "user_id": user_id
        })

        # Send initial content to the new connection
        if initial_content is not None:
            await self.send_personal_message(websocket, {
                "type": "init",
                "content": initial_content
            })

        # Notify other users that a new user has joined
        for connection in self.active_connections[document_id]:
            if connection["websocket"] != websocket:
                await self.send_personal_message(
                    connection["websocket"],
                    {
                        "type": "user_joined",
                        "user_id": user_id
                    }
                )

    def disconnect(self, websocket: WebSocket, document_id: int, user_id: int):
        if document_id in self.active_connections:
            # Remove the specific connection
            self.active_connections[document_id] = [
                conn for conn in self.active_connections[document_id] 
                if conn["websocket"] != websocket
            ]
            
            # Remove the document room if no more connections
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]
                # Also remove the CRDT instance if no connections remain
                if document_id in self.document_crtds:
                    del self.document_crtds[document_id]

    async def broadcast_to_room(self, document_id: int, data: dict, sender_user_id: int, sender_websocket: WebSocket):
        if document_id in self.active_connections:
            for connection in self.active_connections[document_id]:
                # Don't send the message back to the sender
                if connection["websocket"] != sender_websocket:
                    try:
                        await connection["websocket"].send_json(data)
                    except:
                        # Handle disconnected clients
                        self.disconnect(connection["websocket"], document_id, connection["user_id"])

    async def send_personal_message(self, websocket: WebSocket, data: dict):
        await websocket.send_json(data)