#!/bin/bash
# Script to apply incident management migration and restart DFIR-IRIS containers
# Run this after Docker Desktop is fully started

set -e

echo "=========================================="
echo "DFIR-IRIS Incident Management Setup"
echo "=========================================="
echo ""

# Check if Docker is running
if ! docker ps &>/dev/null; then
    echo "ERROR: Docker is not running. Please start Docker Desktop first."
    echo "After starting Docker Desktop, wait 30-60 seconds for full initialization."
    echo ""
    echo "To start Docker Desktop:"
    echo '  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"'
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✓ Docker is running"

# Navigate to project root
cd /c/Users/user/Desktop/projects/iris-web-utmn

# Stop containers
echo ""
echo "Stopping containers..."
docker compose down

# Apply migration
echo ""
echo "Applying incident management migration..."
docker compose run --rm web alembic -c app/alembic.ini upgrade head

# Start containers
echo ""
echo "Starting containers..."
docker compose up -d

# Wait for services to be ready
echo ""
echo "Waiting for services to start..."
sleep 10

# Check container status
echo ""
echo "Container status:"
docker compose ps

echo ""
echo "=========================================="
echo "✓ Migration applied successfully!"
echo ""
echo "Next steps:"
echo "1. Open DFIR-IRIS in your browser"
echo "2. Navigate to any case"
echo "3. Add the 'Управление инцидентом ИБ' button to the case page"
echo "   (see INCIDENT_MANAGEMENT_IMPLEMENTATION.md for integration instructions)"
echo ""
echo "The following endpoints are now available:"
echo "  - GET  /manage/incident/categories/list"
echo "  - GET  /manage/incident/system-types/list"
echo "  - POST /manage/incident/calculate-priority"
echo "  - POST /manage/incident/case/<id>/update"
echo "  - GET  /manage/incident/case/<id>"
echo ""
echo "See INCIDENT_MANAGEMENT_IMPLEMENTATION.md for full documentation."
echo "=========================================="
