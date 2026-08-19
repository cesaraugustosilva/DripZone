param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$BackendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Ambiente virtual nao encontrado em backend\.venv."
}

Write-Host "DripZone backend: http://127.0.0.1:$Port/"
Push-Location $BackendRoot
try {
    $env:PORT = "$Port"
    & $Python run.py
}
finally {
    Pop-Location
}
