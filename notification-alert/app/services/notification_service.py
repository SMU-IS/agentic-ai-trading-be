from app.services.ws_manager import ws_manager
from app.core.config import env_config
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json
import jwt
import asyncio
from fastapi import APIRouter, Header

from app.core.constant import APIPath

router = APIRouter()
connections: List[WebSocket] = [] 

async def notify_users(payload: dict, user_id: str | None = None):
    # if user_id:
    #     return await ws_manager.send_to_user(user_id, payload)
    # else:
    #     await ws_manager.broadcast(payload)
    #     return True
    if payload["type"] == "TRADE_PLACED":
        return await ws_manager.send_to_user(user_id, payload)

    elif payload["type"] == "SIGNAL_GENERATED":
        return await ws_manager.broadcast(payload)

    elif payload["type"] == "NEWS_RECEIVED":
        return await ws_manager.broadcast(payload)

@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    # user_id = websocket.headers.get("X-USER-ID")
    # print(user_id)

    
    if not user_id:
        await websocket.close(code=4001)
        return

    try:
        # token = websocket.headers.get("authorization")
        # if token and token.startswith("Bearer "):
        #     payload = jwt.decode(token, env_config.jwt_token, algorithms=["HS256"])
        #     user_id = payload.get("sub")

        # if not user_id:
        #     data = await websocket.receive_json()
        #     token = data.get("token") 
        #     if token:
        #         payload = jwt.decode(token, env_config.jwt_token, algorithms=["HS256"])
        #         user_id = payload.get("sub")

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

@router.get(APIPath.USER)
def get_current_user(x_user_id: str = Header(...)):
    if not x_user_id:
        return {"error": "User ID not found"}, 401

    return {"status": "success", "user_id": x_user_id}


