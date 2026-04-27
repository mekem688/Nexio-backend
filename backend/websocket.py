import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.auth import decode_session_cookie
from backend.database import get_pool

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send_to(self, user_id: str, payload: dict):
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_json(payload)
            except Exception:
                self.active.pop(user_id, None)

    async def broadcast(self, payload: dict, exclude: str | None = None):
        dead = []
        for uid, ws in list(self.active.items()):
            if uid == exclude:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.active.pop(uid, None)

    async def send_to_users(self, user_ids: list[str], payload: dict):
        for uid in user_ids:
            await self.send_to(uid, payload)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Authenticate via session cookie
    session_cookie = websocket.cookies.get("session")
    if not session_cookie:
        await websocket.close(code=4001)
        return

    session = decode_session_cookie(session_cookie)
    user_info = session.get("user")
    if not user_info:
        await websocket.close(code=4001)
        return

    user_id: str = user_info["claims"]["sub"]

    await manager.connect(user_id, websocket)

    pool = await get_pool()

    # Set user online
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_online = TRUE, last_active = NOW(), updated_at = NOW() WHERE id = $1",
            user_id,
        )
        online_users = await conn.fetch(
            "SELECT * FROM users WHERE is_online = TRUE"
        )

    # Send current online users list to the newly connected client
    await websocket.send_json({
        "type": "online_users_sync",
        "data": [dict(row) for row in online_users],
    })

    # Notify others that this user is now online
    await manager.broadcast(
        {"type": "user_status_update", "data": {"userId": user_id, "isOnline": True}},
        exclude=user_id,
    )

    try:
        while True:
            await websocket.receive_text()  # keep connection alive; we ignore client messages
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_online = FALSE, updated_at = NOW() WHERE id = $1",
                user_id,
            )
        await manager.broadcast(
            {"type": "user_status_update", "data": {"userId": user_id, "isOnline": False}},
            exclude=user_id,
        )
