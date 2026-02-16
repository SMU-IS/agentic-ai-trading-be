from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json

router = APIRouter()
connections: List[WebSocket] = [] 

async def notify_users(trade_event: dict):
    message = json.dumps(trade_event)
    to_remove = []
    for ws in connections:
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)

    for ws in to_remove:
        connections.remove(ws)

@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            await websocket.receive_text() 
    except WebSocketDisconnect:
        connections.remove(websocket)
