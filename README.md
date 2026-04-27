# Nexio — Backend

FastAPI + Python 3.11 backend for the Nexio messaging app.

## Stack
- FastAPI + Uvicorn
- asyncpg (PostgreSQL async driver)
- Starlette SessionMiddleware (cookie sessions)
- Replit OAuth (OpenID Connect / PKCE)
- WebSocket (real-time messaging & presence)

## Local development

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SESSION_SECRET` | Yes | Random secret for cookie signing |
| `REPL_ID` | Yes | Replit app ID (OAuth client_id) |
| `BACKEND_URL` | Prod | Public URL of this backend |
| `FRONTEND_URL` | Prod | Public URL of the frontend |

## Deploy on Render

`render.yaml` at the root configures everything automatically.  
Import this repo on Render — it will detect `render.yaml` and create the service.  
Fill in the environment variables in Render's dashboard.

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/login` | Start Replit OAuth flow |
| GET | `/api/callback` | OAuth callback |
| GET | `/api/logout` | Logout |
| GET | `/api/auth/user` | Current authenticated user |
| GET | `/api/users` | All users |
| GET | `/api/conversations` | User conversations |
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations/{id}/messages` | Messages in conversation |
| POST | `/api/messages` | Send message |
| GET | `/api/stories` | Active stories |
| POST | `/api/stories` | Create story |
| GET | `/api/admin/check` | Check admin status |
| POST | `/api/admin/claim` | Claim admin role |
| GET | `/api/admin/stats` | Platform stats |
| WS | `/ws` | WebSocket connection |
