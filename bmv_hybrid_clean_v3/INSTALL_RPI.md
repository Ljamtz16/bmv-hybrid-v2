# 🍓 Instalación BMV Hybrid en Raspberry Pi 4B+

## Prerequisitos

- **Raspberry Pi 4B+** (4GB RAM mínimo, 8GB recomendado)
- **Raspbian/Raspberry Pi OS** (Bookworm o Bullseye)
- **Conexión a Internet** (WiFi o Ethernet)
- Acceso SSH activado en la RPi
- **Espacio libre**: ~10-15 GB (datos históricos + venv + logs)

---

## **OPCIÓN A: Setup Rápido (Recomendado)**

### Paso 1: Preparar el repo en tu desktop

```bash
# En tu desktop/laptop
cd bmv_hybrid_clean_v3

# Copiar este archivo de setup
cp setup_rpi.sh sync_to_rpi.sh /ruta/del/proyecto/
```

### Paso 2: Sincronizar desde Desktop a RPi

```bash
# Desde tu desktop, ejecuta:
bash sync_to_rpi.sh pi 192.168.1.XXX

# Reemplaza:
# - "pi" con tu usuario en la RPi
# - "192.168.1.XXX" con la IP de tu RPi
```

**Para encontrar la IP de la RPi:**
```bash
# En la RPi o router
hostname -I
```

### Paso 3: Conectar por SSH y ejecutar setup

```bash
# En tu terminal
ssh pi@192.168.1.XXX

# Ya en la RPi
cd ~/bmv_hybrid_clean_v3
bash setup_rpi.sh
```

**Esto tarda ~10-15 minutos la primera vez** (instalación de dependencias).

---

## **OPCIÓN B: Setup Manual Paso a Paso**

Si prefieres hacerlo manualmente o tienes problemas:

### 1. Conectar por SSH

```bash
ssh pi@192.168.1.XXX
```

### 2. Instalar Python 3.10+

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip python3-dev
python3 --version
```

### 3. Clonar/Descargar el proyecto

**Opción A - Vía Git:**
```bash
cd ~
git clone https://github.com/tuusuario/bmv_hybrid_clean_v3.git
cd bmv_hybrid_clean_v3
```

**Opción B - Vía SCP (desde desktop):**
```bash
# En tu desktop
scp -r bmv_hybrid_clean_v3 pi@192.168.1.XXX:~/

