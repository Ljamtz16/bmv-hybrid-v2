# =============================================
# check_setup.ps1
# Script de verificación del entorno
# =============================================

Write-Host "=== USA Hybrid Clean V1 - Verificación del Sistema ===" -ForegroundColor Cyan
Write-Host ""

$allOk = $true

# 1. Verificar Python
Write-Host "[1/7] Verificando Python..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    if ($pyVersion -match "Python (\d+\.\d+\.\d+)") {
        Write-Host "  [OK] Python encontrado: $pyVersion" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] Python no encontrado" -ForegroundColor Red
        $allOk = $false
    }
} catch {
    Write-Host "  [ERROR] Error al verificar Python" -ForegroundColor Red
    $allOk = $false
}

# 2. Verificar entorno virtual
Write-Host "`n[2/7] Verificando entorno virtual..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "  [OK] Directorio .venv existe" -ForegroundColor Green
    
    # Verificar si el entorno es funcional
    $pyvenvCfg = Get-Content .venv\pyvenv.cfg -ErrorAction SilentlyContinue
    if ($pyvenvCfg) {
        $pythonHome = ($pyvenvCfg | Select-String "home = (.+)").Matches.Groups[1].Value
        if (Test-Path $pythonHome) {
            Write-Host "  [OK] Entorno virtual apunta a Python valido" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] Entorno virtual roto (Python base no existe en: $pythonHome)" -ForegroundColor Red
            Write-Host "    -> Ejecuta: Remove-Item -Recurse .venv; python -m venv .venv" -ForegroundColor Yellow
            $allOk = $false
        }
    }
} else {
    Write-Host "  [ERROR] No existe .venv" -ForegroundColor Red
    Write-Host "    -> Ejecuta: python -m venv .venv" -ForegroundColor Yellow
    $allOk = $false
}

# 3. Verificar dependencias Python
Write-Host "`n[3/7] Verificando dependencias Python..." -ForegroundColor Yellow
$requiredPackages = @("pandas", "numpy", "sklearn", "yfinance", "joblib")
$pyExe = ".venv\Scripts\python.exe"

if (Test-Path $pyExe) {
    foreach ($pkg in $requiredPackages) {
        $checkCmd = if ($pkg -eq "sklearn") { "import sklearn; print('OK')" } else { "import $pkg; print('OK')" }
        try {
            $result = & $pyExe -c $checkCmd 2>&1
            if ($result -match "OK") {
                Write-Host "  [OK] $pkg instalado" -ForegroundColor Green
            } else {
                Write-Host "  [ERROR] $pkg NO instalado" -ForegroundColor Red
                $allOk = $false
            }
        } catch {
            Write-Host "  [ERROR] $pkg NO instalado" -ForegroundColor Red
            $allOk = $false
        }
    }
    if (-not $allOk) {
        Write-Host "    -> Ejecuta: pip install -r requirements.txt" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Python del entorno virtual no encontrado" -ForegroundColor Red
    $allOk = $false
}

# 4. Verificar archivos de datos
Write-Host "`n[4/7] Verificando archivos de datos..." -ForegroundColor Yellow
$dataFiles = @(
    "data\us\tickers_master.csv",
    "data\us\tickers_tech.csv",
    "data\us\tickers_financials.csv",
    "data\us\tickers_energy.csv",
    "data\us\tickers_defensive.csv"
)

foreach ($file in $dataFiles) {
    if (Test-Path $file) {
        $rows = (Import-Csv $file -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host "  [OK] $file ($rows tickers)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $file NO existe (opcional)" -ForegroundColor Yellow
    }
}

$ohlcvFile = "data\us\ohlcv_us_daily.csv"
if (Test-Path $ohlcvFile) {
    $rows = (Import-Csv $ohlcvFile -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "  [OK] $ohlcvFile ($rows registros)" -ForegroundColor Green
} else {
    Write-Host "  [WARN] $ohlcvFile NO existe (se descargara automaticamente)" -ForegroundColor Yellow
}

# 5. Verificar modelos
Write-Host "`n[5/7] Verificando modelos ML..." -ForegroundColor Yellow
$models = @(
    "models\return_model_H3.joblib",
    "models\prob_win_clean.joblib"
)

foreach ($model in $models) {
    if (Test-Path $model) {
        $sizeKB = [math]::Round((Get-Item $model).Length / 1KB, 2)
        Write-Host "  [OK] $model ($sizeKB KB)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $model NO existe (se entrenara automaticamente)" -ForegroundColor Yellow
    }
}

# 6. Verificar políticas
Write-Host "`n[6/7] Verificando politicas..." -ForegroundColor Yellow
if (Test-Path "policies\Policy_Base.json") {
    Write-Host "  [OK] Policy_Base.json existe" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Policy_Base.json NO existe" -ForegroundColor Red
    $allOk = $false
}

$monthlyPolicies = Get-ChildItem "policies\monthly\Policy_*.json" -ErrorAction SilentlyContinue
if ($monthlyPolicies) {
    Write-Host "  [OK] $($monthlyPolicies.Count) politicas mensuales encontradas" -ForegroundColor Green
} else {
    Write-Host "  [WARN] No hay politicas mensuales (se crearan automaticamente)" -ForegroundColor Yellow
}

# 7. Verificar estructura de directorios
Write-Host "`n[7/7] Verificando estructura de directorios..." -ForegroundColor Yellow
$requiredDirs = @(
    "data\us",
    "models",
    "policies",
    "reports\forecast",
    "reports\patterns",
    "scripts"
)

foreach ($dir in $requiredDirs) {
    if (Test-Path $dir) {
        Write-Host "  [OK] $dir\" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $dir\ NO existe (se creara automaticamente)" -ForegroundColor Yellow
    }
}

# Resumen final
Write-Host "`n" + ("="*60) -ForegroundColor Cyan
if ($allOk) {
    Write-Host "[OK] SISTEMA LISTO PARA EJECUTAR" -ForegroundColor Green
    Write-Host "`nPara ejecutar el pipeline:" -ForegroundColor White
    Write-Host "  .\scripts\run_pipeline_usa.ps1 -Month '2025-10' -Universe rotation -AutoTune" -ForegroundColor Cyan
} else {
    Write-Host "[WARN] SE REQUIEREN ACCIONES CORRECTIVAS" -ForegroundColor Yellow
    Write-Host "`nPasos recomendados:" -ForegroundColor White
    Write-Host "  1. Recrear entorno virtual:" -ForegroundColor Cyan
    Write-Host "     Remove-Item -Recurse -Force .venv" -ForegroundColor Gray
    Write-Host "     python -m venv .venv" -ForegroundColor Gray
    Write-Host "     .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host "  2. Instalar dependencias:" -ForegroundColor Cyan
    Write-Host "     pip install -r requirements.txt" -ForegroundColor Gray
    Write-Host "  3. Volver a ejecutar este script" -ForegroundColor Cyan
}
Write-Host ("="*60) -ForegroundColor Cyan
