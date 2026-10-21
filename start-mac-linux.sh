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
# backend/.env copied from .env.example may still carry the example PostgreSQL line; if that example
# server is not running, use the local database file instead.
if [ -z "${DATABASE_URL:-}" ] && grep -q '^DATABASE_URL=postgresql+psycopg://fis_app:fis_dev_password@localhost:5432/' backend/.env 2>/dev/null \
   && ! (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null; then
  echo "      Note: backend/.env has the example PostgreSQL line, but PostgreSQL is not running."
  export DATABASE_URL="sqlite:///storage/finance_studio.db"
fi
if [ -z "${DATABASE_URL:-}" ] && ! grep -qi '^DATABASE_URL' backend/.env 2>/dev/null; then
  export DATABASE_URL="sqlite:///storage/finance_studio.db"
  echo "      Database: local file backend/storage/finance_studio.db"
elif [ "${DATABASE_URL:-}" = "sqlite:///storage/finance_studio.db" ]; then
  echo "      Database: local file backend/storage/finance_studio.db"
else
  echo "      Database: PostgreSQL (DATABASE_URL)"
fi

echo "[3/5] Installing backend packages (the first time takes a few minutes)..."
(cd backend && uv sync)
echo "[4/5] Preparing the database..."
(cd backend && uv run alembic upgrade head)

# The marker is written only after a complete install, so an interrupted download is retried.
# It holds a fingerprint of package-lock.json, so a version that needs new packages installs them.
lock_id="$(cksum < frontend/package-lock.json)"
if [ "$(cat frontend/node_modules/.fis-installed 2>/dev/null)" != "$lock_id" ]; then
  for attempt in 1 2 3 4; do
    echo "[5/5] Installing website packages - attempt $attempt of 4 (the first time takes a few minutes)..."
    if (cd frontend && npm install); then
      cksum < frontend/package-lock.json > frontend/node_modules/.fis-installed  # npm may rewrite the lock file
      break
    fi
    if [ "$attempt" = 4 ]; then
      echo "Installing the website packages failed: the internet connection kept dropping."
      echo "Try another network (e.g. a phone hotspot), pause any VPN, then run this script again."
      exit 1
    fi
    echo "The connection dropped during the download. Retrying in 15 seconds..."
    sleep 15
  done
else
  echo "[5/5] Website packages are installed."
fi

# An older copy that is still running would keep ports 8000/5173 and answer instead of this one.
# Stop it only if it answers like this app; never touch other programs.
port_pids() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null || fuser "$1/tcp" 2>/dev/null || true; }
for check in "8000 http://localhost:8000/api/health database_engine" "5173 http://localhost:5173/ Finance.Intelligence.Studio"; do
  set -- $check
  pids="$(port_pids "$1")"
  [ -z "$pids" ] && continue
  if curl -fs --max-time 3 "$2" 2>/dev/null | grep -q "$3"; then
    echo "      An earlier copy of the app is still running on port $1. Stopping it..."
    kill $pids 2>/dev/null || true
    sleep 1
  else
    echo "Port $1 is being used by another program. Close it, then run this script again."
    exit 1
  fi
done

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
