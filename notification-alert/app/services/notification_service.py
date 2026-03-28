from app.services.ws_manager import ws_manager
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json
import asyncio

router = APIRouter()
connections: List[WebSocket] = [] 

async def notify_users(payload: dict, user_id: str | None = None):
    if user_id:
        return await ws_manager.send_to_user(user_id, payload)
    else:
        await ws_manager.broadcast(payload)
        return True

@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = None  

    try:
        user_id = websocket.query_params.get("user_id")

        if not user_id:
            data = await websocket.receive_json()
            user_id = data.get("user_id")

        await ws_manager.connect(websocket, user_id)
        print(f"User {user_id} connected")

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        if user_id:
            ws_manager.disconnect(websocket, user_id)
            print(f"User {user_id} disconnected")

    except asyncio.CancelledError:
        print("WebSocket shutting down gracefully")
        if user_id:
            ws_manager.disconnect(websocket, user_id)
        raise
