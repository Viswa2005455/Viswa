#!/usr/bin/env bash
# Finance Intelligence Studio - one-click start for macOS and Linux.
# Installs uv if missing, prepares the database, starts the backend and the website,
# and opens the browser. Press Ctrl+C in this window to stop everything.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "=============================================================="
echo "   Finance Intelligence Studio - one-click start"
echo "=============================================================="

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "[1/5] Installing uv (Python package manager; it also downloads Python if needed)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "[1/5] uv is installed."
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[2/5] Node.js is not installed."
  echo "      macOS: install from https://nodejs.org (LTS) or run: brew install node"
  echo "      Linux: install Node.js 20+ with your package manager, e.g. sudo apt install nodejs npm"
  exit 1
fi
echo "[2/5] Node.js is installed ($(node --version))."

# Use PostgreSQL if backend/.env or the environment sets DATABASE_URL; otherwise a local database file.
if [ -z "${DATABASE_URL:-}" ] && ! grep -qi '^DATABASE_URL' backend/.env 2>/dev/null; then
  export DATABASE_URL="sqlite:///storage/finance_studio.db"
  echo "      Database: local file backend/storage/finance_studio.db"
else
  echo "      Database: PostgreSQL (DATABASE_URL)"
fi

echo "[3/5] Installing backend packages (the first time takes a few minutes)..."
(cd backend && uv sync)
echo "[4/5] Preparing the database..."
(cd backend && uv run alembic upgrade head)

if [ ! -d frontend/node_modules ]; then
  echo "[5/5] Installing website packages (the first time takes a few minutes)..."
  (cd frontend && npm install)
else
  echo "[5/5] Website packages are installed."
fi

(cd backend && uv run uvicorn app.main:app --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

(
  for _ in $(seq 1 90); do
    if curl -fs http://localhost:8000/api/health >/dev/null 2>&1 && curl -fs http://localhost:5173 >/dev/null 2>&1; then
      echo ""
      echo "  Ready: http://localhost:5173  (first time? click 'Create an account')"
      echo "  Press Ctrl+C here to stop the app."
      if command -v open >/dev/null 2>&1; then open http://localhost:5173; elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 >/dev/null 2>&1 || true; fi
      exit 0
    fi
    sleep 1
  done
) &

cd "$ROOT/frontend" && npm run dev
