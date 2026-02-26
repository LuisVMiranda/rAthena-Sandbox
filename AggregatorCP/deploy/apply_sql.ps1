param(
  [string]$DbHost = $env:DB_HOST,
  [string]$DbPort = $env:DB_PORT,
  [string]$DbUser = $env:DB_USER,
  [string]$DbPass = $env:DB_PASS,
  [string]$DbName = $env:DB_NAME,
  [string]$MysqlBin = $env:MYSQL_BIN,
  [ValidateSet('auto','fresh','migrate')]
  [string]$Mode = 'auto',
  [ValidateSet('auto','en','pt')]
  [string]$Lang = 'auto',
  [switch]$ApplyTools,
  [switch]$SkipTools,
  [switch]$NoPrompt,
  [string]$EmitSql = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$runner = Join-Path $root 'deploy/apply_sql.py'
if (-not (Test-Path $runner)) { throw "Missing Python SQL runner: $runner" }

if (-not $DbHost) { $DbHost = '127.0.0.1' }
if (-not $DbPort) { $DbPort = '3306' }
if (-not $DbUser) { $DbUser = 'rathena' }
if (-not $DbName) { $DbName = 'ragnarok' }
if ($MysqlBin) {
  Write-Host "Note: -MysqlBin is kept for backward compatibility and is ignored by the Python migrator."
}

$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonCmd = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonCmd = 'python'
} else {
  throw 'Python was not found in PATH. Install Python 3 and ensure py/python command is available.'
}

$args = @($runner, '--db-host', $DbHost, '--db-port', $DbPort, '--db-user', $DbUser, '--db-name', $DbName, '--mode', $Mode, '--lang', $Lang)
if ($DbPass) { $args += @('--db-pass', $DbPass) }
if ($ApplyTools -and $SkipTools) { throw 'Use only one of -ApplyTools or -SkipTools.' }
if ($ApplyTools) { $args += '--apply-tools' }
if ($SkipTools) { $args += '--skip-tools' }
if ($NoPrompt) { $args += '--no-prompt' }
if ($EmitSql) { $args += @('--emit-sql', $EmitSql) }

Write-Host "Running Python migrator with mode=$Mode lang=$Lang applyTools=$($ApplyTools.IsPresent)"
& $pythonCmd @args
if ($LASTEXITCODE -ne 0) {
  throw "SQL migration failed (python exit code: $LASTEXITCODE)."
}
