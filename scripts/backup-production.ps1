param(
  [string]$BackupRoot = "backups",
  [string]$ComposeFile = "compose.prod.yaml",
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail($Message) {
  throw $Message
}

function Read-EnvFile($Path) {
  $values = @{}
  if (!(Test-Path -LiteralPath $Path)) { return $values }
  foreach ($line in Get-Content -LiteralPath $Path) {
    if ($line -match "^\s*#" -or $line -notmatch "=") { continue }
    $parts = $line -split "=", 2
    $key = $parts[0].Trim()
    if (!$key) { continue }
    $values[$key] = $parts[1].Trim()
  }
  return $values
}

function Set-ComposeEnvironment($Values) {
  $dbName = if ($Values.ContainsKey("POSTGRES_DB") -and $Values.POSTGRES_DB) { $Values.POSTGRES_DB } else { "dripzone" }
  $dbUser = if ($Values.ContainsKey("POSTGRES_USER") -and $Values.POSTGRES_USER) { $Values.POSTGRES_USER } else { "dripzone" }
  if (!$Values.ContainsKey("POSTGRES_PASSWORD") -or !$Values.POSTGRES_PASSWORD) { Fail "POSTGRES_PASSWORD ausente no ambiente ou $EnvFile." }
  if (!$env:DATABASE_URL -and (!$Values.ContainsKey("DATABASE_URL") -or !$Values.DATABASE_URL)) {
    $encodedPassword = [uri]::EscapeDataString($Values.POSTGRES_PASSWORD)
    $env:DATABASE_URL = "postgresql+psycopg://${dbUser}:${encodedPassword}@postgres:5432/${dbName}"
  }
  if (!$env:SESSION_SECRET_KEY -and (!$Values.ContainsKey("SESSION_SECRET_KEY") -or !$Values.SESSION_SECRET_KEY)) {
    $env:SESSION_SECRET_KEY = "backup-script-placeholder-with-more-than-32-chars"
  }
  if (!$env:CORS_ORIGINS -and (!$Values.ContainsKey("CORS_ORIGINS") -or !$Values.CORS_ORIGINS)) {
    $env:CORS_ORIGINS = "https://dripzone.invalid"
  }
  return @{ DbName = $dbName; DbUser = $dbUser }
}

function Invoke-Checked($Command, $Arguments) {
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) { Fail "Comando falhou: $Command $($Arguments -join ' ')" }
}

