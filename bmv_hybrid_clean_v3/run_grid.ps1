Param(
  # === Parámetros principales ===
  [Parameter(Mandatory=$true)] [string]$Month,                # ej: 2025-10
  [string]$ModelPath = "models\return_model_H3.joblib",
  [string]$ProbModelPath = "models\prob_win_clean.joblib",    # si no quieres probas, pásalo vacío: ""
  [int]$HorizonDays = 3,                                      # 3 para H3, 5 para H5

  # Rutas estándar (deja por defecto salvo que tengas otra estructura)
  [string]$FeaturesCsv = "reports\forecast\latest_forecast_features.csv",
  [string]$LabeledCsv  = "",                                  # si vacío, se usa reports\forecast\<Month>\features_labeled.csv
  [string]$PricesCsv   = "data\daily\ohlcv_daily.csv",

  # === Barridos (grids) ===
  [double[]]$AbsY_ThrList = @(0.025, 0.03, 0.035, 0.04),      # umbrales |y_hat|
  [string[]]$Prob_ThrList = @("none","0.55","0.60"),          # "none" = sin filtro probas
  [double[]]$TP_List = @(0.03, 0.05),                          # take profit %
  [double[]]$SL_List = @(0.015, 0.02),                         # stop loss %
  [int]$ForceTopN = 0,                                        # >0 para forzar top-N por |y_hat|

  # === Opcionales ===
  [switch]$SkipDownload,                                      # omite descarga OHLCV
  [switch]$SkipVol,                                           # omite cálculo ret_20d_vol
  [switch]$SkipTpSl,                                          # omite tp/sl/rrr_abs en features
  [string]$PythonExe = "python"
)

# ----------------- utilidades -----------------
function Write-Title($msg) {
  Write-Host ""
  Write-Host ("=" * 60)
  Write-Host $msg -ForegroundColor Cyan
  Write-Host ("=" * 60)
}

function Invoke-Step {
  param([string]$Cmd, [string]$FailMessage)
  & $PythonExe -c "import sys;print('')" | Out-Null  # 'wake' del py launcher en algunos entornos
  try {
    iex $Cmd
    if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
  } catch {
    Write-Warning "$FailMessage -> $_"
  }
}

# ----------------- paths y carpetas -----------------
$monthDir = Join-Path "reports\forecast" $Month
if (![System.IO.Directory]::Exists($monthDir)) { [System.IO.Directory]::CreateDirectory($monthDir) | Out-Null }

if ([string]::IsNullOrWhiteSpace($LabeledCsv)) {
  $LabeledCsv = Join-Path $monthDir "features_labeled.csv"
}

$SignalsBase = $monthDir  # aquí van todos los CSVs de señales y trades
$SummaryCsv  = Join-Path $monthDir ("grid_summary_{0}.csv" -f $Month)

Write-Title ("GRID Runner para {0}  |  Modelo={1}  H={2}" -f $Month,$ModelPath,$HorizonDays)

# ----------------- Paso 0: OHLCV (opcional) -----------------
if (-not $SkipDownload) {
  Write-Host "Paso 0 - Descargando OHLCV (yfinance)..." -ForegroundColor Yellow
  $dlCmd = "$PythonExe .\scripts\download_daily_prices.py --features-csv `"$FeaturesCsv`" --out-csv `"$PricesCsv`""
  Invoke-Expression $dlCmd
  if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: OHLCV guardado en $PricesCsv"
  } else {
    Write-Warning "Descarga OHLCV terminó con fallos (continuo de todas formas)."
  }
}

# ----------------- Paso 1: Labeled + evaluación rápida -----------------
Write-Host "Paso 1 - Construyendo targets y (opcional) evaluando..." -ForegroundColor Yellow
$evalCmd = @"
$PythonExe .\scripts\make_targets_and_eval.py `
  --features-csv `"$FeaturesCsv`" `
  --prices-csv `"$PricesCsv`" `
  --out-labeled `"$LabeledCsv`"
"@
Invoke-Expression $evalCmd
if ($LASTEXITCODE -ne 0) {
  Write-Warning "make_targets_and_eval.py devolvió error; continuo (revisar features/paths)."
} else {
  Write-Host "OK: Labeled en $LabeledCsv"
}

# ----------------- Paso 1.5: ret_20d_vol (opcional) -----------------
if (-not $SkipVol) {
  Write-Host "Paso 1.5 - Enriqueciendo features con ret_20d_vol..." -ForegroundColor Yellow
  $volCmd = @"
$PythonExe .\scripts\make_ret20d_vol.py `
  --features-in `"$LabeledCsv`" `
  --prices-csv  `"$PricesCsv`"
"@
  Invoke-Expression $volCmd
}

