#!/bin/bash
# rpi_health_check.sh
# Script para verificar salud del sistema RPi en producción

echo "╔════════════════════════════════════════════╗"
echo "║     BMV HYBRID - HEALTH CHECK RPi          ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅${NC} $1"
    else
        echo -e "${RED}❌${NC} $1"
    fi
}

warn_status() {
    echo -e "${YELLOW}⚠️${NC}  $1"
}

echo "1. ESPACIO EN DISCO"
echo "════════════════════"
df -h / | grep -E "^/dev|Avail"
echo ""

echo "2. MEMORIA"
echo "════════════════════"
free -h | grep -E "^Mem|^Swap"
echo ""

echo "3. TEMPERATURA CPU"
echo "════════════════════"
temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{print $1/1000}')
if [ ! -z "$temp" ]; then
    if (( $(echo "$temp > 75" | bc -l) )); then
        warn_status "Temperatura alta: ${temp}°C"
    else
        echo -e "${GREEN}✅${NC} Temperatura: ${temp}°C"
    fi
else
    warn_status "No se pudo leer temperatura"
fi
echo ""

echo "4. CONECTIVIDAD INTERNET"
echo "════════════════════"
ping -c 1 8.8.8.8 > /dev/null 2>&1
check_status "Conectividad Google DNS"
ping -c 1 query1.finance.yahoo.com > /dev/null 2>&1
check_status "Conectividad Yahoo Finance"
echo ""

echo "5. SERVICIOS SYSTEMD"
echo "════════════════════"
systemctl is-active --quiet bmv-daily-tasks.timer
check_status "Timer bmv-daily-tasks"
systemctl is-active --quiet bmv-monitor-live.timer
check_status "Timer bmv-monitor-live"
echo ""

echo "6. VENV PYTHON"
echo "════════════════════"
if [ -d "/home/$(whoami)/bmv_hybrid_clean_v3/.venv" ]; then
    check_status "Virtual Environment existe"
else
    warn_status "Virtual Environment no encontrado"
fi
echo ""

echo "7. LIBRERÍAS CRÍTICAS"
echo "════════════════════"
source .venv/bin/activate 2>/dev/null
python3 -c "import pandas" > /dev/null 2>&1
check_status "pandas"
python3 -c "import numpy" > /dev/null 2>&1
check_status "numpy"
python3 -c "import sklearn" > /dev/null 2>&1
check_status "sklearn"
python3 -c "import yfinance" > /dev/null 2>&1
check_status "yfinance"
echo ""

echo "8. DATOS"
echo "════════════════════"
data_count=$(find data/raw/1d -name "*.csv" 2>/dev/null | wc -l)
if [ $data_count -gt 0 ]; then
    echo -e "${GREEN}✅${NC} Datos 1D: $data_count archivos"
else
    warn_status "No hay datos en data/raw/1d/"
fi
echo ""

echo "9. MODELOS"
echo "════════════════════"
model_count=$(find models -name "*.joblib" 2>/dev/null | wc -l)
if [ $model_count -gt 0 ]; then
    echo -e "${GREEN}✅${NC} Modelos ML: $model_count archivos"
else
    warn_status "No hay modelos en models/"
fi
echo ""

echo "10. CONFIGURACIÓN"
echo "════════════════════"
if [ -f "config/paper.yaml" ]; then
    check_status "Archivo config/paper.yaml"
else
    warn_status "config/paper.yaml no encontrado"
fi
echo ""

echo "11. ÚLTIMAS EJECUCIONES"
echo "════════════════════"
echo "Últimas 5 líneas de logs bmv-daily-tasks:"
journalctl -u bmv-daily-tasks -n 5 --no-pager
echo ""

echo "12. PRÓXIMAS EJECUCIONES"
echo "════════════════════"
systemctl list-timers bmv-daily-tasks bmv-monitor-live --no-pager
echo ""

echo "════════════════════════════════════════════"
echo "✅ Health Check Completado"
echo "════════════════════════════════════════════"
