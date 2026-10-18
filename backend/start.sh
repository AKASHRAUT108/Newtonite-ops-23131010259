#!/bin/sh
set -e

echo "=== STARTING START.SH ==="
echo "Running migrations..."
alembic upgrade head

echo "Seeding database..."
python -m app.seed || echo "Seed skipped (already seeded)"

echo "Starting API on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"