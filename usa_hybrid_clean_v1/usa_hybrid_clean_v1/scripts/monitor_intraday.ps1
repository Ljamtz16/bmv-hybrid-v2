param(
  [string]$Month = (Get-Date -Format 'yyyy-MM'),
  [string]$Interval = '15m',
  [int]$LoopSeconds = 300,
  [int]$LookaheadDays = 5,
  [switch]$OnlyOnce
)

# Paths
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logPath = Join-Path $ROOT 'data/trading/predictions_log.csv'
$dailyPath = Join-Path $ROOT 'data/us/ohlcv_us_daily.csv'
$forecastDir = Join-Path $ROOT ("reports/forecast/" + $Month)
$planPath = Join-Path $forecastDir 'trade_plan_tth.csv'
$mergedIntraday = Join-Path $ROOT 'data/us/intraday/_merged_live.csv'

function Get-TickersToWatch {
  $tickers = @()
  if (Test-Path $planPath) {
    try {
      $p = Import-Csv $planPath
      $tickers += ($p | Select-Object -ExpandProperty ticker)
    } catch {}
  }
  if (Test-Path $logPath) {
    try {
      $r = Import-Csv $logPath | Where-Object { $_.status -eq 'OPEN' }
      $tickers += ($r | Select-Object -ExpandProperty ticker)
    } catch {}
  }
  $tickers | Where-Object { $_ -and $_.Trim() -ne '' } | Sort-Object -Unique
}

function Build-IntradayMerge([string[]]$tickers) {
  if (-not $tickers -or $tickers.Count -eq 0) { return }
  $start = (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
  $end = (Get-Date).AddDays($LookaheadDays).ToString('yyyy-MM-dd')
  $tk = ($tickers -join ',')
  Write-Host "[monitor] Intraday $Interval $start->$end ($($tickers.Count) tickers)"
  python (Join-Path $ROOT 'scripts/29b_build_intraday_merge.py') --tickers $tk --start $start --end $end --interval $Interval --out $mergedIntraday | Out-Host
}

function Run-Notifier {
  param([bool]$HasIntraday)
  $args = @(
    (Join-Path $ROOT 'scripts/35_check_predictions_and_notify.py'),
    '--log', $logPath,
    '--daily', $dailyPath,
    '--notify', 'TP_SL_ONLY'
  )
  if ($HasIntraday) {
    $args += @('--intraday', $mergedIntraday)
  }
  Write-Host "[monitor] Notifier: python $($args -join ' ')"
  python @args | Out-Host
}

Write-Host "[monitor] Live monitor iniciado para $Month (interval=$Interval, loop=$LoopSeconds s)"

while ($true) {
  try {
    $tickers = Get-TickersToWatch
    if ($tickers.Count -gt 0) {
      Build-IntradayMerge -tickers $tickers
      $hasRows = $false
      if (Test-Path $mergedIntraday) {
        try { $hasRows = ((Import-Csv $mergedIntraday).Count -gt 0) } catch { $hasRows = $false }
      }
      Run-Notifier -HasIntraday:$hasRows
    } else {
      Write-Host "[monitor] Sin tickers a vigilar (plan/log vacíos)."
    }
  } catch {
    Write-Warning $_
  }

  if ($OnlyOnce) { break }
  Start-Sleep -Seconds $LoopSeconds
}
