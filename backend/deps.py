import os
import time

import httpx
import jwt
from fastapi import Depends, HTTPException, Request

CLIENT_ID = os.environ.get("REPL_ID", "")


async def _refresh_token(session_user: dict, request: Request) -> dict:
    from backend.auth import get_oidc_config
    refresh_token = session_user.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        config = await get_oidc_config()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                config["token_endpoint"],
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLIENT_ID,
                },
            )
            tokens = resp.json()

        id_token = tokens.get("id_token", "")
        claims = jwt.decode(id_token, options={"verify_signature": False})

        session_user["claims"] = claims
        session_user["access_token"] = tokens.get("access_token")
        session_user["refresh_token"] = tokens.get("refresh_token", refresh_token)
        session_user["expires_at"] = claims.get("exp", int(time.time()) + 3600)
        request.session["user"] = session_user
        return session_user
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def get_current_user(request: Request) -> dict:
    session_user = request.session.get("user")
    if not session_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    expires_at = session_user.get("expires_at", 0)
    if int(time.time()) <= expires_at:
        return session_user

    return await _refresh_token(session_user, request)


async def get_current_admin(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    from backend.database import get_pool
    user_id = user["claims"]["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_admin FROM users WHERE id = $1", user_id)
    if not row or not row["is_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden: admin access required")
    return user
