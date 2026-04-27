import os
import time
import secrets
import hashlib
import base64
import json
import urllib.parse

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

ISSUER_URL = os.environ.get("ISSUER_URL", "https://replit.com/oidc")
CLIENT_ID = os.environ.get("REPL_ID", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "fallback-secret-key")

# BACKEND_URL: the public URL of this FastAPI backend.
# Set this in production so the OAuth callback URL is stable (e.g. https://nexio-api.repl.co).
# Leave empty in development — the URL is inferred from the incoming request.
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")

# FRONTEND_URL: the URL of the deployed frontend (e.g. https://nexio.vercel.app).
# After a successful login the backend redirects here.
# Leave empty in development — redirects to "/" (served by Vite on same host).
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")

_oidc_config: dict | None = None


async def get_oidc_config() -> dict:
    global _oidc_config
    if _oidc_config is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{ISSUER_URL}/.well-known/openid-configuration")
            resp.raise_for_status()
            _oidc_config = resp.json()
    return _oidc_config


def _generate_pkce() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def _get_callback_url(request: Request) -> str:
    """Return the absolute callback URL for OAuth.

    Uses BACKEND_URL env var if set (recommended in production),
    otherwise infers from the incoming request headers.
    """
    if BACKEND_URL:
        return f"{BACKEND_URL}/api/callback"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", "https")
    return f"{scheme}://{host}/api/callback"


async def _upsert_user(claims: dict) -> None:
    from backend.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (id, email, first_name, last_name, profile_image_url, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                updated_at = NOW()
            """,
            claims.get("sub"),
            claims.get("email"),
            claims.get("first_name"),
            claims.get("last_name"),
            claims.get("profile_image_url"),
        )


@router.get("/api/login")
async def login(request: Request):
    config = await get_oidc_config()
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = _generate_pkce()

    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = code_verifier

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _get_callback_url(request),
        "scope": "openid email profile offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login consent",
    }
    auth_url = config["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(auth_url)


@router.get("/api/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    if state != request.session.get("oauth_state"):
        return RedirectResponse(_get_callback_url(request).replace("/api/callback", "/api/login"))

    code_verifier = request.session.pop("oauth_code_verifier", "")
    request.session.pop("oauth_state", None)

    config = await get_oidc_config()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            config["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _get_callback_url(request),
                "client_id": CLIENT_ID,
                "code_verifier": code_verifier,
            },
        )
        tokens = resp.json()

    id_token = tokens.get("id_token", "")
    claims = jwt.decode(id_token, options={"verify_signature": False})

    await _upsert_user(claims)

    request.session["user"] = {
        "claims": claims,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": claims.get("exp", int(time.time()) + 3600),
    }

    # Redirect to the frontend (Vercel) if configured, otherwise same-host root
    destination = FRONTEND_URL if FRONTEND_URL else "/"
    return RedirectResponse(destination)


@router.get("/api/logout")
async def logout(request: Request):
    config = await get_oidc_config()
    request.session.clear()

    post_logout_uri = FRONTEND_URL if FRONTEND_URL else "/"
    if not post_logout_uri.startswith("http"):
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        scheme = request.headers.get("x-forwarded-proto", "https")
        post_logout_uri = f"{scheme}://{host}"

    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "post_logout_redirect_uri": post_logout_uri,
    })
    end_session_url = config.get("end_session_endpoint", ISSUER_URL + "/logout")
    return RedirectResponse(f"{end_session_url}?{params}")


def decode_session_cookie(cookie_value: str) -> dict:
    """Decode a Starlette SessionMiddleware signed cookie (no salt)."""
    from itsdangerous import TimestampSigner, BadSignature
    signer = TimestampSigner(SESSION_SECRET)
    try:
        data = signer.unsign(cookie_value, max_age=7 * 24 * 3600)
        return json.loads(base64.b64decode(data))
    except (BadSignature, Exception):
        return {}
