#!/usr/bin/env bash
# Start the backend (FastAPI, port 8000) and the frontend (Vite, port 5173) together.
# Stop both with Ctrl+C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

(cd "$ROOT/backend" && uv run uvicorn app.main:app --reload --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd "$ROOT/frontend" && npm run dev
