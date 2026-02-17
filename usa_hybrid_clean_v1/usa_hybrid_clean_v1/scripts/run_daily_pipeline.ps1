# =============================================
# run_daily_pipeline.ps1
# Pipeline diario con lockfile, rollback y snapshots
# =============================================
param(
  [switch]$SendTelegram,
  [switch]$AllowStale
)

$ErrorActionPreference = 'Continue'
$ROOT = (Get-Location).Path
$PY = "$ROOT\.venv\Scripts\python.exe"
$LOCKFILE = "$ROOT\tmp\pipeline.lock"
$TODAY = Get-Date -Format "yyyy-MM-dd"
$SNAPSHOT_DIR = "$ROOT\snapshots\$TODAY"

Write-Host "=== Daily Pipeline ($TODAY) ===" -ForegroundColor Cyan

# ========== LOCKFILE ==========
if (-not (Test-Path "tmp")) { New-Item -ItemType Directory -Path "tmp" -Force | Out-Null }
if (Test-Path $LOCKFILE) {
  $lockInfo = Get-Content $LOCKFILE -Raw
  Write-Host "[ERROR] Pipeline ya en ejecucion: $lockInfo" -ForegroundColor Red
  Write-Host "        Elimina el lock si es antiguo: $LOCKFILE"
  exit 1
}

try {
  "PID:$PID | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content $LOCKFILE
  Write-Host "[LOCK] Lockfile creado" -ForegroundColor Yellow

  # ========== PIPELINE ==========
  Write-Host "
[0/6] Refresh data..."
  
  $refreshArgs = @()
  if ($AllowStale) {
    $refreshArgs += "--allow-stale"
    Write-Host "[INFO] Running with --allow-stale (permite datos 1-2 días atrás)" -ForegroundColor Yellow
  }
  
  & $PY scripts/00_refresh_daily_data.py @refreshArgs
  if ($LASTEXITCODE -ne 0) { throw "Data refresh failed" }

  Write-Host "
[1/6] Inference..."
  & $PY scripts/11_infer_and_gate.py

  Write-Host "
[2/6] Trade plan..."
  & $PY scripts/40_make_trade_plan_with_tth.py

  $PLAN = "$ROOT\val\trade_plan.csv"
  $PLAN_AUDIT = "$ROOT\val\trade_plan_audit.parquet"

  Write-Host "
[3/6] Bitacora..."
  if (Test-Path $PLAN) {
    try { & $PY scripts/bitacora_excel.py --add-plan $PLAN } 
    catch { Write-Host "[WARN] Bitacora skip (Excel open?)" -ForegroundColor Yellow }
  }

  Write-Host "
[4/6] Health checks..."
  & $PY scripts/41_daily_health_checks.py
  $healthCode = $LASTEXITCODE
  $HEALTH_REPORT = "reports\health\daily_health_$TODAY.json"

  Write-Host "
[5/6] Validation..."
  $validLog = "tmp\validation_$TODAY.log"
  $validArgs = @()
  if ($AllowStale) {
    $validArgs += "--allow-stale"
  }
  & $PY scripts/test_forward_looking.py @validArgs | Tee-Object -FilePath $validLog
  $validCode = $LASTEXITCODE

  # ========== ROLLBACK CHECK ==========
  $shouldRollback = $false
  if ($validCode -ne 0) {
    Write-Host "
[ERROR] Validation FAILED" -ForegroundColor Red
    $shouldRollback = $true
  }

  if ($shouldRollback) {
    Write-Host "[ROLLBACK] Saving invalid plan..." -ForegroundColor Yellow
    if (Test-Path $PLAN) {
      Copy-Item $PLAN "val\trade_plan_rollback.csv" -Force
      Write-Host "           Backup: val\trade_plan_rollback.csv"
    }
    throw "Pipeline aborted - validation failed"
  }

  Write-Host "
[OK] All validations passed" -ForegroundColor Green

  # ========== SNAPSHOT ==========
  Write-Host "
[6/6] Creating snapshot..."
  if (-not (Test-Path $SNAPSHOT_DIR)) { 
    New-Item -ItemType Directory -Path $SNAPSHOT_DIR -Force | Out-Null 
  }

  if (Test-Path $PLAN) { Copy-Item $PLAN "$SNAPSHOT_DIR\trade_plan.csv" -Force }
  if (Test-Path $PLAN_AUDIT) { Copy-Item $PLAN_AUDIT "$SNAPSHOT_DIR\trade_plan_audit.parquet" -Force }
  if (Test-Path "data\daily\signals_with_gates.parquet") {
    Copy-Item "data\daily\signals_with_gates.parquet" "$SNAPSHOT_DIR\signals_with_gates.parquet" -Force
  }
  if (Test-Path $HEALTH_REPORT) { Copy-Item $HEALTH_REPORT "$SNAPSHOT_DIR\health.json" -Force }
  if (Test-Path $validLog) { Copy-Item $validLog "$SNAPSHOT_DIR\validation.log" -Force }

  $count = (Get-ChildItem $SNAPSHOT_DIR -ErrorAction SilentlyContinue).Count
  Write-Host "[SNAPSHOT] $count files saved to: $SNAPSHOT_DIR" -ForegroundColor Cyan

  # ========== TELEGRAM ==========
  if ($SendTelegram -and (Test-Path $PLAN)) {
    if (Test-Path "scripts\34_send_trade_plan_to_telegram.py") {
      Write-Host "
[TELEGRAM] Sending..." -ForegroundColor Green
      & $PY scripts\34_send_trade_plan_to_telegram.py --plan $PLAN
    }
  }

  Write-Host "
========================================"
  Write-Host "Pipeline COMPLETED" -ForegroundColor Green
  Write-Host "Snapshot: $SNAPSHOT_DIR"
  Write-Host "========================================
"

} catch {
  Write-Host "
[FATAL] $_" -ForegroundColor Red
  exit 1
} finally {
  if (Test-Path $LOCKFILE) {
    Remove-Item $LOCKFILE -Force
    Write-Host "[UNLOCK] Lock removed" -ForegroundColor Yellow
  }
}
