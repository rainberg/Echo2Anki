import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.auth_client import verify_token

router = APIRouter(tags=["ws"])


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    def connect(self, user_id: str, ws: WebSocket):
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self._connections:
            self._connections[user_id].discard(ws)
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        conns = self._connections.get(user_id, set())
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


manager = ConnectionManager()


@router.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    verify_result = await verify_token(token)
    if not verify_result:
        await ws.close(code=4001, reason="Invalid token")
        return

    user_id = verify_result.get("user_id")
    if not user_id:
        await ws.close(code=4001, reason="Invalid token payload")
        return

    manager.connect(user_id, ws)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60)
                if raw == "ping":
                    await ws.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)


async def broadcast_task_progress(user_id: str, task_id: str, stage: str, progress: float, message: str = ""):
    await manager.send_to_user(str(user_id), {
        "type": "task_progress",
        "task_id": task_id,
        "stage": stage,
        "progress": progress,
        "message": message,
    })
