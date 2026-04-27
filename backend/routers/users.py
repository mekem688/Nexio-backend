from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from backend.deps import get_current_user
from backend.database import get_pool

router = APIRouter(prefix="/api")


class ProfileUpdate(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    age: Optional[int] = None
    maritalStatus: Optional[str] = None
    profession: Optional[str] = None
    hobbies: Optional[str] = None
    profileImageUrl: Optional[str] = None


class StatusUpdate(BaseModel):
    isOnline: bool


def _row_to_user(row) -> dict:
    if row is None:
        return {}
    d = dict(row)
    # Convert snake_case DB columns to camelCase for frontend compatibility
    return {
        "id": d.get("id"),
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
        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
        "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
    }


@router.get("/auth/user")
async def get_auth_user(user: dict = Depends(get_current_user)):
    pool = await get_pool()
    user_id = user["claims"]["sub"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _row_to_user(row)


@router.get("/users")
async def get_all_users(user: dict = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE first_name IS NOT NULL AND first_name != '' ORDER BY last_active DESC"
        )
    return [_row_to_user(r) for r in rows]


@router.get("/users/online")
async def get_online_users(user: dict = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE is_online = TRUE ORDER BY last_active"
        )
    return [_row_to_user(r) for r in rows]


@router.put("/users/profile")
async def update_profile(
    data: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    user_id = user["claims"]["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users SET
                first_name = COALESCE($2, first_name),
                last_name = COALESCE($3, last_name),
                age = COALESCE($4, age),
                marital_status = COALESCE($5, marital_status),
                profession = COALESCE($6, profession),
                hobbies = COALESCE($7, hobbies),
                profile_image_url = COALESCE($8, profile_image_url),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            user_id,
            data.firstName,
            data.lastName,
            data.age,
            data.maritalStatus,
            data.profession,
            data.hobbies,
            data.profileImageUrl,
        )
    return _row_to_user(row)


@router.post("/users/status")
async def update_status(
    data: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    user_id = user["claims"]["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_online = $2, last_active = NOW(), updated_at = NOW() WHERE id = $1",
            user_id,
            data.isOnline,
        )
    return {"success": True}
