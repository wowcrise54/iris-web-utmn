# DFIR-IRIS Incident Management Setup Script
# Run this from PowerShell to apply migration and restart containers

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "DFIR-IRIS Incident Management Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker Desktop is running
Write-Host "Checking Docker Desktop status..." -ForegroundColor Yellow
try {
    $dockerRunning = docker ps 2>&1 | Select-String -Pattern "CONTAINER" -Quiet
} catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-Host "Docker Desktop is not running or not fully initialized." -ForegroundColor Red
    Write-Host ""
    Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    
    Write-Host "Waiting for Docker Desktop to fully start (this may take 60-90 seconds)..." -ForegroundColor Yellow
    Write-Host ""
    
    # Wait for Docker to be ready (up to 90 seconds)
    $maxWait = 90
    $waited = 0
    while ($waited -lt $maxWait) {
        try {
            $test = docker ps 2>&1
            if ($test -match "CONTAINER") {
                Write-Host "✓ Docker is ready!" -ForegroundColor Green
                break
            }
        } catch {}
        
        Start-Sleep -Seconds 5
        $waited += 5
        Write-Host "Waiting... ($waited/$maxWait seconds)" -NoNewline
        Write-Host "." -NoNewline
    }
    
    if ($waited -ge $maxWait) {
        Write-Host ""
        Write-Host "ERROR: Docker Desktop did not start within $maxWait seconds." -ForegroundColor Red
        Write-Host "Please wait for Docker Desktop to fully load and run this script again." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✓ Docker is already running" -ForegroundColor Green
}

Write-Host ""
Write-Host "Stopping containers..." -ForegroundColor Yellow
docker compose down

Write-Host ""
Write-Host "Applying incident management migration..." -ForegroundColor Yellow
docker compose run --rm web alembic -c app/alembic.ini upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Migration failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Starting containers..." -ForegroundColor Yellow
docker compose up -d

Write-Host ""
Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "Container status:" -ForegroundColor Yellow
docker compose ps

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "✓ Migration applied successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Open DFIR-IRIS in your browser"
Write-Host "2. Navigate to any case"
Write-Host "3. Add the 'Управление инцидентом ИБ' button to the case page"
Write-Host "   (see INCIDENT_MANAGEMENT_IMPLEMENTATION.md for integration instructions)"
Write-Host ""
Write-Host "Available API endpoints:" -ForegroundColor Cyan
Write-Host "  - GET  /manage/incident/categories/list"
Write-Host "  - GET  /manage/incident/system-types/list"
Write-Host "  - POST /manage/incident/calculate-priority"
Write-Host "  - POST /manage/incident/case/<id>/update"
Write-Host "  - GET  /manage/incident/case/<id>"
Write-Host ""
Write-Host "Full documentation: INCIDENT_MANAGEMENT_IMPLEMENTATION.md" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
