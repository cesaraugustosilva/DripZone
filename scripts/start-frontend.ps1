param(
    [int]$Port = 4173,
    [string]$ApiProxyTarget = ""
)

$ErrorActionPreference = "Stop"
$FrontendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\frontend")
$UploadsRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend\storage\uploads")

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js nao encontrado no PATH."
}

Write-Host "DripZone frontend: http://127.0.0.1:$Port/"
if (-not $ApiProxyTarget) {
    $ApiProxyTarget = "http://127.0.0.1:8080"
}

Write-Host "Admin API canonica: /api via proxy local para $ApiProxyTarget/api"
Write-Host "Uploads: Docker/Caddy em 8080 primeiro; fallback host somente se configurado/necessario."
Push-Location $FrontendRoot
try {
    $env:PORT = "$Port"
    $env:API_PROXY_TARGET = $ApiProxyTarget
    if (-not $env:UPLOADS_PROXY_TARGETS) {
        $env:UPLOADS_PROXY_TARGETS = "http://127.0.0.1:8080,http://127.0.0.1:3000"
    }
    if (-not $env:UPLOADS_ROOT) {
        $env:UPLOADS_ROOT = "$UploadsRoot"
    }
    node (Join-Path $PSScriptRoot "static-server.js")
}
finally {
    Pop-Location
}
