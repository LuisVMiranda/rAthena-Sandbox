param(
  [Parameter(Mandatory = $true)][string]$RathenaTree,
  [string]$InstallSubdir = 'tools/traveler-companion'
)

$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$targetTree = (Resolve-Path $RathenaTree).Path
$destRoot = Join-Path $targetTree $InstallSubdir

New-Item -ItemType Directory -Force -Path $destRoot | Out-Null

$items = @('companion-service','bridge-service','sql-files','docs','deploy','README.md')
foreach ($item in $items) {
  $src = Join-Path $sourceRoot $item
  $dst = Join-Path $destRoot $item
  if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
  Copy-Item -Recurse -Force $src $dst
}

Write-Host "TravelerCompanion modules copied to: $destRoot"
Write-Host "Next steps:"
Write-Host "  1) Run $destRoot/deploy/apply_sql.ps1 with DB_* env vars."
Write-Host "  2) Start companion-service (and bridge-service if needed) from $destRoot."
Write-Host "  3) Open the web panel at http://127.0.0.1:4310 after service startup."
