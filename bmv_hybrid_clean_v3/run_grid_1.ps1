Param(
  [Parameter(Mandatory=$true)]
  [string]$Month,                                 # ej. "2025-10"

  [Parameter(Mandatory=$true)]
  [string]$ModelPath,                             # ej. "models\return_model_H3.joblib"

  [Parameter(Mandatory=$true)]
  [string]$ProbModelPath,                         # ej. "models\prob_win_clean.joblib"

  [Parameter(Mandatory=$true)]
  [int]$HorizonDays,                              # ej. 3

  [double[]]$AbsY_ThrList = @(0.025,0.03,0.035,0.04),
  [string[]]$Prob_ThrList = @("none","0.55","0.60"),
  [double[]]$TP_List = @(0.03,0.05),
  [double[]]$SL_List = @(0.015,0.02),
  [int]$ForceTopN = 0
)

$ErrorActionPreference = "Stop"

# -----------------------------
# 0) Resolver intérprete Python
# -----------------------------
$PythonExe = "python"
$venvPy = ".\.venv\Scripts\python.exe"
if (Test-Path $venvPy) { $PythonExe = $venvPy }

function RunPy {
  param(
    [Parameter(Mandatory=$true)][string[]]$ArgsArray,
    [string]$StepName = "python-step"
  )
  & $PythonExe $ArgsArray
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    throw "Fallo en $StepName (exit=$code)"
  }
}

function Ensure-Dir {
  param([string]$Path)
  $dir = $Path
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}

# Formato porcentaje con 3 decimales, cultura invariante
function Format-Pct([double]$x) {
  return [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.000}", $x)
}

Write-Host "============================================================"
Write-Host "GRID Runner para $Month  |  Modelo=$ModelPath  H=$HorizonDays"
Write-Host "============================================================"

# Directorios base
$DATA_DAILY_DIR = "data\daily"
$REPORT_BASE    = "reports\forecast"
$REPORT_MONTH   = Join-Path $REPORT_BASE $Month

Ensure-Dir $DATA_DAILY_DIR
Ensure-Dir $REPORT_BASE
Ensure-Dir $REPORT_MONTH

# Rutas de archivos
$OHLCV_CSV      = Join-Path $DATA_DAILY_DIR "ohlcv_daily.csv"
$LATEST_FEATS   = Join-Path $REPORT_BASE "latest_forecast_features.csv"
$LABELED_CSV    = Join-Path $REPORT_MONTH "features_labeled.csv"

# -----------------------------
# Paso 0 - Descargar OHLCV
# -----------------------------
Write-Host "Paso 0 - Descargando OHLCV (yfinance)..."
# Si ya tienes otro script de fetch, ajústalo aquí. De lo contrario, se asume que ya existe/lo generas aparte.
if (-not (Test-Path $OHLCV_CSV)) {
  $fetchArgs = @(
    ".\scripts\fetch_ohlcv_daily.py",
    "--out-csv", $OHLCV_CSV
  )
  try {
    RunPy -ArgsArray $fetchArgs -StepName "fetch_ohlcv_daily.py"
    Write-Host "✅ OHLCV guardado en: $OHLCV_CSV"
  } catch {
    Write-Warning "No se pudo ejecutar fetch_ohlcv_daily.py. Si ya tienes $OHLCV_CSV, continuamos. Detalle: $_"
  }
} else {
  $rows = (Get-Content $OHLCV_CSV | Measure-Object -Line).Lines
  Write-Host "✅ OHLCV existente: $OHLCV_CSV (rows=$rows)"
}
Write-Host "OK: OHLCV guardado en $OHLCV_CSV"

# -----------------------------
# Paso 1 - Construir targets / labeling
# -----------------------------
Write-Host "Paso 1 - Construyendo targets y (opcional) evaluando..."
Ensure-Dir (Split-Path $LABELED_CSV -Parent)

$evalArgs = @(
  ".\scripts\label_targets.py",
  "--features-csv", $LATEST_FEATS,
  "--prices-csv",   $OHLCV_CSV,
  "--out-labeled",  $LABELED_CSV
)
try {
  RunPy -ArgsArray $evalArgs -StepName "label_targets.py"
  Write-Host "OK: Labeled en $LABELED_CSV"
} catch {
  Write-Warning $_.Exception.Message
  Write-Host   "OK: Labeled en $LABELED_CSV (continuando si el archivo fue generado)"
}

