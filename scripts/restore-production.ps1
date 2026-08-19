param(
  [Parameter(Mandatory = $true)]
  [string]$BackupPath,
  [string]$RestoreRoot = "backups/_restore-validation",
  [string]$ContainerName = "",
  [string]$PostgresImage = "postgres:17-alpine",
  [switch]$Isolated,
  [switch]$AllowNonIsolated
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail($Message) {
  throw $Message
}

function Get-FileSha256($Path) {
  (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Invoke-Checked($Command, $Arguments) {
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) { Fail "Comando falhou: $Command $($Arguments -join ' ')" }
}

function Assert-Artifact($Path, $ExpectedHash) {
  if (!(Test-Path -LiteralPath $Path)) { Fail "Arquivo ausente: $Path" }
  if ((Get-Item -LiteralPath $Path).Length -le 0) { Fail "Arquivo vazio: $Path" }
  $actual = Get-FileSha256 $Path
  if ($actual -ne $ExpectedHash.ToLowerInvariant()) {
    Fail "Checksum invalido para $Path. Esperado $ExpectedHash, obtido $actual."
  }
}

function Read-Checksums($Path) {
  $checksums = @{}
  foreach ($line in Get-Content -LiteralPath $Path) {
    if (!$line.Trim()) { continue }
    if ($line -notmatch "^([a-fA-F0-9]{64})\s+(.+)$") { Fail "Linha invalida em checksums.sha256: $line" }
    $checksums[$matches[2].Trim()] = $matches[1].ToLowerInvariant()
  }
  return $checksums
}

function Assert-ChecksumEntry($Checksums, $Name, $ExpectedHash) {
  if (!$Checksums.ContainsKey($Name)) { Fail "Checksum ausente para $Name." }
  if ($Checksums[$Name] -ne $ExpectedHash.ToLowerInvariant()) {
    Fail "Checksum de $Name diverge do manifesto."
  }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

try {
  $backupDir = (Resolve-Path -LiteralPath $BackupPath).Path
  $manifestPath = Join-Path $backupDir "manifest.json"
  $checksumsPath = Join-Path $backupDir "checksums.sha256"
  $databaseDump = Join-Path $backupDir "database.dump"
  $filesZip = Join-Path $backupDir "files.zip"
  if (!(Test-Path -LiteralPath $manifestPath)) { Fail "manifest.json ausente." }
  if (!(Test-Path -LiteralPath $checksumsPath)) { Fail "checksums.sha256 ausente." }
  $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
  if ($manifest.format -ne "dripzone-backup-v1") { Fail "Formato de manifesto invalido." }
  $checksums = Read-Checksums $checksumsPath
  Assert-ChecksumEntry $checksums "database.dump" $manifest.database.dump_sha256
  Assert-ChecksumEntry $checksums "files.zip" $manifest.files.archive_sha256
  Assert-ChecksumEntry $checksums $manifest.files.products_json_path $manifest.files.products_json_sha256

  Assert-Artifact $databaseDump $manifest.database.dump_sha256
  Assert-Artifact $filesZip $manifest.files.archive_sha256

  if (!$Isolated -and !$AllowNonIsolated) {
    Fail "Restauracao nao isolada recusada. Use -Isolated para validacao ou -AllowNonIsolated para destino planejado."
  }

  $restoreDir = Join-Path $RestoreRoot ((Split-Path -Leaf $backupDir) + "-restore")
  if (Test-Path -LiteralPath $restoreDir) { Fail "Diretorio de restauracao ja existe: $restoreDir" }
  New-Item -ItemType Directory -Path $restoreDir -Force | Out-Null
  $filesRestore = Join-Path $restoreDir "files"
  New-Item -ItemType Directory -Path $filesRestore -Force | Out-Null
  Expand-Archive -LiteralPath $filesZip -DestinationPath $filesRestore -Force
  $restoredProducts = Join-Path $filesRestore "products.json"
  Assert-Artifact $restoredProducts $manifest.files.products_json_sha256

  $uploadFiles = @(Get-ChildItem -LiteralPath (Join-Path $filesRestore "uploads") -File -Recurse -ErrorAction SilentlyContinue)
  if ($uploadFiles.Count -ne [int]$manifest.files.uploads_file_count) {
    Fail "Quantidade de uploads divergente. Esperado $($manifest.files.uploads_file_count), obtido $($uploadFiles.Count)."
  }

  if (!$ContainerName) {
    $safeName = (Split-Path -Leaf $backupDir).ToLowerInvariant() -replace "[^a-z0-9-]", "-"
    $ContainerName = "dripzone-restore-$safeName"
  }
  $dbName = $manifest.database.logical_name
  $dbUser = $manifest.database.user
  $dbPassword = "restore_validation_password"
  $existing = (& docker ps -a --filter "name=^/${ContainerName}$" --format "{{.Names}}")
  if ($existing) { Fail "Container temporario ja existe: $ContainerName" }

  Invoke-Checked "docker" @("run", "-d", "--name", $ContainerName, "-e", "POSTGRES_DB=$dbName", "-e", "POSTGRES_USER=$dbUser", "-e", "POSTGRES_PASSWORD=$dbPassword", $PostgresImage)
  $started = $false
  for ($i = 0; $i -lt 30; $i++) {
    & docker exec $ContainerName pg_isready -U $dbUser -d $dbName *> $null
    if ($LASTEXITCODE -eq 0) { $started = $true; break }
    Start-Sleep -Seconds 1
  }
  if (!$started) { Fail "PostgreSQL temporario nao ficou pronto." }

  Invoke-Checked "docker" @("cp", $databaseDump, "${ContainerName}:/tmp/database.dump")
  Invoke-Checked "docker" @("exec", "-e", "PGPASSWORD=$dbPassword", $ContainerName, "pg_restore", "-U", $dbUser, "-d", $dbName, "--clean", "--if-exists", "/tmp/database.dump")

  $validationSql = "select 'products=' || count(*) from products union all select 'product_images=' || count(*) from product_images union all select 'brands=' || count(*) from brands union all select 'categories=' || count(*) from categories union all select 'import_records=' || count(*) from import_records union all select 'import_items=' || count(*) from import_items union all select 'import_images=' || count(*) from import_images order by 1; select 'status:' || status || '=' || count(*) from products group by status order by status; select 'visibility:' || visibility || '=' || count(*) from products group by visibility order by visibility; select 'published=' || count(*) from products where status = 'published'; select p.id || '|' || p.slug || '|' || p.status || '|' || p.visibility || '|' || p.price::text from products p order by p.id; select version_num from alembic_version limit 1;"
  $validation = (& docker exec -e "PGPASSWORD=$dbPassword" $ContainerName psql -U $dbUser -d $dbName -At -c $validationSql)
  if ($LASTEXITCODE -ne 0) { Fail "Validacao SQL do banco restaurado falhou." }
  $validation | Set-Content -LiteralPath (Join-Path $restoreDir "database-validation.txt") -Encoding utf8

  $result = [ordered]@{
    restored_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    backup = $backupDir
    restore_dir = $restoreDir
    isolated = [bool]$Isolated
    container = $ContainerName
    products_json_sha256 = Get-FileSha256 $restoredProducts
    uploads_file_count = $uploadFiles.Count
    database_validation_file = "database-validation.txt"
  }
  $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $restoreDir "restore-result.json") -Encoding utf8
  Write-Host "Restauracao isolada concluida: $restoreDir"
  Write-Host "Container temporario: $ContainerName"
} catch {
  Write-Error $_
  exit 1
}
