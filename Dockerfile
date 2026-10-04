# Live Studio: one container with the FastAPI backend serving the built frontend (DEPLOY.md).
# Stage 1 builds frontend/dist; stage 2 runs the backend with uv. Secrets are never baked in:
# Google APIs use the Cloud Run service account (ADC).
FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY data/ /app/data/
COPY prompts/ /app/prompts/
COPY --from=web /app/frontend/dist /app/frontend/dist
ENV APP_ENV=cloud PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
