#!/bin/bash
################################################################################
# setup_rpi.sh (MEJORADO)
# Instalación production-ready para Raspberry Pi
# - Pre-requisitos apt (evita compilar)
# - Estructura runtime separada
# - Permisos y environment centralizados
# - Health check integrado
################################################################################

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  BMV HYBRID - SETUP PRODUCTION READY (Raspberry Pi 4B+)"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ============================================================================
# CONFIG INICIAL
# ============================================================================

REPO_DIR=$(pwd)
RUNTIME_DIR="$HOME/bmv_runtime"
VENV_DIR="$REPO_DIR/.venv"
USERNAME=$(whoami)

echo "[CONFIG]"
echo "  Repo:     $REPO_DIR"
echo "  Runtime:  $RUNTIME_DIR"
echo "  Venv:     $VENV_DIR"
echo "  Usuario:  $USERNAME"
echo ""

# ============================================================================
# PASO 1: Pre-requisitos por APT (crítico para ARM)
# ============================================================================

echo "[1/8] Instalando pre-requisitos del sistema..."

sudo apt update -qq
sudo apt install -y \
    python3 python3-venv python3-pip \
    python3-dev \
    build-essential \
    libatlas-base-dev \
    libffi-dev libssl-dev \
    git rsync \
    curl wget \
    ca-certificates

echo "✅ Pre-requisitos instalados"
echo ""

# ============================================================================
# PASO 2: Virtual Environment
# ============================================================================

echo "[2/8] Preparando Virtual Environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "✅ Venv creado"
else
    echo "✅ Venv ya existe"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel
echo "✅ pip/setuptools actualizado"
echo ""

# ============================================================================
# PASO 3: Instalar dependencias (con cache para RPi)
# ============================================================================

echo "[3/8] Instalando dependencias (esto tarda ~5-10 min en RPi)..."

# Crear cache si no existe
mkdir -p ~/.cache/pip

# Instalar requirements-lite
pip install --cache-dir ~/.cache/pip -r requirements-lite.txt

echo "✅ Dependencias instaladas"
echo ""

# ============================================================================
# PASO 4: Crear estructura RUNTIME (separada del código)
# ============================================================================

echo "[4/8] Creando estructura de runtime..."

mkdir -p "$RUNTIME_DIR"/{data/raw/{1d,1h},data/interim,data/daily}
mkdir -p "$RUNTIME_DIR"/{reports/paper_trading,reports/dashboards}
mkdir -p "$RUNTIME_DIR"/{logs,state,config}
mkdir -p "$RUNTIME_DIR/models"

