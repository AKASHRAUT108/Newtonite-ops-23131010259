#!/bin/sh
set -e

echo "Running migrations..."
alembic upgrade head

echo "Seeding (idempotent)..."
python -m app.seed || echo "Seed skipped (already seeded)"

echo "Starting API on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"