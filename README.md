markdown
# Newtonite Ops — Roll 23131010259

An internal web app to create, assign, track, and resolve operational work items across teams, built for the Newtonite "Operations Under Pressure" challenge.

**Status:** Stage 1 — Foundation (in progress)

## Quick start

```bash
cp .env.example .env   # then set JWT_SECRET
docker compose up --build
API health: http://localhost:8000/health

text

That's the whole README for now — we'll expand it in Stage 6.

---

## Block 1.4 — Backend Dockerfile

Create **`backend/Dockerfile`**:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed by asyncpg / bcrypt at build time
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Non-root user
RUN useradd --create-home --uid 1000 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]