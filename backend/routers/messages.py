from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.deps import get_current_user
from backend.database import get_pool
from backend.routers.conversations import _get_user_conversations, _row_to_message
from backend.routers.users import _row_to_user

router = APIRouter(prefix="/api")


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["claims"]["sub"]

    # Verify user is a participant
    user_convs = await _get_user_conversations(user_id)
    if not any(c["id"] == conversation_id for c in user_convs):
        raise HTTPException(status_code=403, detail="Unauthorized - not a participant in this conversation")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM messages
            WHERE conversation_id = $1
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at ASC
            """,
            conversation_id,
        )
    return [_row_to_message(r) for r in rows]


class SendMessage(BaseModel):
    conversationId: str
    content: str


@router.post("/messages")
async def send_message(
    data: SendMessage,
    user: dict = Depends(get_current_user),
):
    from backend.websocket import manager

    user_id = user["claims"]["sub"]

    # Verify user is a participant
    user_convs = await _get_user_conversations(user_id)
    conv = next((c for c in user_convs if c["id"] == data.conversationId), None)
    if not conv:
        raise HTTPException(status_code=403, detail="Unauthorized - not a participant in this conversation")

    pool = await get_pool()
    async with pool.acquire() as conn:
        msg_row = await conn.fetchrow(
            """
            INSERT INTO messages (id, conversation_id, sender_id, content)
            VALUES (gen_random_uuid(), $1, $2, $3)
            RETURNING *
            """,
            data.conversationId,
            user_id,
            data.content,
        )
        # Update last_message_at on the conversation
        await conn.execute(
            "UPDATE conversations SET last_message_at = NOW() WHERE id = $1",
            data.conversationId,
        )
        sender_row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    message = _row_to_message(msg_row)
    sender = _row_to_user(sender_row)

    # Broadcast via WebSocket to participants only
    participants = [conv["participant1Id"], conv["participant2Id"]]
    await manager.send_to_users(participants, {
        "type": "new_message",
        "data": {**message, "sender": sender},
    })

    return message
