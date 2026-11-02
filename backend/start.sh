#!/bin/bash
set -e

# ResolveAI V2 — Production Container Entrypoint
echo "Starting ResolveAI V2 backend container..."

# Check database type
if [[ "${DATABASE_URL:-}" == *"postgres"* ]] || [[ -n "${POSTGRES_HOST:-}" ]]; then
    DB_HOST=${POSTGRES_HOST:-postgres}
    DB_PORT=${POSTGRES_PORT:-5432}
    DB_USER=${POSTGRES_USER:-postgres}
    echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT (user: $DB_USER)..."
    
    while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
        echo "PostgreSQL is unavailable - sleeping 2s"
        sleep 2
    done
    echo "PostgreSQL connection confirmed."
else
    echo "Database mode: SQLite (local volume persistence)."
fi

# Run migrations safely
echo "Applying Alembic database migrations..."
if ! alembic upgrade head; then
    echo "ERROR: Alembic migrations failed. Halting startup."
    exit 1
fi
echo "Database migrations up to date."

# Start FastAPI application
echo "Starting FastAPI on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
