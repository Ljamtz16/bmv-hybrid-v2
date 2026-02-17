# =============================================
# 8. run_pipeline_usa.ps1
# =============================================
param(
  [string]$Month = "2025-10",
  [ValidateSet('rotation','master','file','expanded')]
  [string]$Universe = 'rotation',
  [string]$TickersFile = '',
  [switch]$AutoTune
  , [switch]$SkipDownload
)
$ROOT = (Get-Location).Path
$PY = "$ROOT\.venv\Scripts\python.exe"
### Run metadata (timestamp + flags)
$RUN_ID = (Get-Date).ToString("yyyyMMdd_HHmmss")
$FALLBACK_USED = $false
$MONTH_DIR = "reports/forecast/$Month"
Write-Host "=== PIPELINE USA Hybrid Clean ==="
Write-Host "Usando Python: $PY"
if ($Universe -eq 'file' -and -not $TickersFile) {
  Write-Host "--Universe=file requiere --TickersFile"
  exit 1
}
if (-not $SkipDownload) {
  if ($Universe -eq 'file' -and -not $TickersFile) {
    Write-Host "--Universe=file requiere --TickersFile"
    exit 1
  }
  if ($Universe -eq 'expanded') {
    $EXP_OUT = "data/us/tickers_expanded.csv"
    & $PY scripts/19_build_ticker_universe.py --out $EXP_OUT --max-count 20
    & $PY scripts/download_us_prices.py --universe file --tickers-file $EXP_OUT
  } elseif ($Universe -eq 'file') {
    & $PY scripts/download_us_prices.py --universe file --tickers-file $TickersFile
  } elseif ($Universe -eq 'master') {
    & $PY scripts/download_us_prices.py --universe master
  } else {
    & $PY scripts/download_us_prices.py --universe rotation
  }
} else {
  Write-Host "[skip] Saltando descarga de precios; usando data/us/ohlcv_us_daily.csv existente"
}
& $PY scripts/make_targets_and_eval.py
& $PY scripts/train_models.py
if ($Universe -eq 'expanded') {
  & $PY scripts/infer_and_gate.py --month $Month --tickers-file "data/us/tickers_expanded.csv"
} elseif ($Universe -eq 'file' -and $TickersFile) {
  & $PY scripts/infer_and_gate.py --month $Month --tickers-file $TickersFile
} else {
  & $PY scripts/infer_and_gate.py --month $Month
}
& $PY scripts/simulate_montecarlo.py --month $Month
& $PY scripts/executor_mc_v2.py --month $Month
& $PY scripts/wf_plan.py --train-end-jan 2024-12 --train-end-forward $Month

# === Policy resolve (Base + Mensual) ===
& $PY scripts/32_policy_manager.py --month $Month --out "$MONTH_DIR/Policy_Resolved.json"
$POL_PATH = "$MONTH_DIR/Policy_Resolved.json"
$POL = Get-Content $POL_PATH | ConvertFrom-Json
$GATE = [double]$POL.gate_threshold

# === Guardrails: capital y concurrencia ===
$CAPITAL_CAP = 1000.0
$MAX_OPEN = [int]$POL.max_open
if ($MAX_OPEN -lt 2) { Write-Host "[guardrail] max_open <$($MAX_OPEN) → 2" -ForegroundColor Yellow; $MAX_OPEN = 2 }
if ($MAX_OPEN -gt 5) { Write-Host "[guardrail] max_open >$($MAX_OPEN) → 5" -ForegroundColor Yellow; $MAX_OPEN = 5 }
$SIM_MAXOPEN = $MAX_OPEN
$SIM_CASH = [double]$POL.per_trade_cash
if (($SIM_CASH * $SIM_MAXOPEN) -gt $CAPITAL_CAP) {
  $SIM_CASH = [math]::Floor($CAPITAL_CAP / $SIM_MAXOPEN)
  Write-Host "[guardrail] Ajuste per_trade_cash → $SIM_CASH para no exceder ${CAPITAL_CAP}" -ForegroundColor Yellow
}

