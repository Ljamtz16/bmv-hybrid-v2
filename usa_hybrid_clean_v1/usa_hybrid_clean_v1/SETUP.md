# Guía de Configuración - USA Hybrid Clean V1

## Sistema de Trading Automatizado para Mercado USA

---

## 🚀 Instalación Rápida

### 1. Recrear el Entorno Virtual

El entorno virtual actual está roto. Elimínalo y créalo de nuevo:

```powershell
# Eliminar el entorno virtual roto
Remove-Item -Recurse -Force .venv

# Crear nuevo entorno virtual con Python 3.12
python -m venv .venv

# Activar el entorno virtual
.\.venv\Scripts\Activate.ps1
```

**Nota:** Si PowerShell muestra error de permisos, ejecuta:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Instalar Dependencias

```powershell
# Actualizar pip
python -m pip install --upgrade pip

# Instalar todas las dependencias
pip install -r requirements.txt
```

### 3. Verificar Instalación

```powershell
# Verificar que los paquetes están instalados
pip list

# Verificar que Python puede importar las librerías
python -c "import pandas, numpy, sklearn, yfinance, joblib; print('✓ Todas las dependencias OK')"
```

---

## 📁 Estructura de Archivos Necesarios

### Archivos de Configuración (✓ Ya existen)
- `policies/Policy_Base.json` - Configuración base
- `policies/monthly/Policy_2025-*.json` - Políticas mensuales

### Archivos de Datos Requeridos
Asegúrate de tener estos archivos antes de ejecutar:

```
data/us/
  ├── tickers_master.csv        # Lista principal de tickers
  ├── tickers_rotation.csv      # Rotación semanal (opcional)
  ├── tickers_tech.csv          # Sector tecnología
  ├── tickers_financials.csv    # Sector financiero
  ├── tickers_energy.csv        # Sector energía
  ├── tickers_defensive.csv     # Sector defensivo
  └── ohlcv_us_daily.csv       # Precios (se descarga automáticamente)
```

### Modelos ML (✓ Ya existen)
- `models/return_model_H3.joblib`
- `models/prob_win_clean.joblib`

---

## 🎯 Primer Ejecución

### Opción 1: Pipeline Completo (Recomendado)

```powershell
# Ejecutar pipeline para octubre 2025 con autotune
.\scripts\run_pipeline_usa.ps1 -Month "2025-10" -Universe rotation -AutoTune
```

### Opción 2: Por Pasos

```powershell
# 1. Descargar precios
python scripts/download_us_prices.py --universe master

# 2. Generar features y targets
python scripts/make_targets_and_eval.py

# 3. Entrenar modelos
python scripts/train_models.py

# 4. Generar predicciones
python scripts/infer_and_gate.py --month 2025-10

# 5. Simular trading
python scripts/24_simulate_trading.py --month 2025-10 --forecast_dir reports/forecast
```

---

## 🔍 Verificación del Sistema

### Check 1: Datos Disponibles
```powershell
# Verificar archivos de tickers
Get-ChildItem data\us\tickers_*.csv | Select-Object Name, Length

# Verificar datos OHLCV
if (Test-Path data\us\ohlcv_us_daily.csv) {
    $rows = (Import-Csv data\us\ohlcv_us_daily.csv).Count
    Write-Host "✓ OHLCV: $rows registros"
} else {
    Write-Host "✗ Falta ohlcv_us_daily.csv - ejecuta download_us_prices.py"
}
```

### Check 2: Modelos Entrenados
```powershell
Get-ChildItem models\*.joblib | Select-Object Name, Length, LastWriteTime
```

### Check 3: Políticas
```powershell
Get-ChildItem policies\monthly\*.json | Select-Object Name
```

---

## 🐛 Solución de Problemas Comunes

### Error: "No module named 'sklearn'"
```powershell
pip install scikit-learn
```

### Error: "No module named 'yfinance'"
```powershell
pip install yfinance
```

### Error: Python no encuentra archivos
- Asegúrate de estar en la raíz del proyecto
- Verifica que el entorno virtual esté activado (debe aparecer `(.venv)` en el prompt)

### El pipeline falla en la descarga de datos
- Verifica conexión a internet
- Yahoo Finance puede tener límites de rate, espera unos minutos

---

## 📊 Flujo del Sistema

1. **Descarga** → `download_us_prices.py`
2. **Features** → `make_targets_and_eval.py`
3. **Training** → `train_models.py`
4. **Inferencia** → `infer_and_gate.py`
5. **Patrones** → Scripts 20-23
6. **Simulación** → `24_simulate_trading.py`
7. **Análisis** → Scripts 25-36

---

## 📈 Métricas Objetivo

El sistema está configurado para:
- **Trades mensuales:** 10-15
- **Capital máximo:** $1,000
- **Max posiciones abiertas:** 2-5
- **Cash por trade:** $200
- **Win rate objetivo:** >50%

---

## 🔐 Variables de Entorno (Opcional)

Si usas Telegram para notificaciones, crea `.env`:
```
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
```

---

## 📞 Soporte

Para más información, revisa:
- Scripts individuales (comentarios internos)
- Archivo `Policy_Base.json` para parámetros
- Reportes en `reports/forecast/` después de ejecutar

---

**Versión:** USA Hybrid Clean V1  
**Última actualización:** Noviembre 2025