# -----------------------------
# Paso 1.5 - Añadir ret_20d_vol
# -----------------------------
Write-Host "Paso 1.5 - Enriqueciendo features con ret_20d_vol..."
$volArgs = @(
  ".\scripts\add_ret20_vol.py",
  "--features-in", $LABELED_CSV,
  "--prices-csv",  $OHLCV_CSV
)
try {
  RunPy -ArgsArray $volArgs -StepName "add_ret20_vol.py"
} catch {
  Write-Warning $_.Exception.Message
}

# -----------------------------
# Paso 1.6 - Añadir tp/sl/rrr_abs
# -----------------------------
Write-Host "Paso 1.6 - Añadiendo tp/sl/rrr_abs a features..."
$tpslArgs = @(
  ".\scripts\add_tp_sl_rrr_abs.py",
  "--features-csv", $LABELED_CSV,
  "--tp-pct", "0.08",
  "--sl-pct", "0.02"
)
try {
  RunPy -ArgsArray $tpslArgs -StepName "add_tp_sl_rrr_abs.py"
} catch {
  Write-Warning $_.Exception.Message
}

# -----------------------------
# Paso 2 - Grid: inferencia + gate + simulación
# -----------------------------
Write-Host "Paso 2 - Ejecutando grid de inferencia + simulación..."

foreach ($thrAbs in $AbsY_ThrList) {
  foreach ($pThr in $Prob_ThrList) {
    # --- 2.1 Inferir y generar señales ---
    $pTag = if ($pThr -eq "none") { "None" } else { $pThr }
    $forecastCsv = Join-Path $REPORT_MONTH ("forecast_{0}_thr_{1}_{2}.csv" -f $Month, (Format-Pct $thrAbs), ("p$($pTag)"))

    $inferArgs = @(
      ".\scripts\infer_and_gate.py",
      "--month",          $Month,
      "--model-path",     $ModelPath,
      "--prob-model-path",$ProbModelPath,
      "--features-csv",   $LABELED_CSV,
      "--abs-y-thr",      (Format-Pct $thrAbs),
      "--horizon-days",   "$HorizonDays",
      "--out-csv",        $forecastCsv
    )

    if ($ForceTopN -gt 0) {
      $inferArgs += @("--force-top-n", "$ForceTopN")
    }
    # prob-thr (opcional)
    if ($pThr -ne "none") {
      $inferArgs += @("--prob-thr", $pThr)
    } else {
      $inferArgs += @("--prob-thr", "none")
    }

    try {
      RunPy -ArgsArray $inferArgs -StepName "infer_and_gate.py (thr_abs=$thrAbs, p=$pThr)"
      Write-Host "{`"rows`": ? , `"min_abs_y`": $thrAbs, `"min_prob`": $((if ($pThr -eq "none"){"null"}else{$pThr})), `"has_prob`": true, `"outfile`": `"$forecastCsv`"}"
    } catch {
      Write-Warning $_.Exception.Message
      # Si falla la inferencia, no tiene sentido simular; pasamos al siguiente combo
      continue
    }

    # --- 2.2 Simulación para cada TP/SL ---
    foreach ($tp in $TP_List) {
      foreach ($sl in $SL_List) {
        $suffix = ("thr_{0}_p{1}_tp{2}_sl{3}" -f (Format-Pct $thrAbs), $pTag, (Format-Pct $tp), (Format-Pct $sl))

        $simArgs = @(
          ".\scripts\simulate_tp_sl.py",
          "--month",          $Month,
          "--signals-csv",    $forecastCsv,
          "--capital-initial","10000",
          "--fixed-cash",     "2000",
          "--tp-pct",         (Format-Pct $tp),
          "--sl-pct",         (Format-Pct $sl),
          "--horizon-days",   "$HorizonDays",
          "--out-suffix",     $suffix
        )

        try {
          RunPy -ArgsArray $simArgs -StepName "simulate_tp_sl.py [$suffix]"
        } catch {
          Write-Warning "Simulación falló [$suffix] -> $($_.Exception.Message)"
          continue
        }
      }
    }
  }
}

Write-Host "✅ Grid finalizado. Resultados en: $REPORT_MONTH"
