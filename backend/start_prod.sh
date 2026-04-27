#!/bin/bash
# Production startup script for the FastAPI backend.
# Reads PORT from environment (set by Render, Railway, Replit, etc.).
exec python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --workers 2 \
  --log-level info
