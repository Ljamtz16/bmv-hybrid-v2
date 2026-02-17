#!/bin/bash
################################################################################
# remote_control_rpi.sh
# Script para controlar la RPi remotamente desde desktop
# Uso: bash remote_control_rpi.sh <usuario> <ip> <comando>
################################################################################

if [ $# -lt 3 ]; then
    echo "Uso: bash remote_control_rpi.sh <usuario> <ip> <comando>"
    echo ""
    echo "Comandos disponibles:"
    echo "  start-daily      - Ejecutar tareas diarias ahora"
    echo "  start-monitor    - Iniciar monitoreo en vivo"
    echo "  stop-monitor     - Detener monitoreo"
    echo "  logs-daily       - Ver últimas 50 líneas de logs diarios"
    echo "  logs-monitor     - Ver últimas 50 líneas de logs monitor"
    echo "  status           - Ver estado de servicios"
    echo "  sync-data        - Sincronizar datos desde desktop a RPi"
    echo "  backup-reports   - Backup de reports desde RPi a desktop"
    echo "  restart-services - Reiniciar todos los servicios"
    echo ""
    echo "Ejemplo: bash remote_control_rpi.sh pi 192.168.1.100 logs-daily"
    exit 1
fi

USER=$1
IP=$2
CMD=$3
REPO="/home/$USER/bmv_hybrid_clean_v3"

echo "========================================"
echo "Control Remoto RPi"
echo "Usuario: $USER"
echo "IP: $IP"
echo "Comando: $CMD"
echo "========================================"
echo ""

case $CMD in
    start-daily)
        echo "[+] Ejecutando tareas diarias..."
        ssh $USER@$IP "sudo systemctl start bmv-daily-tasks"
        echo "✅ Tareas iniciadas"
        ;;
    
    start-monitor)
        echo "[+] Iniciando monitoreo en vivo..."
        ssh $USER@$IP "sudo systemctl start bmv-monitor-live"
        echo "✅ Monitor iniciado"
        ;;
    
    stop-monitor)
        echo "[+] Deteniendo monitoreo..."
        ssh $USER@$IP "sudo systemctl stop bmv-monitor-live"
        echo "✅ Monitor detenido"
        ;;
    
    logs-daily)
        echo "[+] Últimas 50 líneas de logs diarios:"
        ssh $USER@$IP "sudo journalctl -u bmv-daily-tasks -n 50"
        ;;
    
    logs-monitor)
        echo "[+] Últimas 50 líneas de logs monitor:"
        ssh $USER@$IP "sudo journalctl -u bmv-monitor-live -n 50"
        ;;
    
    status)
        echo "[+] Estado de servicios:"
        ssh $USER@$IP "sudo systemctl status bmv-daily-tasks.timer bmv-monitor-live.timer"
        echo ""
        echo "[+] Próximas ejecuciones:"
        ssh $USER@$IP "sudo systemctl list-timers bmv-*"
        ;;
    
    sync-data)
        echo "[+] Sincronizando datos hacia RPi..."
        echo "Asegúrate que has ejecutado 'bash sync_to_rpi.sh $USER $IP' primero"
        ;;
    
    backup-reports)
        echo "[+] Backup de reports desde RPi..."
        mkdir -p ./rpi_backups
        scp -r $USER@$IP:$REPO/reports ./rpi_backups/reports_$(date +%Y%m%d_%H%M%S)
        echo "✅ Backup completado en ./rpi_backups/"
        ;;
    
    restart-services)
        echo "[+] Reiniciando servicios..."
        ssh $USER@$IP "sudo systemctl restart bmv-daily-tasks.timer bmv-monitor-live.timer"
        echo "✅ Servicios reiniciados"
        ;;
    
    *)
        echo "❌ Comando no reconocido: $CMD"
        exit 1
        ;;
esac

echo ""
echo "========================================"
