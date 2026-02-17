#!/bin/bash
################################################################################
# setup_rpi.sh
# Script de instalación automática para Raspberry Pi 4B+
# Uso: bash setup_rpi.sh
################################################################################

set -e  # Exit on error

echo "=========================================="
echo "SETUP BMV HYBRID - RASPBERRY PI 4B+"
echo "=========================================="
echo ""

# ============================================================================
# 1. Verificar/Instalar Python 3.10+
# ============================================================================
echo "[1/7] Verificando Python 3.10+..."

PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "❌ Python3 no encontrado. Instalando..."
    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip python3-dev
else
    PYTHON_VERSION=$($PYTHON_CMD --version | awk '{print $2}')
    echo "✅ Python encontrado: $PYTHON_VERSION"
fi

# ============================================================================
# 2. Crear Virtual Environment
# ============================================================================
echo ""
echo "[2/7] Creando Virtual Environment..."

if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    echo "✅ Virtual Environment creado"
else
    echo "✅ Virtual Environment ya existe"
fi

# Activar venv
source .venv/bin/activate

# ============================================================================
# 3. Instalar dependencias livianas
# ============================================================================
echo ""
echo "[3/7] Instalando dependencias (esto puede tardar ~5-10 min)..."

pip install --upgrade pip setuptools wheel

# Instalar con cache para RPi
pip install --cache-dir ~/.cache/pip -r requirements-lite.txt

echo "✅ Dependencias instaladas"

# ============================================================================
# 4. Crear estructura de directorios
# ============================================================================
echo ""
echo "[4/7] Creando estructura de directorios..."

mkdir -p data/raw/1d
mkdir -p data/raw/1h
mkdir -p data/interim
mkdir -p data/daily
mkdir -p reports/paper_trading
mkdir -p logs

echo "✅ Directorios creados"

# ============================================================================
# 5. Preparar archivo .env para Telegram (opcional)
# ============================================================================
echo ""
echo "[5/7] Configurando variables de entorno..."

if [ ! -f "scripts/.env" ]; then
    cat > scripts/.env << 'EOF'
# .env - Variables de entorno
# Telegram (opcional - para notificaciones en vivo)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Otros
PYTHONPATH=.
EOF
    echo "✅ Archivo .env creado en scripts/"
    echo "   📌 IMPORTANTE: Edita scripts/.env con tus credenciales de Telegram (opcional)"
else
    echo "✅ Archivo .env ya existe"
fi

# ============================================================================
# 6. Crear servicios systemd
# ============================================================================
echo ""
echo "[6/7] Instalando servicios systemd..."

REPO_DIR=$(pwd)
USERNAME=$(whoami)

# Service para tareas diarias (06:00)
sudo tee /etc/systemd/system/bmv-daily-tasks.service > /dev/null << EOF
[Unit]
Description=BMV Hybrid - Tareas Diarias
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USERNAME
WorkingDirectory=$REPO_DIR
Environment="PATH=$REPO_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=$REPO_DIR"
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/scripts/paper_run_daily.py --start "\$(date -d yesterday +\%Y-\%m-\%d)" --end "\$(date +\%Y-\%m-\%d)"
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bmv-daily

[Install]
WantedBy=multi-user.target
EOF

# Timer para ejecutar a las 06:00
sudo tee /etc/systemd/system/bmv-daily-tasks.timer > /dev/null << EOF
[Unit]
Description=Ejecuta tareas diarias de BMV a las 06:00
Requires=bmv-daily-tasks.service

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 06:00:00
Persistent=true
Unit=bmv-daily-tasks.service

[Install]
WantedBy=timers.target
EOF

# Service para monitoreo en vivo (9:30-16:30)
sudo tee /etc/systemd/system/bmv-monitor-live.service > /dev/null << EOF
[Unit]
Description=BMV Hybrid - Monitor en Vivo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$REPO_DIR
Environment="PATH=$REPO_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=$REPO_DIR"
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/scripts/monitor_forecast_live.py --loop --interval 300
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bmv-monitor

[Install]
WantedBy=multi-user.target
EOF

# Timer para monitoreo (9:30-16:30, solo trading days)
sudo tee /etc/systemd/system/bmv-monitor-live.timer > /dev/null << EOF
[Unit]
Description=Inicia monitoreo BMV de 9:30 a 16:30
Requires=bmv-monitor-live.service

[Timer]
OnCalendar=Mon-Fri *-*-* 09:30:00
OnCalendar=Mon-Fri *-*-* 16:30:00
Unit=bmv-monitor-live.service

[Install]
WantedBy=timers.target
EOF

# Recargar systemd
sudo systemctl daemon-reload

echo "✅ Servicios instalados:"
echo "   - bmv-daily-tasks.service (ejecuta 06:00 todos los días)"
echo "   - bmv-monitor-live.service (9:30-16:30, lunes-viernes)"

# ============================================================================
# 7. Mostrar próximos pasos
# ============================================================================
echo ""
echo "[7/7] Configuración final..."
echo ""
echo "=========================================="
echo "✅ SETUP COMPLETADO"
echo "=========================================="
echo ""
echo "📝 PRÓXIMOS PASOS:"
echo ""
echo "1️⃣  OPCIONAL - Configurar Telegram:"
echo "   nano scripts/.env"
echo "   (Agrega TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID)"
echo ""
echo "2️⃣  Copiar datos históricos desde tu desktop:"
echo "   scp -r usuario@desktop:/ruta/data/raw/1d ./data/raw/"
echo "   scp -r usuario@desktop:/ruta/models ./models/"
echo "   scp usuario@desktop:/ruta/config/paper.yaml ./config/"
echo ""
echo "3️⃣  Activar servicios:"
echo "   sudo systemctl start bmv-daily-tasks.timer"
echo "   sudo systemctl start bmv-monitor-live.timer"
echo "   sudo systemctl enable bmv-daily-tasks.timer"
echo "   sudo systemctl enable bmv-monitor-live.timer"
echo ""
echo "4️⃣  Ver logs en vivo:"
echo "   journalctl -u bmv-daily-tasks -f"
echo "   journalctl -u bmv-monitor-live -f"
echo ""
echo "5️⃣  Probar scripts manualmente:"
echo "   source .venv/bin/activate"
echo "   python scripts/01_download_data.py"
echo "   python scripts/02_build_features.py"
echo "   python scripts/04_generate_signals.py"
echo "   python scripts/paper_run_daily.py --start 2025-01-20 --end 2025-01-24"
echo ""
echo "=========================================="
echo ""
