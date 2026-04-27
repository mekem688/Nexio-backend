from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from backend.deps import get_current_user
from backend.database import get_pool
from backend.routers.users import _row_to_user

router = APIRouter(prefix="/api")


def _row_to_story(row) -> dict:
    d = dict(row)
    return {
        "id": d.get("id"),
        "authorId": d.get("author_id"),
        "type": d.get("type"),
        "textContent": d.get("text_content"),
        "mediaUrl": d.get("media_url"),
        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
        "expiresAt": d.get("expires_at").isoformat() if d.get("expires_at") else None,
    }


@router.get("/stories")
async def get_active_stories(user: dict = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, u.id as u_id, u.email, u.first_name, u.last_name,
                   u.profile_image_url, u.age, u.marital_status, u.profession,
                   u.hobbies, u.is_online, u.is_admin, u.last_active,
                   u.created_at as u_created_at, u.updated_at as u_updated_at
            FROM stories s
            JOIN users u ON s.author_id = u.id
            WHERE s.expires_at > NOW()
            ORDER BY s.created_at DESC
            """
        )

    result = []
    for row in rows:
        d = dict(row)
        story = _row_to_story(row)
        story["author"] = {
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
        result.append(story)

    return result


class CreateStory(BaseModel):
    type: str = "text"
    textContent: Optional[str] = None
    mediaUrl: Optional[str] = None


@router.post("/stories")
async def create_story(
    data: CreateStory,
    user: dict = Depends(get_current_user),
):
    from backend.websocket import manager

    user_id = user["claims"]["sub"]

    if data.type == "text" and not data.textContent:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="textContent is required for text stories")

    pool = await get_pool()
    async with pool.acquire() as conn:
        story_row = await conn.fetchrow(
            """
            INSERT INTO stories (id, author_id, type, text_content, media_url)
            VALUES (gen_random_uuid(), $1, $2, $3, $4)
            RETURNING *
            """,
            user_id,
            data.type,
            data.textContent,
            data.mediaUrl,
        )
        author_row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    story = _row_to_story(story_row)
    author = _row_to_user(author_row)

    # Broadcast new story to all connected clients
    await manager.broadcast({"type": "new_story", "data": {**story, "author": author}})

    return story
