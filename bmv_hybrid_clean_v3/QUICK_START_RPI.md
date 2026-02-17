# 🚀 GUÍA RÁPIDA: BMV Hybrid en Raspberry Pi 4B+

## **En 3 Pasos**

### **Paso 1: En tu Desktop**
```bash
cd bmv_hybrid_clean_v3
bash sync_to_rpi.sh pi 192.168.1.100  # Reemplaza con tu IP y usuario
```

### **Paso 2: En la Raspberry Pi**
```bash
ssh pi@192.168.1.100
cd ~/bmv_hybrid_clean_v3
bash setup_rpi.sh
```
*(Espera 10-15 minutos la primera vez)*

### **Paso 3: Activar Automatización**
```bash
sudo systemctl enable bmv-daily-tasks.timer
sudo systemctl enable bmv-monitor-live.timer
sudo systemctl start bmv-daily-tasks.timer
sudo systemctl start bmv-monitor-live.timer
```

**¡Listo! Ya está corriendo.**

---

## **¿Qué Hace Automaticamente?**

| Hora | Acción | Frecuencia |
|------|--------|-----------|
| **06:00** | Descarga datos + Calcula features + Genera señales + **Paper Trading** | Diario |
| **09:30-16:30** | Monitor en vivo (actualiza cada 5 min) | Lunes-Viernes |
| **Diario** | Guarda trades y PnL en `reports/paper_trading/` | Automático |

---

## **Ver Logs en Vivo**

```bash
# Tareas diarias
journalctl -u bmv-daily-tasks -f

# Monitor en vivo
journalctl -u bmv-monitor-live -f
```

---

## **Dashboard Web (Opcional)**

```bash
# En la RPi
pip install flask flask-cors
python dashboard_app.py
```

Luego accede desde cualquier dispositivo:
```
http://192.168.1.100:5000
```

---

## **Control Remoto desde Desktop**

```bash
# Ver logs remotamente
bash remote_control_rpi.sh pi 192.168.1.100 logs-daily

# Iniciar manualmente
bash remote_control_rpi.sh pi 192.168.1.100 start-daily

# Backup de reportes
bash remote_control_rpi.sh pi 192.168.1.100 backup-reports

# Ver estado
bash remote_control_rpi.sh pi 192.168.1.100 status
```

---

## **Archivos Creados**

```
✅ setup_rpi.sh           - Instalación automática
✅ sync_to_rpi.sh         - Sincronizar desde desktop
✅ remote_control_rpi.sh  - Control remoto
✅ dashboard_app.py       - Dashboard web ligero
✅ requirements-lite.txt  - Dependencias optimizadas
✅ INSTALL_RPI.md         - Documentación completa
✅ QUICK_START.md         - Esta guía
```

---

## **Troubleshooting Rápido**

**❌ No conecta a la RPi:**
```bash
ping 192.168.1.100
ssh-copy-id pi@192.168.1.100
```

**❌ Falla la instalación de packages:**
```bash
ssh pi@192.168.1.100
cd ~/bmv_hybrid_clean_v3
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-lite.txt
```

**❌ Ver qué servicios están activos:**
```bash
sudo systemctl list-timers
sudo systemctl status bmv-daily-tasks.timer
```

**❌ Los datos no se actualizan:**
```bash
# Ejecutar manualmente
source .venv/bin/activate
python scripts/01_download_data.py
python scripts/02_build_features.py
```

---

## **Acceder a Reportes**

**Opción 1 - SCP (copiar archivos):**
```bash
scp -r pi@192.168.1.100:~/bmv_hybrid_clean_v3/reports ./mi_reporte_local
```

**Opción 2 - Servidor web:**
```bash
# En RPi
cd ~/bmv_hybrid_clean_v3/reports
python3 -m http.server 8000

# En desktop
# Abre http://192.168.1.100:8000
```

---

## **Documentación Completa**

Para más detalles, ve a: `INSTALL_RPI.md`

---

**¿Dudas? Contacta con soporte o revisa los logs con `journalctl`**
