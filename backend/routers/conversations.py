from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.deps import get_current_user
from backend.database import get_pool
from backend.routers.users import _row_to_user

router = APIRouter(prefix="/api")


def _row_to_conversation(row) -> dict:
    d = dict(row)
    return {
        "id": d.get("id"),
        "participant1Id": d.get("participant1_id"),
        "participant2Id": d.get("participant2_id"),
        "lastMessageAt": d.get("last_message_at").isoformat() if d.get("last_message_at") else None,
        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
    }


def _row_to_message(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    return {
        "id": d.get("id"),
        "conversationId": d.get("conversation_id"),
        "senderId": d.get("sender_id"),
        "content": d.get("content"),
        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
        "expiresAt": d.get("expires_at").isoformat() if d.get("expires_at") else None,
    }


async def _get_user_conversations(user_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        conv_rows = await conn.fetch(
            """
            SELECT * FROM conversations
            WHERE participant1_id = $1 OR participant2_id = $1
            ORDER BY last_message_at DESC
            """,
            user_id,
        )

        result = []
        for conv in conv_rows:
            other_id = conv["participant2_id"] if conv["participant1_id"] == user_id else conv["participant1_id"]
            other_user_row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", other_id)
            if not other_user_row:
                continue

            last_msg_row = await conn.fetchrow(
                """
                SELECT * FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                conv["id"],
            )

            result.append({
                **_row_to_conversation(conv),
                "otherUser": _row_to_user(other_user_row),
                "lastMessage": _row_to_message(last_msg_row),
            })

    return result


@router.get("/conversations")
async def get_conversations(user: dict = Depends(get_current_user)):
    user_id = user["claims"]["sub"]
    return await _get_user_conversations(user_id)


class CreateConversation(BaseModel):
    participantId: str


@router.post("/conversations")
async def create_conversation(
    data: CreateConversation,
    user: dict = Depends(get_current_user),
):
    user_id = user["claims"]["sub"]

    if user_id == data.participantId:
        raise HTTPException(status_code=400, detail="Cannot create conversation with yourself")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check participant exists
        participant = await conn.fetchrow("SELECT id FROM users WHERE id = $1", data.participantId)
        if not participant:
            raise HTTPException(status_code=400, detail="Participant user not found")

        # Find existing conversation
        existing = await conn.fetchrow(
            """
            SELECT * FROM conversations
            WHERE (participant1_id = $1 AND participant2_id = $2)
               OR (participant1_id = $2 AND participant2_id = $1)
            """,
            user_id,
            data.participantId,
        )
        if existing:
            return _row_to_conversation(existing)

        # Create new conversation
        new_conv = await conn.fetchrow(
            """
            INSERT INTO conversations (id, participant1_id, participant2_id)
            VALUES (gen_random_uuid(), $1, $2)
            RETURNING *
            """,
            user_id,
            data.participantId,
        )
        return _row_to_conversation(new_conv)