# ----------------- Paso 1.6: tp/sl/rrr_abs (opcional, para prob-model/sim) -----------------
if (-not $SkipTpSl) {
  Write-Host "Paso 1.6 - Añadiendo tp/sl/rrr_abs a features..." -ForegroundColor Yellow
  # usa 0.08/0.02 como default; cambia si quieres otros
  $tpslCmd = @"
$PythonExe .\scripts\add_tp_sl_rrr.py `
  --features-csv `"$LabeledCsv`" `
  --tp-pct 0.08 --sl-pct 0.02
"@
  Invoke-Expression $tpslCmd
}

# ----------------- Paso 2: GRID -----------------
Write-Host "Paso 2 - Ejecutando grid de inferencia + simulación..." -ForegroundColor Yellow

$results = @()

foreach ($thr in $AbsY_ThrList) {

  foreach ($pThr in $Prob_ThrList) {

    # --- construir nombre de salida para señales ---
    $probTag = if ($pThr -eq "none") { "pNone" } else { "p$("{0:N2}" -f [double]$pThr)" }
    $topTag  = if ($ForceTopN -gt 0) { "_top$ForceTopN" } else { "" }
    $sigName = "forecast_{0}_thr_{1}_{2}{3}.csv" -f $Month, ("{0:N3}" -f $thr), $probTag, $topTag
    $sigPath = Join-Path $SignalsBase $sigName

    # --- inferencia ---
    $inferCmd = "$PythonExe .\scripts\infer_and_gate.py --features-csv `"$LabeledCsv`" --out-csv `"$sigPath`" --model `"$ModelPath`" --min-abs-y $thr"
    if (-not [string]::IsNullOrWhiteSpace($ProbModelPath) -and ($pThr -ne "none")) {
      $inferCmd += " --prob-model `"$ProbModelPath`" --min-prob $pThr"
    }
    if ($ForceTopN -gt 0) { $inferCmd += " --force-top-n $ForceTopN" }

    Invoke-Expression $inferCmd
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "Inferencia falló para thr=$thr prob=$pThr"
      continue
    }

    # --- simulación (para cada TP/SL) ---
    foreach ($tp in $TP_List) {
      foreach ($sl in $SL_List) {
        $suffix = "thr_$("{0:N3}" -f $thr)_$probTag`_tp$("{0:N3}" -f $tp)_sl$("{0:N3}" -f $sl)$topTag"
        $simCmd = @"
$PythonExe .\scripts\simulate_trading.py `
  --month `"$Month`" `
  --signals-csv `"$sigPath`" `
  --capital-initial 10000 --fixed-cash 2000 `
  --tp-pct $tp --sl-pct $sl --horizon-days $HorizonDays `
  --out-suffix `"$suffix`"
"@
        $json = ""
        try {
          $json = Invoke-Expression $simCmd | Out-String
        } catch {
          Write-Warning "Simulación falló [$suffix] -> $_"
          continue
        }

        # Intenta extraer el último bloque de JSON del output (sim imprime un dict al final)
        $lineJson = ($json -split "`n" | Where-Object { $_ -match "^{.*}$" } | Select-Object -Last 1)
        if (-not [string]::IsNullOrWhiteSpace($lineJson)) {
          try {
            $obj = $lineJson | ConvertFrom-Json
            $results += [PSCustomObject]@{
              month          = $Month
              model          = $ModelPath
              horizon_days   = $HorizonDays
              thr_abs_y      = [double]$thr
              prob_thr       = $pThr
              tp_pct         = [double]$tp
              sl_pct         = [double]$sl
              force_top_n    = $ForceTopN
              rows           = $obj.rows
              capital_init   = $obj.capital_initial
              capital_final  = $obj.capital_final
              gross_pnl      = $obj.gross_pnl
              trades_csv     = $obj.trades_csv
              signals_csv    = $sigPath
            }
          } catch {
            Write-Warning "No pude parsear JSON de simulación [$suffix]"
          }
        } else {
          Write-Warning "No se encontró JSON de simulación [$suffix]"
        }

      } # SL
    } # TP

  } # prob threshold
} # abs y thr

# ----------------- Paso 3: Guardar resumen -----------------
if ($results.Count -gt 0) {
  $results | Sort-Object -Property @{Expression="gross_pnl";Descending=$true} |
    Export-Csv -Path $SummaryCsv -NoTypeInformation -Encoding UTF8
  Write-Host ""
  Write-Host "Resumen guardado en: $SummaryCsv" -ForegroundColor Green

  # Top 5 por PnL en consola
  Write-Host "`nTop 5 combinaciones por PnL:" -ForegroundColor Green
  $results | Sort-Object -Property @{Expression="gross_pnl";Descending=$true} |
    Select-Object -First 5 month,thr_abs_y,prob_thr,tp_pct,sl_pct,force_top_n,gross_pnl,rows,signals_csv |
    Format-Table -AutoSize
} else {
  Write-Warning "No se generaron resultados de simulación."
}

Write-Host "`nLISTO."