function Get-FileSha256($Path) {
  (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-RelativePath($Base, $Path) {
  [IO.Path]::GetRelativePath((Resolve-Path -LiteralPath $Base).Path, (Resolve-Path -LiteralPath $Path).Path).Replace("\", "/")
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$envValues = Read-EnvFile $EnvFile
$dbConfig = Set-ComposeEnvironment $envValues
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$backupDir = Join-Path $BackupRoot $timestamp
$workDir = Join-Path $backupDir "_work"
$filesRoot = Join-Path $workDir "files"
$databaseDump = Join-Path $backupDir "database.dump"
$filesZip = Join-Path $backupDir "files.zip"
$manifestPath = Join-Path $backupDir "manifest.json"
$checksumsPath = Join-Path $backupDir "checksums.sha256"

try {
  if (Test-Path -LiteralPath $backupDir) { Fail "Diretorio de backup ja existe: $backupDir" }
  New-Item -ItemType Directory -Path $filesRoot -Force | Out-Null

  $compose = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile)
  $postgresVersion = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select version();")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel consultar versao do PostgreSQL." }

  $alembicVersion = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select version_num from alembic_version limit 1;")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel consultar Alembic." }

  $productCount = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select count(*) from products;")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel contar produtos." }

  $productStatusRaw = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select status || '=' || count(*) from products group by status order by status;")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel contar produtos por status." }

  $productVisibilityRaw = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select visibility || '=' || count(*) from products group by visibility order by visibility;")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel contar produtos por visibilidade." }

  $publishedCount = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select count(*) from products where status = 'published';")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel contar produtos publicados." }

  $dbCountsRaw = (& docker @($compose + @("exec", "-T", "postgres", "psql", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-At", "-c", "select 'products=' || count(*) from products union all select 'product_images=' || count(*) from product_images union all select 'brands=' || count(*) from brands union all select 'categories=' || count(*) from categories union all select 'import_records=' || count(*) from import_records union all select 'import_items=' || count(*) from import_items union all select 'import_images=' || count(*) from import_images order by 1;")))
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel coletar contagens do banco." }

  $containerDump = "/tmp/dripzone-backup-$timestamp.dump"
  Invoke-Checked "docker" @($compose + @("exec", "-T", "postgres", "pg_dump", "-U", $dbConfig.DbUser, "-d", $dbConfig.DbName, "-Fc", "-f", $containerDump))
  $postgresContainer = (& docker @($compose + @("ps", "-q", "postgres"))).Trim()
  if (!$postgresContainer) { Fail "Container postgres nao encontrado." }
  Invoke-Checked "docker" @("cp", "${postgresContainer}:$containerDump", $databaseDump)
  Invoke-Checked "docker" @($compose + @("exec", "-T", "postgres", "rm", "-f", $containerDump))
  if (!(Test-Path -LiteralPath $databaseDump) -or (Get-Item -LiteralPath $databaseDump).Length -le 0) { Fail "database.dump vazio ou ausente." }

  $backendContainer = (& docker @($compose + @("ps", "-q", "backend"))).Trim()
  if (!$backendContainer) { Fail "Container backend nao encontrado." }

  Invoke-Checked "docker" @("cp", "${backendContainer}:/app/storage/uploads", (Join-Path $filesRoot "uploads"))
  Invoke-Checked "docker" @("cp", "${backendContainer}:/app/public-data/products.json", (Join-Path $filesRoot "products.json"))

  $productsJson = Join-Path $filesRoot "products.json"
  if (!(Test-Path -LiteralPath $productsJson)) { Fail "products.json nao foi copiado." }
  if ((Get-Item -LiteralPath $productsJson).Length -le 0) { Fail "products.json esta vazio em bytes." }

  Compress-Archive -Path (Join-Path $filesRoot "*") -DestinationPath $filesZip -CompressionLevel Optimal
  if (!(Test-Path -LiteralPath $filesZip) -or (Get-Item -LiteralPath $filesZip).Length -le 0) { Fail "files.zip vazio ou ausente." }

  $uploadFiles = @(Get-ChildItem -LiteralPath (Join-Path $filesRoot "uploads") -File -Recurse -ErrorAction SilentlyContinue)
  $uploadBytes = ($uploadFiles | Measure-Object -Property Length -Sum).Sum
  if ($null -eq $uploadBytes) { $uploadBytes = 0 }

  $databaseHash = Get-FileSha256 $databaseDump
  $filesHash = Get-FileSha256 $filesZip
  $productsHash = Get-FileSha256 $productsJson
  $gitCommit = (& git rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0) { $gitCommit = $null }

  $artifactChecksums = @(
    "$databaseHash  database.dump",
    "$filesHash  files.zip",
    "$productsHash  files/products.json"
  )
  $artifactChecksums | Set-Content -LiteralPath $checksumsPath -Encoding utf8

  $manifest = [ordered]@{
    format = "dripzone-backup-v1"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    source_environment = "production"
    database = [ordered]@{
      service = "postgres"
      logical_name = $dbConfig.DbName
      user = $dbConfig.DbUser
      postgres_version = ($postgresVersion -join "`n")
      alembic_version = ($alembicVersion -join "`n")
      product_count = [int]($productCount | Select-Object -First 1)
      product_status_counts = $productStatusRaw
      product_visibility_counts = $productVisibilityRaw
      published_count = [int]($publishedCount | Select-Object -First 1)
      counts = $dbCountsRaw
      dump_file = "database.dump"
      dump_size_bytes = (Get-Item -LiteralPath $databaseDump).Length
      dump_sha256 = $databaseHash
    }
    files = [ordered]@{
      archive = "files.zip"
      archive_size_bytes = (Get-Item -LiteralPath $filesZip).Length
      archive_sha256 = $filesHash
      uploads_file_count = $uploadFiles.Count
      uploads_size_bytes = [int64]$uploadBytes
      products_json_path = "files/products.json"
      products_json_size_bytes = (Get-Item -LiteralPath $productsJson).Length
      products_json_sha256 = $productsHash
    }
    git = [ordered]@{
      commit = $gitCommit
      dirty_allowed = $true
    }
    excludes = @(".env", "backend/.env", "node_modules", "backend/.venv", "logs", "caches", "backups")
  }
  $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
  if ((Get-Item -LiteralPath $manifestPath).Length -le 0) { Fail "manifest.json vazio." }

  Remove-Item -LiteralPath $workDir -Recurse -Force
  Write-Host "Backup criado: $backupDir"
  Write-Host "database.dump sha256: $databaseHash"
  Write-Host "files.zip sha256: $filesHash"
  Write-Host "products.json sha256: $productsHash"
} catch {
  if (Test-Path -LiteralPath $backupDir) {
    Remove-Item -LiteralPath $backupDir -Recurse -Force
  }
  Write-Error $_
  exit 1
}
