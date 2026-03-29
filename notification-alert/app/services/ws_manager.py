from fastapi import WebSocket
from typing import Dict, List

class WSManager:
    def __init__(self):
        self.user_connections: Dict[str, List[WebSocket]] = {}  
        self.all_connections: List[WebSocket] = []  

    async def connect(self, websocket: WebSocket, user_id: str):
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(websocket)
        self.all_connections.append(websocket)

        print("Connected users:", list(self.user_connections.keys()))

    def disconnect(self, websocket: WebSocket, user_id: str):
        if websocket in self.all_connections:
            self.all_connections.remove(websocket)
        if user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to a specific user."""
        if user_id not in self.user_connections:
            return False
        delivered = False
        for ws in self.user_connections[user_id]:
            try:
                await ws.send_json(message)
                delivered = True
            except Exception:
                pass
        return delivered

    async def broadcast(self, message: dict):
        """Send message to all connected users."""
        to_remove = []
        for ws in self.all_connections:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.all_connections.remove(ws)
            # Also remove from user_connections
            for user_id, conns in list(self.user_connections.items()):
                if ws in conns:
                    conns.remove(ws)
                    if not conns:
                        del self.user_connections[user_id]
        return True

ws_manager = WSManager()