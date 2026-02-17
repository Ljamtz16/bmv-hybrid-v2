#!/bin/bash
################################################################################
# sync_to_rpi.sh
# Script para sincronizar archivos esenciales desde desktop a Raspberry Pi
# Uso: bash sync_to_rpi.sh <usuario_rpi> <ip_rpi>
# Ejemplo: bash sync_to_rpi.sh pi 192.168.1.100
################################################################################

if [ $# -lt 2 ]; then
    echo "❌ Uso: bash sync_to_rpi.sh <usuario> <ip>"
    echo "   Ejemplo: bash sync_to_rpi.sh pi 192.168.1.100"
    exit 1
fi

RPi_USER=$1
RPi_IP=$2
RPi_HOME="/home/$RPi_USER/bmv_hybrid_clean_v3"

echo "=========================================="
echo "SYNC A RASPBERRY PI"
echo "=========================================="
echo "Usuario: $RPi_USER"
echo "IP: $RPi_IP"
echo "Destino: $RPi_HOME"
echo ""

# ============================================================================
# Sincronizar archivos esenciales
# ============================================================================

echo "[1/5] Sincronizando configuración..."
rsync -avz --delete config/ $RPi_USER@$RPi_IP:$RPi_HOME/config/

echo "[2/5] Sincronizando modelos entrenados..."
rsync -avz --delete models/ $RPi_USER@$RPi_IP:$RPi_HOME/models/ \
    --exclude="*.joblib" \
    --exclude="*.pickle"

# Transferir modelos joblib (puede ser grande)
echo "[3/5] Sincronizando modelos ML (joblib)..."
rsync -avz models/*.joblib $RPi_USER@$RPi_IP:$RPi_HOME/models/ 2>/dev/null || true

echo "[4/5] Sincronizando datos históricos (1d)..."
rsync -avz --delete data/raw/1d/ $RPi_USER@$RPi_IP:$RPi_HOME/data/raw/1d/

echo "[5/5] Sincronizando código fuente..."
rsync -avz --delete src/ $RPi_USER@$RPi_IP:$RPi_HOME/src/
rsync -avz --delete scripts/*.py $RPi_USER@$RPi_IP:$RPi_HOME/scripts/

echo ""
echo "=========================================="
echo "✅ SINCRONIZACIÓN COMPLETADA"
echo "=========================================="
echo ""
echo "Próximos pasos en la RPi:"
echo "  ssh $RPi_USER@$RPi_IP"
echo "  cd $RPi_HOME"
echo "  bash setup_rpi.sh"
echo ""
