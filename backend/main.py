import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.database import lifespan
from backend.auth import router as auth_router
from backend.routers.users import router as users_router
from backend.routers.conversations import router as conversations_router
from backend.routers.messages import router as messages_router
from backend.routers.stories import router as stories_router
from backend.routers.admin import router as admin_router
from backend.websocket import router as ws_router

app = FastAPI(title="Nexio API", lifespan=lifespan)

SESSION_SECRET = os.environ.get("SESSION_SECRET", "nexio-secret-key-change-in-prod")

# When FRONTEND_URL is set the frontend lives on a different domain (e.g. Vercel).
# Cookies must be SameSite=None + Secure so browsers send them cross-origin.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")
cross_origin = bool(FRONTEND_URL)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="session",
    max_age=7 * 24 * 60 * 60,
    https_only=cross_origin,          # Secure flag required for SameSite=None
    same_site="none" if cross_origin else "lax",
)

# Build CORS origins list
_cors_origins = [
    "http://localhost:5000",
    "http://localhost:5173",
]
if FRONTEND_URL:
    _cors_origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.include_router(stories_router)
app.include_router(admin_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Nexio FastAPI Backend"}
