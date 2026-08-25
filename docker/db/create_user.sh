#!/bin/sh
set -e

echo "Creating database role: ${POSTGRES_ADMIN_USER}"

# In the official postgres:alpine image, the default superuser is always 'postgres'
# We connect as 'postgres' to create other users and databases
psql --username postgres <<-EOSQL
CREATE USER ${POSTGRES_ADMIN_USER} WITH CREATEDB SUPERUSER PASSWORD '${POSTGRES_ADMIN_PASSWORD}';
CREATE USER ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}';
CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_ADMIN_USER};
EOSQL

# Now connect to the newly created database and enable extensions
psql --username ${POSTGRES_ADMIN_USER} -d ${POSTGRES_DB} <<-EOSQL
CREATE EXTENSION IF NOT EXISTS pgcrypto CASCADE;
EOSQL

echo "Database setup complete!"