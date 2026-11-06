<#
.SYNOPSIS
  Bring up a local Switch server (switch-core + Postgres + Mattermost + Gateway)
  from Switch's published standalone Compose file.

.DESCRIPTION
  Windows equivalent of Switch's `just init-env` + `docker compose up`.
  On first run it copies Switch's .env.example into infra/switch.env and fills
  every blank secret with a fresh random value (same keys as
  deploy/local/generate-env-secrets.sh). Later runs reuse that file, because the
  Postgres volume keeps the passwords it was created with.

  Requires: Docker Desktop, and a clone of sandbox-quantum/switch
  (default: ..\switch-repo next to this project, or pass -SwitchRepo).
#>
param(
  [string]$SwitchRepo = (Join-Path $PSScriptRoot "..\..\switch-repo"),
  [switch]$Down
)
$ErrorActionPreference = "Stop"

$SwitchRepo = (Resolve-Path $SwitchRepo).Path
$compose    = Join-Path $SwitchRepo "deploy\local\standalone-docker-compose.yml"
$envFile    = Join-Path $PSScriptRoot "switch.env"
$project    = "switch-sentry-stack"

if (-not (Test-Path $compose)) { throw "Switch compose file not found at $compose. Clone https://github.com/sandbox-quantum/switch first." }

if ($Down) {
  docker compose -p $project --env-file $envFile -f $compose --profile collab --profile gateway down
  exit $LASTEXITCODE
}

function New-Hex([int]$bytes) {
  $b = New-Object byte[] $bytes
  # Create().GetBytes works on Windows PowerShell 5.1 as well as PowerShell 7.
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  -join ($b | ForEach-Object { $_.ToString("x2") })
}

if (-not (Test-Path $envFile)) {
  Write-Host "Generating $envFile with fresh secrets..."
  $lines = Get-Content (Join-Path $SwitchRepo ".env.example")
  $secrets = "DB_PASSWORD","DB_OWNER_PASSWORD","AGENT_REGISTRATION_TOKEN","GATEWAY_ADMIN_PASSWORD","MATTERMOST_ADMIN_PASSWORD","MATTERMOST_USER_PASSWORD"
  $overrides = @{
    # 5432 is often taken by another local Postgres; keep Switch's off it.
    "POSTGRES_HOST_PORT" = "55432"
    "FRONTEND_BASE_URL"  = "http://localhost:3000"
    "SECRET_KEYS"        = "local:$(New-Hex 32)"
  }
  foreach ($k in $secrets) { $overrides[$k] = New-Hex 24 }
  $out = foreach ($line in $lines) {
    if ($line -match '^([A-Z_]+)=') {
      $key = $Matches[1]
      if ($overrides.ContainsKey($key)) { "$key=$($overrides[$key])"; continue }
    }
    $line
  }
  Set-Content -Path $envFile -Value $out -Encoding utf8
}

docker compose -p $project --env-file $envFile -f $compose --profile collab --profile gateway up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$cfg = @{}
Get-Content $envFile | Where-Object { $_ -match '^([A-Z_]+)=(.*)$' } | ForEach-Object { $cfg[$Matches[1]] = $Matches[2] }

Write-Host ""
Write-Host "Switch is starting. Endpoints:"
Write-Host "  Agent bridge API : http://localhost:$($cfg.API_HOST_PORT)   (GET /health)"
Write-Host "  Gateway          : http://localhost:$($cfg.GATEWAY_HOST_PORT)  login $($cfg.GATEWAY_ADMIN_EMAIL)"
Write-Host "  Mattermost       : http://localhost:$($cfg.MATTERMOST_HOST_PORT)  user '$($cfg.MATTERMOST_USER)'"
Write-Host "Secrets (passwords, AGENT_REGISTRATION_TOKEN) are in infra\switch.env - never commit it."
