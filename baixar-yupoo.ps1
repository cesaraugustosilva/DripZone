param()

$ErrorActionPreference = "Stop"

function Read-YupooUrl {
  Write-Host "> " -NoNewline
  try {
    return [Console]::ReadLine()
  }
  catch {
    return Read-Host "> "
  }
}

function Read-LineValue {
  param([string]$Prompt = "> ")
  Write-Host $Prompt -NoNewline
  try {
    return [Console]::ReadLine()
  }
  catch {
    return Read-Host $Prompt
  }
}

Write-Host "========================================"
Write-Host "       DRIPZONE - YUPOO DOWNLOADER"
Write-Host "========================================"
Write-Host ""
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$backendDir = Join-Path $projectRoot "backend"
$output = "..\downloads\yupoo"

if (!(Test-Path -LiteralPath $python)) {
  Write-Host "Erro: Python do venv nao encontrado em backend\.venv." -ForegroundColor Red
  exit 1
}

$mode = Read-LineValue "[R] Retomar download existente / [N] Novo download: "
if ($null -eq $mode) { $mode = "" }
$mode = $mode.Trim().ToUpperInvariant()
$arguments = @("-m", "app.scripts.download_yupoo_images", "--output", $output, "--verbose")

if ($mode -eq "R") {
  $runsRoot = Join-Path $projectRoot "downloads\yupoo"
  $runs = @(Get-ChildItem -LiteralPath $runsRoot -Directory -ErrorAction SilentlyContinue | Where-Object {
      (Test-Path -LiteralPath (Join-Path $_.FullName "manifest.json")) -and
      (Test-Path -LiteralPath (Join-Path $_.FullName "albums.json")) -and
      (Test-Path -LiteralPath (Join-Path $_.FullName "errors.json"))
    } | Sort-Object LastWriteTime -Descending | Select-Object -First 10)
  if ($runs.Count -eq 0) {
    Write-Host "Nenhum run resumivel encontrado em downloads\yupoo." -ForegroundColor Red
    exit 1
  }
  Write-Host ""
  Write-Host "Runs resumiveis recentes:"
  for ($index = 0; $index -lt $runs.Count; $index++) {
    Write-Host ("[{0}] {1}" -f ($index + 1), $runs[$index].Name)
  }
  $choice = Read-LineValue "Escolha o run: "
  $parsedChoice = 0
  if (-not [int]::TryParse($choice, [ref]$parsedChoice)) {
    Write-Host "Escolha invalida." -ForegroundColor Red
    exit 1
  }
  $runIndex = $parsedChoice
  if ($runIndex -lt 1 -or $runIndex -gt $runs.Count) {
    Write-Host "Escolha invalida." -ForegroundColor Red
    exit 1
  }
  $selectedRun = $runs[$runIndex - 1].FullName
  $retryLimit = Read-LineValue "Limite de retries pendentes [20, 0 = sem limite]: "
  if ($null -eq $retryLimit) { $retryLimit = "" }
  $retryLimit = $retryLimit.Trim()
  $arguments += @("--resume-run", $selectedRun)
  if ([string]::IsNullOrWhiteSpace($retryLimit)) {
    $arguments += @("--max-retries", "20")
  }
  elseif ($retryLimit -ne "0") {
    $arguments += @("--max-retries", $retryLimit)
  }
  Write-Host ""
  Write-Host "Retomando run Yupoo..."
  Write-Host "Run: $selectedRun"
}
else {
  Write-Host ""
  Write-Host "Cole o link do Yupoo:"
  $url = Read-YupooUrl

  if ([string]::IsNullOrWhiteSpace($url)) {
    Write-Host "Erro: URL nao pode estar vazia." -ForegroundColor Red
    exit 1
  }

  $url = $url.Trim()
  if ($url -notmatch '^https?://') {
    Write-Host "Erro: URL deve comecar com http:// ou https://." -ForegroundColor Red
    exit 1
  }
  $arguments += @("--url", $url, "--max-pages", "100", "--max-albums", "10000")
  Write-Host ""
  Write-Host "Iniciando download Yupoo..."
  Write-Host "Origem: $url"
}

Write-Host ""
Write-Host "Arquivos serao salvos em: downloads\yupoo"
Write-Host ""

$pushedLocation = $false
try {
  Push-Location $backendDir
  $pushedLocation = $true
  & $python @arguments
  $exitCode = $LASTEXITCODE
}
catch [System.Management.Automation.PipelineStoppedException] {
  Write-Host ""
  Write-Host "Download interrompido. Arquivos concluidos foram preservados; use --resume pelo CLI se o run tiver manifest salvo." -ForegroundColor Yellow
  exit 130
}
catch {
  Write-Host ""
  Write-Host "Download terminou com erro: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
finally {
  if ($pushedLocation) {
    Pop-Location
  }
}

if ($exitCode -eq 0) {
  Write-Host ""
  Write-Host "Download concluido com sucesso." -ForegroundColor Green
  exit 0
}

if ($exitCode -eq 130) {
  Write-Host ""
  Write-Host "Download interrompido pelo usuario." -ForegroundColor Yellow
  exit 130
}

Write-Host ""
Write-Host "Download terminou com erro. Codigo: $exitCode" -ForegroundColor Red
exit $exitCode
