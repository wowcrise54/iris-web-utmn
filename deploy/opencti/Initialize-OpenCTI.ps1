param(
    [string]$AdminEmail = "admin@opencti.local",
    [string]$AlienVaultApiKey = ""
)

$ErrorActionPreference = "Stop"
$outputPath = Join-Path $PSScriptRoot ".env"

if (Test-Path -LiteralPath $outputPath) {
    Write-Host "OpenCTI .env already exists: $outputPath"
    exit 0
}

function New-RandomBytes {
    param([int]$Count)

    $bytes = New-Object byte[] $Count
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return $bytes
}

function New-RandomHex {
    param([int]$Count)

    return ([System.BitConverter]::ToString((New-RandomBytes -Count $Count))).Replace("-", "").ToLowerInvariant()
}

$values = @(
    "OPENCTI_VERSION=7.260728.0"
    "OPENCTI_ADMIN_EMAIL=$AdminEmail"
    "OPENCTI_ADMIN_PASSWORD=OpenCTI!$(New-RandomHex -Count 16)"
    "OPENCTI_ADMIN_TOKEN=$([guid]::NewGuid())"
    "OPENCTI_ENCRYPTION_KEY=$([Convert]::ToBase64String((New-RandomBytes -Count 32)))"
    "OPENCTI_HEALTHCHECK_ACCESS_KEY=$(New-RandomHex -Count 32)"
    "MINIO_ROOT_USER=opencti"
    "MINIO_ROOT_PASSWORD=$(New-RandomHex -Count 24)"
    "RABBITMQ_DEFAULT_USER=opencti"
    "RABBITMQ_DEFAULT_PASS=$(New-RandomHex -Count 24)"
    "ALIENVAULT_CONNECTOR_ID=$([guid]::NewGuid())"
    "ALIENVAULT_API_KEY=$AlienVaultApiKey"
    "ALIENVAULT_PULSE_START_TIMESTAMP=$([DateTime]::UtcNow.AddMonths(-1).ToString('yyyy-MM-ddT00:00:00'))"
)

[System.IO.File]::WriteAllLines(
    $outputPath,
    $values,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Generated local OpenCTI configuration: $outputPath"
Write-Host "Admin email: $AdminEmail"
Write-Host "The generated password and API token are stored only in the ignored .env file."
