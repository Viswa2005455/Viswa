# Finance Intelligence Studio: one container that serves the website and the API on one address.
# Build:  docker build -t finance-studio .
# Run:    docker run -p 8000:8000 -e DATABASE_URL=postgresql://user:pass@host:5432/db finance-studio
# The start command applies database migrations first. Production needs PostgreSQL (see render.yaml).

# ---- 1. build the website
FROM node:22.22.0-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. the Python app
FROM python:3.13-slim-bookworm
RUN pip install --no-cache-dir uv==0.11.32
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/backend/.venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=web /src/frontend/dist /app/frontend/dist
RUN useradd --system --uid 10001 --home-dir /app app && mkdir -p /app/backend/storage && chown -R app /app/backend/storage
USER app

ENV PATH="/app/backend/.venv/bin:$PATH" FIS_ENV=production PORT=8000
EXPOSE 8000
# --proxy-headers: hosting platforms put a proxy in front; it passes the visitor's real address,
# which the sign-in rate limits use. Only the platform's proxy can reach the container.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
