ARG PYTHON_VERSION=3.11

# ---------- Frontend build stage ----------
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ---------- Backend runtime stage ----------
FROM python:${PYTHON_VERSION}-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (for wheels / SSL / fonts used by reportlab, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code and requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ api/
COPY src/ src/
COPY config/ config/

# Copy pre-built frontend assets into image
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Application data directory (SQLite DB, orchestrator state, etc.)
VOLUME ["/app/data"]

# Expose API port
EXPOSE 8000

# Uvicorn entrypoint
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