# === Pattern Layer ===
Write-Host "=== (Patterns) Detectando patrones ==="
& $PY scripts/20_detect_patterns.py --input "data/us/ohlcv_us_daily.csv" --outdir "reports/patterns"

Write-Host "=== (Patterns) Memoria adaptativa (opcional) ==="
if (Test-Path "reports/trades_history.csv") {
  & $PY scripts/23_pattern_memory.py --trades "reports/trades_history.csv" --outdir "reports/patterns"
} else {
  Write-Host "No se encontró reports/trades_history.csv, se omite memoria de patrones"
}

Write-Host "=== (Patterns) Features de patrones ==="
& $PY scripts/21_pattern_features.py --patterns_dir "reports/patterns" --features_in "features_labeled.csv" --features_out "features_labeled_with_patterns.csv" --pattern_memory "reports/patterns/pattern_memory.json"

Write-Host "=== (Patterns) Merge forecast + patrones ==="
& $PY scripts/22_merge_patterns_with_forecast.py --month $Month --forecast_dir "reports/forecast" --features_with_patterns "features_labeled_with_patterns.csv" --pattern_memory "reports/patterns/pattern_memory.json" --gate_threshold $GATE

Write-Host "=== (Simulación) Usando forecast_with_patterns.csv (global) ==="
# Autotune opcional de umbrales (trade count 8-15)
$MIN_PROB = [double]$POL.min_prob
$MIN_ABS = [double]$POL.min_abs_yhat
if ($AutoTune) {
  Write-Host "=== Autotune de umbrales (min_prob, min_abs_yhat) ==="
  $FORECAST_MERGED = "$MONTH_DIR/forecast_with_patterns.csv"
  & $PY scripts/26_autotune_trade_count.py --month $Month --forecast $FORECAST_MERGED --target_low 10 --target_high 15 --gate-threshold $GATE --gate-grid "0.56,0.57,0.58" --horizon-days $POL.horizon_days --max-open $SIM_MAXOPEN --cooldown-days $POL.cooldown_days --out-choice "reports/forecast/$Month/autotune_choice.json" --write-policy --policy-dir "policies/monthly"
  $CHOICE_JSON = "reports/forecast/$Month/autotune_choice.json"
  if (Test-Path $CHOICE_JSON) {
    $choice = Get-Content $CHOICE_JSON | ConvertFrom-Json
    if ($choice -and $choice.best) {
      Write-Host ("[autotune] min_prob=" + $choice.best.min_prob + " min_abs_yhat=" + $choice.best.min_abs_yhat + " signals=" + $choice.best.signals)
    }
    # Re-resolver política tras escribir mensual
    & $PY scripts/32_policy_manager.py --month $Month --out "reports/forecast/$Month/Policy_Resolved.json"
    $POL = Get-Content $POL_PATH | ConvertFrom-Json
    $MIN_PROB = [double]$POL.min_prob
    $MIN_ABS  = [double]$POL.min_abs_yhat
  }
}

# Simulador con modo position-active (global) bajo guardrails
& $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out "simulate_results_all.csv" --position-active --max-open $SIM_MAXOPEN --cooldown-days $POL.cooldown_days --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1

Write-Host "=== Archivos generados ==="
Get-ChildItem -Path ("reports/forecast/" + $Month) | Select-Object Name,Length,LastWriteTime
Write-Host "=== Simulación sectorial y comparación de KPIs ==="
$SECTORS = @("tech","financials","energy","defensive")
foreach ($SEC in $SECTORS) {
  $TICKFILE = "data/us/tickers_${SEC}.csv"
  if (Test-Path $TICKFILE) {
    Write-Host "Simulando sector $SEC..."
  & $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --tickers $TICKFILE --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out ("simulate_results_sector_" + $SEC + ".csv") --position-active --max-open 4 --cooldown-days 0 --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1
  }
}
Write-Host "Comparando KPIs sectoriales..."
& $PY scripts/compare_sector_kpis.py --month $Month

