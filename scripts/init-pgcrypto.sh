#!/bin/bash
# Initialize pgcrypto extension before starting the app

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h db -p 5432; do
  sleep 1
done

echo "Creating pgcrypto extension..."
PGPASSWORD="$POSTGRES_ADMIN_PASSWORD" psql -h db -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" || {
  echo "Extension might already exist or DB not ready"
}

echo "pgcrypto extension ready!"
