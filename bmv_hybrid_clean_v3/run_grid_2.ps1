Param(
  [Parameter(Mandatory=$true)]
  [string]$Month,
  [Parameter(Mandatory=$true)]
  [string]$ModelPath,
  [Parameter(Mandatory=$true)]
  [string]$ProbModelPath,
  [Parameter(Mandatory=$true)]
  [int]$HorizonDays,
  [double[]]$AbsY_ThrList = @(0.025,0.03,0.035,0.04),
  [string[]]$Prob_ThrList = @("none","0.55","0.60"),
  [double[]]$TP_List = @(0.03,0.05),
  [double[]]$SL_List = @(0.015,0.02),
  [int]$ForceTopN = 0
)

$ErrorActionPreference = "Stop"

# Python
$PythonExe = "python"
$venvPy = ".\.venv\Scripts\python.exe"
if (Test-Path $venvPy) { $PythonExe = $venvPy }

function RunPy {
  param([string[]]$ArgsArray, [string]$StepName)
  & $PythonExe $ArgsArray
  if ($LASTEXITCODE -ne 0) { throw "Fallo en $StepName (exit=$LASTEXITCODE)" }
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path $Path)) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
}

function Format-Pct([double]$x) {
  return [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.000}", $x)
}

Write-Host "============================================================"
Write-Host "GRID Runner para $Month  |  Modelo=$ModelPath  H=$HorizonDays"
Write-Host "============================================================"

$DATA_DAILY_DIR = "data\daily"
$REPORT_BASE    = "reports\forecast"
$REPORT_MONTH   = Join-Path $REPORT_BASE $Month
Ensure-Dir $DATA_DAILY_DIR
Ensure-Dir $REPORT_BASE
Ensure-Dir $REPORT_MONTH

$OHLCV_CSV      = Join-Path $DATA_DAILY_DIR "ohlcv_daily.csv"
$LATEST_FEATS   = Join-Path $REPORT_BASE "latest_forecast_features.csv"
$LABELED_CSV    = Join-Path $REPORT_MONTH "features_labeled.csv"

# Paso 0
Write-Host "Paso 0 - Descargando OHLCV (yfinance)..."
if (-not (Test-Path $OHLCV_CSV)) {
  $fetch = ".\scripts\fetch_ohlcv_daily.py"
  if (Test-Path $fetch) {
    RunPy @($fetch, "--out-csv", $OHLCV_CSV) "fetch_ohlcv_daily.py"
  } else {
    Write-Warning "No existe $fetch. Asegúrate de tener $OHLCV_CSV listo."
  }
}
$rows = (Get-Content $OHLCV_CSV | Measure-Object -Line).Lines
Write-Host "✅ OHLCV existente: $OHLCV_CSV (rows=$rows)"
Write-Host "OK: OHLCV guardado en $OHLCV_CSV"

# Paso 1 (opcionales, si existen)
Write-Host "Paso 1 - Construyendo targets y (opcional) evaluando..."
$labelScript = ".\scripts\label_targets.py"
if (Test-Path $labelScript) {
  Ensure-Dir (Split-Path $LABELED_CSV -Parent)
  try {
    RunPy @($labelScript, "--features-csv", $LATEST_FEATS, "--prices-csv", $OHLCV_CSV, "--out-labeled", $LABELED_CSV) "label_targets.py"
    Write-Host "OK: Labeled en $LABELED_CSV"
  } catch {
    Write-Warning $_.Exception.Message
    Write-Host "OK: Labeled en $LABELED_CSV (si se generó); si no, se usará $LATEST_FEATS."
  }
} else {
  Write-Warning "No se encontró $labelScript — se usará $LATEST_FEATS directamente."
}

Write-Host "Paso 1.5 - Enriqueciendo features con ret_20d_vol..."
$volScript = ".\scripts\add_ret20_vol.py"
if (Test-Path $volScript) {
  try {
    RunPy @($volScript, "--features-in", $LABELED_CSV, "--prices-csv", $OHLCV_CSV) "add_ret20_vol.py"
  } catch { Write-Warning $_.Exception.Message }
} else {
  Write-Warning "No se encontró $volScript — se omite este enriquecimiento."
}

Write-Host "Paso 1.6 - Añadiendo tp/sl/rrr_abs a features..."
$tpslScript = ".\scripts\add_tp_sl_rrr_abs.py"
if (Test-Path $tpslScript) {
  try {
    RunPy @($tpslScript, "--features-csv", $LABELED_CSV, "--tp-pct", "0.08", "--sl-pct", "0.02") "add_tp_sl_rrr_abs.py"
  } catch { Write-Warning $_.Exception.Message }
} else {
  Write-Warning "No se encontró $tpslScript — se omite este enriquecimiento."
}

# Elegir de dónde leer features para la inferencia
$FeaturesForInfer = if (Test-Path $LABELED_CSV) { $LABELED_CSV } else { $LATEST_FEATS }
Write-Host "→ Usando features: $FeaturesForInfer"

# Paso 2 - Grid
Write-Host "Paso 2 - Ejecutando grid de inferencia + simulación..."
$inferScript = ".\scripts\infer_and_gate.py"
$simScript   = ".\scripts\simulate_tp_sl.py"

foreach ($thrAbs in $AbsY_ThrList) {
  foreach ($pThr in $Prob_ThrList) {

    $pTag = if ($pThr -eq "none") { "None" } else { $pThr }
    $forecastCsv = Join-Path $REPORT_MONTH ("forecast_{0}_thr_{1}_p{2}.csv" -f $Month, (Format-Pct $thrAbs), $pTag)

    if (-not (Test-Path $inferScript)) {
      Write-Error "No se encontró $inferScript. No puedo continuar con la inferencia."
      break
    }

    # ⚠️ Flags corregidos según el usage real del script
    $inferArgs = @(
      $inferScript,
      "--features-csv", $FeaturesForInfer,
      "--out-csv",      $forecastCsv,
      "--model",        $ModelPath
    )
    if ($ProbModelPath) { $inferArgs += @("--prob-model", $ProbModelPath) }
    if ($thrAbs -ne $null) { $inferArgs += @("--min-abs-y", (Format-Pct $thrAbs)) }
    if ($ForceTopN -gt 0) { $inferArgs += @("--force-top-n", "$ForceTopN") }
    if ($pThr -ne "none") { $inferArgs += @("--min-prob", $pThr) }

    try {
      RunPy -ArgsArray $inferArgs -StepName "infer_and_gate.py (thr_abs=$thrAbs, p=$pThr)"
      Write-Host "{`"outfile`": `"$forecastCsv`"}"
    } catch {
      Write-Warning $_.Exception.Message
      continue
    }

    if (-not (Test-Path $simScript)) {
      Write-Warning "No se encontró $simScript — salto simulación, pero ya tienes las señales en $forecastCsv."
      continue
    }

    foreach ($tp in $TP_List) {
      foreach ($sl in $SL_List) {
        $suffix = ("thr_{0}_p{1}_tp{2}_sl{3}" -f (Format-Pct $thrAbs), $pTag, (Format-Pct $tp), (Format-Pct $sl))

        $simArgs = @(
          $simScript,
          "--month",           $Month,
          "--signals-csv",     $forecastCsv,
          "--capital-initial", "10000",
          "--fixed-cash",      "2000",
          "--tp-pct",          (Format-Pct $tp),
          "--sl-pct",          (Format-Pct $sl),
          "--horizon-days",    "$HorizonDays",
          "--out-suffix",      $suffix
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