Write-Host "=== Optimizando pesos sectoriales ==="
$KPI_SECT = "reports\forecast\$Month\kpi_compare_sectors.csv"
if (Test-Path $KPI_SECT) {
  & $PY scripts/26_sector_optimizer.py --month $Month --input $KPI_SECT --metric net_pnl_sum --floor 0.05 --cap 0.70 --out-json "reports\forecast\$Month\policy_sector_weights.json"
  Write-Host "Pesos sectoriales optimizados guardados"
}

Write-Host "=== Uniendo simulate_results*.csv (dedupe) ==="
$ANY_SIM = Get-ChildItem -Path ("reports/forecast/" + $Month) -Filter "simulate_results*.csv" -ErrorAction SilentlyContinue
if ($ANY_SIM) {
  & $PY scripts/28_merge_simulate_results.py --month $Month --in-dir "reports/forecast" --out-dir "reports/forecast"
} else {
  Write-Host "No se encontraron simulate_results*.csv para unir"
}

# Merge sector results (if sector files were produced)
& $PY scripts/31_merge_sector_results.py --month $Month --dir "reports/forecast"

# Calcular métricas de actividad (únicos post-merge) y actualizar KPI
& $PY scripts/31_trade_activity_metrics.py --month $Month --dir "reports/forecast" --update-kpi

# === Relajar gate_threshold a 0.55 solo si trades únicos < 6 ===
$ACT_FILE = "reports/forecast/$Month/activity_metrics.json"
$uniq_lt6 = $false
if (Test-Path $ACT_FILE) {
  try { $act0 = Get-Content $ACT_FILE | ConvertFrom-Json; if ([int]$act0.unique_trades_executed -lt 6) { $uniq_lt6 = $true } } catch { $uniq_lt6 = $false }
}
if ($uniq_lt6) {
  Write-Host "[relax] UniqueTrades < 6 en $Month → gate_threshold=0.55 y re-simulación" -ForegroundColor Yellow
  $MONTHLY_DIR = "policies/monthly"; New-Item -ItemType Directory -Force -Path $MONTHLY_DIR | Out-Null
  $POL_MONTH_FILE = Join-Path $MONTHLY_DIR ("Policy_" + $Month + ".json")
  $MAX_OPEN_F = [int]$POL.max_open; if ($MAX_OPEN_F -lt 2) { $MAX_OPEN_F = 2 } ; if ($MAX_OPEN_F -gt 5) { $MAX_OPEN_F = 5 }
  $PER_TRADE_F = [math]::Floor($CAPITAL_CAP / $MAX_OPEN_F)
  # Actualizar (merge) el policy mensual existente para preservar otros overrides
  if (Test-Path $POL_MONTH_FILE) {
    try { $monthlyObj = Get-Content $POL_MONTH_FILE | ConvertFrom-Json } catch { $monthlyObj = $null }
  } else { $monthlyObj = $null }
  if (-not $monthlyObj) { $monthlyObj = [pscustomobject]@{} }
  $monthlyObj | Add-Member -NotePropertyName month -NotePropertyValue $Month -Force
  $monthlyObj | Add-Member -NotePropertyName gate_threshold -NotePropertyValue 0.55 -Force
  $monthlyObj | Add-Member -NotePropertyName min_prob -NotePropertyValue $MIN_PROB -Force
  $monthlyObj | Add-Member -NotePropertyName min_abs_yhat -NotePropertyValue $MIN_ABS -Force
  $monthlyObj | Add-Member -NotePropertyName max_open -NotePropertyValue $MAX_OPEN_F -Force
  $monthlyObj | Add-Member -NotePropertyName per_trade_cash -NotePropertyValue $PER_TRADE_F -Force
  $monthlyObj | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $POL_MONTH_FILE
  & $PY scripts/32_policy_manager.py --month $Month --out "$MONTH_DIR/Policy_Resolved.json"
  $POL = Get-Content $POL_PATH | ConvertFrom-Json
  $GATE = [double]$POL.gate_threshold
  & $PY scripts/22_merge_patterns_with_forecast.py --month $Month --forecast_dir "reports/forecast" --features_with_patterns "features_labeled_with_patterns.csv" --pattern_memory "reports/patterns/pattern_memory.json" --gate_threshold $GATE
  # Re-sim global y sectores con mismos thresholds MIN_PROB/MIN_ABS
  & $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out "simulate_results_all.csv" --position-active --max-open $SIM_MAXOPEN --cooldown-days $POL.cooldown_days --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1
  foreach ($SEC in $SECTORS) {
    $TICKFILE = "data/us/tickers_${SEC}.csv"
    if (Test-Path $TICKFILE) {
      & $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --tickers $TICKFILE --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out ("simulate_results_sector_" + $SEC + ".csv") --position-active --max-open 4 --cooldown-days 0 --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1
    }
  }
  & $PY scripts/compare_sector_kpis.py --month $Month
  & $PY scripts/31_merge_sector_results.py --month $Month --dir "reports/forecast"
  & $PY scripts/31_trade_activity_metrics.py --month $Month --dir "reports/forecast" --update-kpi
}

