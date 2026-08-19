param(
    [int]$FrontendPort = 4173,
    [int]$BackendPort = 3000,
    [ValidateSet("docker", "host")]
    [string]$Mode = "host"
)

$ErrorActionPreference = "Stop"
$FrontendScript = Resolve-Path (Join-Path $PSScriptRoot "start-frontend.ps1")
$BackendScript = Resolve-Path (Join-Path $PSScriptRoot "start-backend.ps1")

if ($Mode -eq "docker") {
    Write-Host "Iniciando DripZone em modo Docker canonico."
    Write-Host "Frontend: http://127.0.0.1:$FrontendPort/"
    Write-Host "API Admin em 4173: /api via proxy para http://127.0.0.1:8080/api"
    Write-Host "Uploads: /uploads via Docker/Caddy em 8080"
    Write-Host "Backend host em 3000 nao sera iniciado neste modo."
    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$FrontendScript`"", "-Port", "$FrontendPort"
    return
}

Write-Host "Iniciando DripZone em modo host dev."
Write-Host "Frontend: http://127.0.0.1:$FrontendPort/"
Write-Host "Backend:  http://127.0.0.1:$BackendPort/"
Write-Host "Use -Mode docker para operar contra API/uploads canonicos em 8080."

Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$BackendScript`"", "-Port", "$BackendPort"
Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$FrontendScript`"", "-Port", "$FrontendPort"
