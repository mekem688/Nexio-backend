from fastapi import APIRouter, Depends, HTTPException
from backend.deps import get_current_user, get_current_admin
from backend.database import get_pool
from backend.routers.users import _row_to_user
from backend.routers.conversations import _row_to_conversation, _row_to_message

router = APIRouter(prefix="/api/admin")


@router.post("/claim")
async def claim_admin(user: dict = Depends(get_current_user)):
    user_id = user["claims"]["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
        if count > 0:
            raise HTTPException(status_code=403, detail="An admin already exists")
        row = await conn.fetchrow(
            "UPDATE users SET is_admin = TRUE, updated_at = NOW() WHERE id = $1 RETURNING *",
            user_id,
        )
    return _row_to_user(row)


@router.get("/check")
async def check_admin(user: dict = Depends(get_current_user)):
    user_id = user["claims"]["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_admin FROM users WHERE id = $1", user_id)
        admin_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
    return {
        "isAdmin": bool(row and row["is_admin"]),
        "adminExists": admin_count > 0,
    }


@router.get("/stats")
async def get_stats(_: dict = Depends(get_current_admin)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE expires_at > NOW()"
        )
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE created_at >= CURRENT_DATE AND expires_at > NOW()"
        )
        active_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_online = TRUE"
        )
    return {"total": total, "today": today, "activeUsers": active_users}


@router.get("/messages/recent")
async def get_recent_messages(
    limit: int = 10,
    _: dict = Depends(get_current_admin),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT m.*, u.id as u_id, u.first_name, u.last_name, u.profile_image_url,
                   u.email, u.age, u.marital_status, u.profession, u.hobbies,
                   u.is_online, u.is_admin, u.last_active,
                   u.created_at as u_created_at, u.updated_at as u_updated_at,
                   c.id as c_id, c.participant1_id, c.participant2_id,
                   c.last_message_at, c.created_at as c_created_at
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.expires_at > NOW()
            ORDER BY m.created_at DESC
            LIMIT $1
            """,
            limit,
        )

    result = []
    for row in rows:
        d = dict(row)
        msg = _row_to_message(row)
        msg["sender"] = {
            "id": d.get("u_id"),
            "email": d.get("email"),
            "firstName": d.get("first_name"),
            "lastName": d.get("last_name"),
            "profileImageUrl": d.get("profile_image_url"),
            "age": d.get("age"),
            "maritalStatus": d.get("marital_status"),
            "profession": d.get("profession"),
            "hobbies": d.get("hobbies"),
            "isOnline": d.get("is_online", False),
            "isAdmin": d.get("is_admin", False),
            "lastActive": d.get("last_active").isoformat() if d.get("last_active") else None,
            "createdAt": d.get("u_created_at").isoformat() if d.get("u_created_at") else None,
            "updatedAt": d.get("u_updated_at").isoformat() if d.get("u_updated_at") else None,
        }
        msg["conversation"] = {
            "id": d.get("c_id"),
            "participant1Id": d.get("participant1_id"),
            "participant2Id": d.get("participant2_id"),
            "lastMessageAt": d.get("last_message_at").isoformat() if d.get("last_message_at") else None,
            "createdAt": d.get("c_created_at").isoformat() if d.get("c_created_at") else None,
        }
        result.append(msg)

    return result


@router.post("/cleanup")
async def cleanup(_: dict = Depends(get_current_admin)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted_messages = await conn.fetchval(
            "WITH deleted AS (DELETE FROM messages WHERE expires_at < NOW() RETURNING id) SELECT COUNT(*) FROM deleted"
        )
        deleted_stories = await conn.fetchval(
            "WITH deleted AS (DELETE FROM stories WHERE expires_at < NOW() RETURNING id) SELECT COUNT(*) FROM deleted"
        )
    return {"deletedMessages": deleted_messages, "deletedStories": deleted_stories}