Write-Host "Pipeline completado."

# Loguear trades totales del mes (objetivo 10-15)
if (Test-Path ("reports/forecast/" + $Month + "/simulate_results_all.csv")) {
  $simCount = (Import-Csv ("reports/forecast/" + $Month + "/simulate_results_all.csv")).Count
  Write-Host ("Trades en " + $Month + ": " + $simCount + " (objetivo 10-15)")
}

# (9/9) Generar detalle y duración de trades si existe simulate_results.csv
$SIM_FILE = "reports/forecast/$Month/simulate_results.csv"
if (Test-Path $SIM_FILE) {
  Write-Host "=== Generando detalle y duración de trades ==="
  & $PY scripts/27_trades_durations.py --month $Month --in-dir "reports/forecast" --out-dir "reports/forecast"
  Write-Host "=== Validación intradía de TP/SL (15m) ==="
  & $PY scripts/30_validate_intraday_hits.py --month $Month --dir "reports/forecast" --intraday-dir "data/us/intraday" --interval 15m --lookahead-days 5
  Write-Host "=== Enriqueciendo trades con validación intradía ==="
  & $PY scripts/31_merge_trades_intraday.py --month $Month --dir "reports/forecast"
} else {
  Write-Host "No existe $SIM_FILE, se omite cálculo de duración de trades"
}