# Copiar modelos si no existen
if [ -d "$REPO_DIR/models" ] && [ ! -z "$(ls -A $REPO_DIR/models 2>/dev/null)" ]; then
    cp -v "$REPO_DIR/models"/*.joblib "$RUNTIME_DIR/models/" 2>/dev/null || true
    cp -v "$REPO_DIR/models"/*.json "$RUNTIME_DIR/models/" 2>/dev/null || true
fi

# Copiar config
if [ -f "$REPO_DIR/config/paper.yaml" ]; then
    cp "$REPO_DIR/config/paper.yaml" "$RUNTIME_DIR/config/"
fi

# Permisos
chmod -R u+rwx "$RUNTIME_DIR"

echo "✅ Estructura runtime creada en: $RUNTIME_DIR"
echo ""

# ============================================================================
# PASO 5: Crear runtime.env (configuración centralizada)
# ============================================================================

echo "[5/8] Creando runtime.env..."

cat > "$RUNTIME_DIR/config/runtime.env" << 'ENVEOF'
# ═══════════════════════════════════════════════════════════════
# BMV HYBRID - RUNTIME CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Rutas (CRÍTICO: todo relativo a BVM_RUNTIME)
export BVM_RUNTIME="${HOME}/bmv_runtime"
export BVM_CODE="$(cd $(dirname "${BASH_SOURCE[0]}")/../.. && pwd)"
export BVM_DATA="${BVM_RUNTIME}/data"
export BVM_REPORTS="${BVM_RUNTIME}/reports"
export BVM_LOGS="${BVM_RUNTIME}/logs"
export BVM_STATE="${BVM_RUNTIME}/state"
export BVM_CONFIG="${BVM_RUNTIME}/config"
export BVM_MODELS="${BVM_RUNTIME}/models"

# Python
export PYTHONPATH="${BVM_CODE}:${PYTHONPATH}"
export BVM_VENV="${BVM_CODE}/.venv"

# Aplicación
export MODE="paper"
export TZ="America/Mexico_City"
export DASH_PORT="5000"
export DASH_WORKERS="2"

# Datos
export TICKERS="AMXL,GAPPXL,WALMEX,TELEVISA,BIMBOA"
export DATA_SOURCE="yfinance"
export DATA_RETENTION_DAYS="90"

# Logging
export LOG_LEVEL="INFO"
export LOG_FORMAT="%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Trading
export PAPER_CAPITAL="100000"
export POSITION_LIMIT="5"
export MAX_POSITION_SIZE_PCT="5"

# Telegram (opcional)
export TELEGRAM_BOT_TOKEN=""
export TELEGRAM_CHAT_ID=""

# Sentry/Monitoring (opcional)
export SENTRY_DSN=""
ENVEOF

chmod 600 "$RUNTIME_DIR/config/runtime.env"
echo "✅ runtime.env creado (permisos 600)"
echo ""

# ============================================================================
# PASO 6: Crear systemd services
# ============================================================================

echo "[6/8] Instalando servicios systemd..."

# Service para dashboard
sudo tee /etc/systemd/system/bmv-dashboard.service > /dev/null << SERVICEEOF
[Unit]
Description=BMV Hybrid Dashboard (Flask + Gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$REPO_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$RUNTIME_DIR/config/runtime.env

ExecStart=$VENV_DIR/bin/gunicorn \
    --bind 0.0.0.0:\${DASH_PORT} \
    --workers \${DASH_WORKERS} \
    --timeout 30 \
    --access-logfile $RUNTIME_DIR/logs/dashboard.access.log \
    --error-logfile $RUNTIME_DIR/logs/dashboard.error.log \
    dashboard_app:app

Restart=always
RestartSec=10
StandardOutput=append:$RUNTIME_DIR/logs/dashboard.log
StandardError=append:$RUNTIME_DIR/logs/dashboard.err
SyslogIdentifier=bmv-dashboard

# Límites
MemoryLimit=512M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Service para tareas diarias (oneshot)
sudo tee /etc/systemd/system/bmv-daily-tasks.service > /dev/null << SERVICEEOF
[Unit]
Description=BMV Hybrid - Daily Tasks (paper trading, signals)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USERNAME
WorkingDirectory=$REPO_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$RUNTIME_DIR/config/runtime.env

# Lock para evitar doble ejecución
ExecStartPre=/bin/bash -c 'mkdir -p \${BVM_STATE} && flock -n \${BVM_STATE}/lock_daily || exit 1'
ExecStart=$VENV_DIR/bin/python scripts/paper_run_daily.py \
    --start "\$(date -d yesterday +\%Y-\%m-\%d)" \
    --end "\$(date +\%Y-\%m-\%d)"
ExecStartPost=/bin/bash -c 'echo "success" > \${BVM_STATE}/last_run.json; rm -f \${BVM_STATE}/lock_daily'
OnFailure=bmv-daily-tasks-failed.service

StandardOutput=append:$RUNTIME_DIR/logs/daily.log
StandardError=append:$RUNTIME_DIR/logs/daily.err
SyslogIdentifier=bmv-daily

TimeoutStartSec=1800
MemoryLimit=768M

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Timer para tareas diarias (06:00)
sudo tee /etc/systemd/system/bmv-daily-tasks.timer > /dev/null << SERVICEEOF
[Unit]
Description=Ejecuta tareas BMV diarias a las 06:00
Requires=bmv-daily-tasks.service

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 06:00:00
Persistent=true
OnBootSec=5min

Unit=bmv-daily-tasks.service

[Install]
WantedBy=timers.target
SERVICEEOF

# Timer para monitor en vivo (09:30-16:30)
sudo tee /etc/systemd/system/bmv-monitor-live.timer > /dev/null << SERVICEEOF
[Unit]
Description=Monitor en vivo BMV (9:30-16:30, L-V)
Requires=bmv-monitor-live.service

[Timer]
OnCalendar=Mon-Fri *-*-* 09:30:00
OnCalendar=Mon-Fri *-*-* 16:30:00
Unit=bmv-monitor-live.service

[Install]
WantedBy=timers.target
SERVICEEOF

sudo systemctl daemon-reload
echo "✅ Servicios systemd instalados"
echo ""

# ============================================================================
# PASO 7: Configurar swap (si es necesario)
# ============================================================================

echo "[7/8] Verificando swap..."

free_swap=$(free | awk '/^Swap:/ {print $4}')
if [ "$free_swap" -lt 1000000 ]; then
    echo "⚠️  Swap limitado. Recomendación:"
    echo "    sudo dphys-swapfile swapoff"
    echo "    sudo nano /etc/dphys-swapfile (cambiar CONF_SWAPSIZE=2048)"
    echo "    sudo dphys-swapfile setup && sudo dphys-swapfile swapon"
else
    echo "✅ Swap OK"
fi
echo ""

# ============================================================================
# PASO 8: Health check
# ============================================================================

echo "[8/8] Ejecutando health check..."

python validate_rpi_setup.py

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETADO"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📝 PRÓXIMOS PASOS:"
echo ""
echo "1️⃣  Configurar credenciales (opcional):"
echo "    nano $RUNTIME_DIR/config/runtime.env"
echo ""
echo "2️⃣  Activar servicios:"
echo "    sudo systemctl enable bmv-dashboard.service"
echo "    sudo systemctl enable bmv-daily-tasks.timer"
echo "    sudo systemctl enable bmv-monitor-live.timer"
echo ""
echo "3️⃣  Iniciar servicios:"
echo "    sudo systemctl start bmv-dashboard.service"
echo "    sudo systemctl start bmv-daily-tasks.timer"
echo ""
echo "4️⃣  Ver logs en vivo:"
echo "    journalctl -u bmv-dashboard -f"
echo "    journalctl -u bmv-daily-tasks -f"
echo ""
echo "5️⃣  Acceder al dashboard:"
echo "    http://localhost:5000"
echo ""
echo "════════════════════════════════════════════════════════════════"