# En la RPi
cd ~/bmv_hybrid_clean_v3
```

### 4. Crear Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 5. Instalar dependencias

```bash
pip install -r requirements-lite.txt
```

**Nota:** En RPi esto puede tardar 5-10 minutos. El proceso es normal.

### 6. Crear estructura de directorios

```bash
mkdir -p data/raw/1d data/raw/1h data/interim data/daily reports/paper_trading logs
```

### 7. Copiar datos históricos desde desktop

**Desde tu desktop:**
```bash
scp -r data/raw/1d/* pi@192.168.1.XXX:~/bmv_hybrid_clean_v3/data/raw/1d/
scp -r models/*.joblib pi@192.168.1.XXX:~/bmv_hybrid_clean_v3/models/
scp config/paper.yaml pi@192.168.1.XXX:~/bmv_hybrid_clean_v3/config/
```

### 8. Prueba manual

**En la RPi:**
```bash
source .venv/bin/activate
python scripts/01_download_data.py
python scripts/02_build_features.py
python scripts/04_generate_signals.py
```

---

## **Configuración de Automatización**

### Opción 1: Servicios Systemd (Recomendado)

El script `setup_rpi.sh` ya lo hace, pero si lo hiciste manual:

```bash
# Crear archivo de servicio para tareas diarias (06:00)
sudo nano /etc/systemd/system/bmv-daily-tasks.service
```

Pega esto:
```ini
[Unit]
Description=BMV Hybrid - Tareas Diarias
After=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/bmv_hybrid_clean_v3
Environment="PATH=/home/pi/bmv_hybrid_clean_v3/.venv/bin:/usr/bin"
Environment="PYTHONPATH=/home/pi/bmv_hybrid_clean_v3"
ExecStart=/home/pi/bmv_hybrid_clean_v3/.venv/bin/python /home/pi/bmv_hybrid_clean_v3/scripts/paper_run_daily.py --start "$(date -d yesterday +%Y-%m-%d)" --end "$(date +%Y-%m-%d)"
StandardOutput=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Timer
sudo nano /etc/systemd/system/bmv-daily-tasks.timer
```

Pega esto:
```ini
[Unit]
Description=Ejecuta tareas BMV a las 06:00

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bmv-daily-tasks.timer
sudo systemctl start bmv-daily-tasks.timer
```

### Opción 2: Cron (Alternativa)

```bash
crontab -e
```

Agrega estas líneas:

```cron
# Tareas diarias a las 06:00 (lunes a viernes)
0 6 * * 1-5 cd /home/pi/bmv_hybrid_clean_v3 && source .venv/bin/activate && python scripts/01_download_data.py >> logs/daily.log 2>&1

10 6 * * 1-5 cd /home/pi/bmv_hybrid_clean_v3 && source .venv/bin/activate && python scripts/02_build_features.py >> logs/daily.log 2>&1

15 6 * * 1-5 cd /home/pi/bmv_hybrid_clean_v3 && source .venv/bin/activate && python scripts/04_generate_signals.py >> logs/daily.log 2>&1

20 6 * * 1-5 cd /home/pi/bmv_hybrid_clean_v3 && source .venv/bin/activate && python scripts/paper_run_daily.py --start "$(date -d yesterday +\%Y-\%m-\%d)" --end "$(date +\%Y-\%m-\%d)" >> logs/daily.log 2>&1

# Monitor en vivo 9:30-16:30 (lunes a viernes)
30 9 * * 1-5 cd /home/pi/bmv_hybrid_clean_v3 && source .venv/bin/activate && python scripts/monitor_forecast_live.py --loop --interval 300 >> logs/monitor.log 2>&1 &

0 16 * * 1-5 pkill -f "monitor_forecast_live.py"
```

---

## **Monitoreo y Logs**

### Ver logs en vivo (systemd)

```bash
# Tareas diarias
sudo journalctl -u bmv-daily-tasks -f

# Monitor en vivo
sudo journalctl -u bmv-monitor-live -f

# Últimas 50 líneas
sudo journalctl -u bmv-daily-tasks -n 50
```

### Ver logs en archivos (cron)

```bash
tail -f logs/daily.log
tail -f logs/monitor.log
```

### Ver estado de timers

```bash
systemctl list-timers
sudo systemctl status bmv-daily-tasks.timer
```

---

## **Acceder a Reportes Remotamente**

### Opción A: SCP (copiar archivos)

```bash
# Desde tu desktop
scp pi@192.168.1.XXX:~/bmv_hybrid_clean_v3/reports/paper_trading/*.csv ~/local_reports/
```

### Opción B: Setup web ligero (Opcional)

```bash
# En la RPi
sudo apt install python3-http-server

cd ~/bmv_hybrid_clean_v3/reports
python3 -m http.server 8000
```

Luego en tu navegador:
```
http://192.168.1.XXX:8000
```

---

## **Troubleshooting**

### ❌ "pip: command not found"

```bash
sudo apt install python3-pip
```

### ❌ "ModuleNotFoundError: No module named 'pandas'"

```bash
source .venv/bin/activate
pip install -r requirements-lite.txt
```

### ❌ "Permission denied" en systemd

```bash
# Asegúrate que el directorio sea propiedad del usuario
sudo chown -R pi:pi /home/pi/bmv_hybrid_clean_v3
```

### ❌ Bajo rendimiento en RPi

1. **Aumentar espacio de swap:**
   ```bash
   sudo dphys-swapfile swapoff
   sudo nano /etc/dphys-swapfile
   # Cambiar: CONF_SWAPSIZE=2048
   sudo dphys-swapfile setup
   sudo dphys-swapfile swapon
   ```

2. **Reducir procesos innecesarios:**
   ```bash
   sudo systemctl disable avahi-daemon
   sudo systemctl disable triggerhappy
   ```

### ❌ Errores de conexión a yfinance

```bash
# Verificar conectividad
ping -c 3 8.8.8.8
curl -I https://query1.finance.yahoo.com
```

---

## **Checklist de Validación**

```bash
# En la RPi, verifica todo está OK
echo "=== Python ==="
python3 --version

echo "=== Venv ==="
source .venv/bin/activate && pip list | head -10

echo "=== Directorios ==="
ls -la data/raw/1d/ | head -5
ls -la models/*.joblib

echo "=== Scripts ==="
ls scripts/*.py | wc -l

echo "=== Config ==="
ls config/

echo "=== Prueba de importes ==="
python3 -c "import pandas, yfinance, sklearn, yaml; print('✅ Todas las librerías OK')"

echo "=== Timers (systemd) ==="
sudo systemctl list-timers
```

---

## **Mantenimiento Semanal**

```bash
# Actualizar datos (manual si algo falla)
cd ~/bmv_hybrid_clean_v3
source .venv/bin/activate
python scripts/01_download_data.py

# Verificar espacio
df -h

# Limpiar logs antiguos (más de 7 días)
find logs -type f -mtime +7 -delete

# Backup de reportes
tar czf reports_backup_$(date +%Y%m%d).tar.gz reports/
```

---

## **Dashboard Web Avanzado (Opcional)**

Si quieres un dashboard web más robusto:

```bash
pip install flask flask-cors
```

Crea un archivo `dashboard_app.py` en la RPi con un servidor Flask ligero que sirva los CSVs como JSON.

---

¡Listo! Tu RPi ahora ejecutará automáticamente:
- ✅ 06:00 - Descarga, features, señales y paper trading
- ✅ 09:30-16:30 - Monitoreo en vivo con actualizaciones cada 5 min
- ✅ Logs en `journalctl` o archivos
- ✅ Reportes de PnL en `reports/paper_trading/`

¿Alguna pregunta?