# === Fallback automático si trades reales < 10 y se usó -AutoTune ===
if ($AutoTune) {
  # Medir actividad por trades únicos ejecutados (post-merge)
  $ACT_FILE = "reports/forecast/$Month/activity_metrics.json"
  $uniq = -1
  if (Test-Path $ACT_FILE) {
    try { $act = Get-Content $ACT_FILE | ConvertFrom-Json; $uniq = [int]$act.unique_trades_executed } catch { $uniq = -1 }
  } else {
    # fallback: computar en vivo desde simulate_results_all.csv
    $SIM_ALL_PATH = "reports/forecast/$Month/simulate_results_all.csv"
    if (Test-Path $SIM_ALL_PATH) {
      try {
        $keys = (Import-Csv $SIM_ALL_PATH | ForEach-Object { $_.ticker + '|' + $_.entry_date })
        $uniq = ($keys | Sort-Object -Unique | Measure-Object).Count
      } catch { $uniq = -1 }
    }
  }
  if ($uniq -ge 0 -and $uniq -lt 10) {
      $FALLBACK_USED = $true
      Write-Host "[fallback] UniqueTrades=$uniq < 10 en $Month. Re-simulando con thresholds forzados y guardrails..." -ForegroundColor Yellow
      # Escribir/actualizar política mensual relajada (forzada)
      $MONTHLY_DIR = "policies/monthly"
      New-Item -ItemType Directory -Force -Path $MONTHLY_DIR | Out-Null
      $POL_MONTH_FILE = Join-Path $MONTHLY_DIR ("Policy_" + $Month + ".json")
      # Calcular sizing bajo guardrails
      $MAX_OPEN_F = [int]$POL.max_open
      if ($MAX_OPEN_F -lt 2) { $MAX_OPEN_F = 2 }
      if ($MAX_OPEN_F -gt 5) { $MAX_OPEN_F = 5 }
      $PER_TRADE_F = [math]::Floor($CAPITAL_CAP / $MAX_OPEN_F)
      # Relajar también el gate para ampliar candidatos (merge con existing policy mensual)
      if (Test-Path $POL_MONTH_FILE) {
        try { $monthlyObj = Get-Content $POL_MONTH_FILE | ConvertFrom-Json } catch { $monthlyObj = $null }
      } else { $monthlyObj = $null }
      if (-not $monthlyObj) { $monthlyObj = [pscustomobject]@{} }
      $monthlyObj | Add-Member -NotePropertyName month -NotePropertyValue $Month -Force
      $monthlyObj | Add-Member -NotePropertyName min_prob -NotePropertyValue 0.54 -Force
      $monthlyObj | Add-Member -NotePropertyName min_abs_yhat -NotePropertyValue 0.05 -Force
      $monthlyObj | Add-Member -NotePropertyName gate_threshold -NotePropertyValue 0.54 -Force
      $monthlyObj | Add-Member -NotePropertyName max_open -NotePropertyValue $MAX_OPEN_F -Force
      $monthlyObj | Add-Member -NotePropertyName per_trade_cash -NotePropertyValue $PER_TRADE_F -Force
      $monthlyObj | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $POL_MONTH_FILE
      # Re-resolver política y tomar nuevos umbrales
      & $PY scripts/32_policy_manager.py --month $Month --out "$MONTH_DIR/Policy_Resolved.json"
      $POL = Get-Content $POL_PATH | ConvertFrom-Json
      $MIN_PROB = [double]$POL.min_prob
      $MIN_ABS  = [double]$POL.min_abs_yhat
  $GATE = [double]$POL.gate_threshold
  # Re-construir forecast_with_patterns con gate potencialmente relajado
  & $PY scripts/22_merge_patterns_with_forecast.py --month $Month --forecast_dir "reports/forecast" --features_with_patterns "features_labeled_with_patterns.csv" --pattern_memory "reports/patterns/pattern_memory.json" --gate_threshold $GATE
      # Guardrails post-resolve
      $SIM_MAXOPEN = [int]$POL.max_open
      if ($SIM_MAXOPEN -lt 2) { $SIM_MAXOPEN = 2 }
      if ($SIM_MAXOPEN -gt 5) { $SIM_MAXOPEN = 5 }
      $SIM_CASH = [double]$POL.per_trade_cash
      if (($SIM_CASH * $SIM_MAXOPEN) -gt $CAPITAL_CAP) { $SIM_CASH = [math]::Floor($CAPITAL_CAP / $SIM_MAXOPEN) }
      # Re-simulación global con thresholds forzados
  & $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out "simulate_results_all.csv" --position-active --max-open $SIM_MAXOPEN --cooldown-days $POL.cooldown_days --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1
      # Re-simulación sectorial con thresholds relajados
      $SECTORS = @("tech","financials","energy","defensive")
      foreach ($SEC in $SECTORS) {
        $TICKFILE = "data/us/tickers_${SEC}.csv"
        if (Test-Path $TICKFILE) {
          Write-Host "[fallback] Re-simulando sector $SEC..."
          & $PY scripts/24_simulate_trading.py --month $Month --forecast_dir "reports/forecast" --source-file "forecast_with_patterns.csv" --tickers $TICKFILE --min-prob $MIN_PROB --min-abs-yhat $MIN_ABS --per-trade-cash $SIM_CASH --simulate-results-out ("simulate_results_sector_" + $SEC + ".csv") --position-active --max-open 4 --cooldown-days 0 --lock-same-ticker --sort-signals-by prob_win --horizon-dynamic-atr --horizon-days-high-atr 2 --allow-reentry-after-tp --rebalance-every-days 10 --rebalance-close-k 1
        }
      }
      Write-Host "[fallback] Recalculando KPIs sectoriales y merge final..."
      & $PY scripts/compare_sector_kpis.py --month $Month
      & $PY scripts/31_merge_sector_results.py --month $Month --dir "reports/forecast"
      # Actualizar KPI/trade count tras fallback
      Write-Host "[fallback] Re-simulación completada."
      # Recalcular métricas de actividad y reportar
      & $PY scripts/31_trade_activity_metrics.py --month $Month --dir "reports/forecast" --update-kpi
      if (Test-Path $ACT_FILE) {
        try { $act2 = Get-Content $ACT_FILE | ConvertFrom-Json; $uniq2 = [int]$act2.unique_trades_executed } catch { $uniq2 = -1 }
        if ($uniq2 -ge 0) { Write-Host ("[fallback] UniqueTrades en " + $Month + ": " + $uniq2 + " (objetivo 10-15)") }
      }
    }
}

