# Script: run_trade_plan.ps1
# Wrapper de nivel superior para generar trade plan desde parquet/CSV
# Uso: .\run_trade_plan.ps1 -Forecast signals_with_gates.parquet -Prices ohlcv_daily.parquet -Out val/trade_plan.csv

param(
    [Parameter(Mandatory=$true)]
    [string]$Forecast,
    
    [Parameter(Mandatory=$true)]
    [string]$Prices,
    
    [Parameter(Mandatory=$true)]
    [string]$Out,
    
    [string]$Month = "2026-01",
    
    [double]$Capital = 100000,
    [int]$MaxOpen = 15,
    [double]$TpPct = 0.10,
    [double]$SlPct = 0.02,
    [string]$AsofDate = $null,
    [string]$AuditFile = $null,
    [switch]$DryRun
)

$env:PYTHONIOENCODING = 'utf-8'

$cmd = @(
    "python", "scripts/run_trade_plan.py",
    "--forecast", $Forecast,
    "--prices", $Prices,
    "--out", $Out,
    "--month", $Month,
    "--capital", $Capital,
    "--max-open", $MaxOpen,
    "--tp-pct", $TpPct,
    "--sl-pct", $SlPct
)

if ($AsofDate) {
    $cmd += @("--asof-date", $AsofDate)
}

if ($AuditFile) {
    $cmd += @("--audit-file", $AuditFile)
}

if ($DryRun) {
    $cmd += "--dry-run"
}

Write-Host "════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "RUN TRADE PLAN (Wrapper)" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Forecast: $Forecast" -ForegroundColor Green
Write-Host "Prices:   $Prices" -ForegroundColor Green
Write-Host "Output:   $Out" -ForegroundColor Green
Write-Host "Month:    $Month | Capital: $Capital | Max-Open: $MaxOpen" -ForegroundColor Green
if ($AsofDate) { Write-Host "AsofDate: $AsofDate" -ForegroundColor Green }
if ($DryRun) { Write-Host "MODE: DRY-RUN (no executará 33_make_trade_plan.py)" -ForegroundColor Yellow }
Write-Host ""

# Convertir array a lista de argumentos para Invoke-Expression
$cmdStr = ($cmd | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join ' '
Invoke-Expression $cmdStr
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✅ Trade plan generation completed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Trade plan generation failed (exit code: $exitCode)" -ForegroundColor Red
}

exit $exitCode