# === Snapshot de ejecución con marca de tiempo ===
try {
  New-Item -ItemType Directory -Force -Path (Join-Path $MONTH_DIR "history") | Out-Null
  $RUN_DIR = Join-Path $MONTH_DIR ("history/run_" + $RUN_ID)
  New-Item -ItemType Directory -Force -Path $RUN_DIR | Out-Null
  # Conteo de trades finales
  $finalTrades = 0
  $finalSimFile = Join-Path $MONTH_DIR "simulate_results_all.csv"
  if (Test-Path $finalSimFile) { $finalTrades = (Import-Csv $finalSimFile).Count }
  # Guardar metadatos de la corrida
  $meta = @{
    run_id = $RUN_ID
    month = $Month
    autotune = [bool]$AutoTune
    fallback_used = [bool]$FALLBACK_USED
    thresholds = @{ min_prob = $MIN_PROB; min_abs_yhat = $MIN_ABS }
    per_trade_cash = [double]$POL.per_trade_cash
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    final_trades = $finalTrades
  }
  $meta | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $RUN_DIR "run_metadata.json")
  # Copiar todos los archivos del mes (nivel superior) al folder de la corrida
  Get-ChildItem -Path $MONTH_DIR -File | Copy-Item -Destination $RUN_DIR -Force
  # Crear copias con sufijo _RUNID en el mismo folder para los archivos clave
  $stampPatterns = @(
    "simulate_results*.csv",
    "kpi*.json",
    "kpi_compare_sectors.csv",
    "simulate_results_merged.csv",
    "Policy_Resolved.json",
    "autotune_choice.json",
    "policy_sector_weights.json",
    "trades_detailed.csv",
    "forecast_with_patterns.csv"
  )
  foreach ($pat in $stampPatterns) {
    Get-ChildItem -Path $MONTH_DIR -Filter $pat -File -ErrorAction SilentlyContinue | ForEach-Object {
      $dst = Join-Path $MONTH_DIR ("$($_.BaseName)_$RUN_ID$($_.Extension)")
      Copy-Item -Path $_.FullName -Destination $dst -Force
    }
  }
  Write-Host ("[snapshot] Archivos de la corrida guardados en: " + $RUN_DIR)
} catch {
  Write-Host "[snapshot] Error al guardar snapshot de la corrida: $_" -ForegroundColor Yellow
}

# === Agregarización de snapshots (per-month y global) ===
try {
  & $PY scripts/34_aggregate_run_history.py --months $Month
} catch {
  Write-Host "[runs] Error al agregarizar snapshots: $_" -ForegroundColor Yellow
}
