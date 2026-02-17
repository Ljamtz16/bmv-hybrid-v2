# 📦 ARCHIVOS CREADOS PARA RASPBERRY PI

Estos archivos ya están listos en tu proyecto. Solo debes:

## **Paso 1: DESDE TU DESKTOP**

```bash
# En PowerShell / Git Bash
cd bmv_hybrid_clean_v3
bash sync_to_rpi.sh pi 192.168.1.XXX
```

*Reemplaza:*
- `pi` = tu usuario en la RPi
- `192.168.1.XXX` = IP de tu Raspberry Pi

**Archivo:** `sync_to_rpi.sh`
- Copia automáticamente: `config/`, `models/`, `data/raw/1d/`, `src/`, `scripts/`

---

## **Paso 2: EN LA RASPBERRY PI**

```bash
ssh pi@192.168.1.XXX
cd ~/bmv_hybrid_clean_v3
bash setup_rpi.sh
```

**Archivo:** `setup_rpi.sh`
- Instala Python 3.10+
- Crea virtual environment
- Instala todas las dependencias de `requirements-lite.txt`
- Crea directorios necesarios
- Instala servicios systemd (timers)
- Configura archivo `.env`

---

## **Paso 3: VALIDAR**

```bash
python validate_rpi_setup.py
```

**Archivo:** `validate_rpi_setup.py`
- Verifica Python, venv, librerías
- Verifica archivos y directorios
- Prueba de conectividad a Internet
- Verifica servicios systemd
- 10 tests completos

---

## **Archivos Principales Creados**

### 📄 **Setup & Instalación**
| Archivo | Propósito |
|---------|-----------|
| `setup_rpi.sh` | Instalación automática completa (una sola línea) |
| `sync_to_rpi.sh` | Sincronizar archivos desktop → RPi |
| `requirements-lite.txt` | Dependencias optimizadas para RPi |
| `validate_rpi_setup.py` | Validar que todo está bien instalado |

### 🎮 **Control Remoto**
| Archivo | Propósito |
|---------|-----------|
| `remote_control_rpi.sh` | Controlar RPi desde desktop (logs, backup, status) |
| `dashboard_app.py` | Dashboard web ligero (Flask) |

### 📚 **Documentación**
| Archivo | Propósito |
|---------|-----------|
| `QUICK_START_RPI.md` | Guía rápida 3 pasos |
| `INSTALL_RPI.md` | Documentación completa detallada |
| `ARCHITECTURE.md` | Flujo completo y arquitectura |
| `RPi_SETUP_FILES.md` | Este archivo (resumen) |

---

## **FLUJO RESUMIDO**

```
┌─ Desktop (Windows)
│  └─ bash sync_to_rpi.sh pi 192.168.1.100
│
├─ RPi Terminal
│  ├─ ssh pi@192.168.1.100
│  ├─ cd ~/bmv_hybrid_clean_v3
│  ├─ bash setup_rpi.sh
│  └─ python validate_rpi_setup.py
│
└─ ✅ LISTO
   ├─ 06:00 - Corre automáticamente (tareas diarias)
   ├─ 09:30-16:30 - Monitor en vivo
   └─ Dashboard: http://192.168.1.100:5000
```

---

## **¿QUÉ HACE AUTOMÁTICAMENTE?**

### ⏰ **06:00 (Todos los días)**
1. Descarga datos nuevos con `yfinance`
2. Calcula indicadores técnicos (features)
3. Genera señales BUY/SELL con tus modelos
4. **Ejecuta paper trading del día entero**
5. Guarda trades en `reports/paper_trading/YYYY-MM-DD/trades.csv`

### 📊 **09:30-16:30 (Lunes-Viernes)**
1. Monitorea posiciones en vivo
2. Calcula TP/SL en tiempo real
3. Actualiza `bitacora_intraday.csv` cada 5 minutos
4. [Opcional] Envía notificaciones a Telegram

### 📈 **Reportes Generados**
```
reports/paper_trading/
├── 2025-01-24/
│   ├── signals.csv         (señales del día)
│   ├── trades.csv          (trades ejecutados + PnL)
│   └── equity.csv          (curva de capital)
├── bitacora_intraday.csv   (posiciones actuales)
└── equity_curve.csv        (histórico diario)
```

---

## **ACCESO REMOTO A DATOS**

### 🌐 **Dashboard Web**
```bash
# Accede desde cualquier navegador
http://192.168.1.100:5000
```
✅ Gráficos en tiempo real
✅ Posiciones activas
✅ Últimos trades
✅ Curva de capital

### 📱 **Telegram** (Opcional)
```bash
# En scripts/.env, agrega:
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id

# Recibirás notificaciones cuando se abra/cierre posición
```

### 💻 **SSH Terminal**
```bash
ssh pi@192.168.1.100
journalctl -u bmv-daily-tasks -f
# Ver logs en tiempo real
```

### 📥 **Descargar Reportes**
```bash
scp -r pi@192.168.1.100:~/bmv_hybrid_clean_v3/reports ./mi_reporte_local
```

---

## **CONTROL DESDE DESKTOP**

**Archivo:** `remote_control_rpi.sh`

```bash
# Ver logs
bash remote_control_rpi.sh pi 192.168.1.100 logs-daily

# Iniciar manualmente
bash remote_control_rpi.sh pi 192.168.1.100 start-daily

# Ver estado
bash remote_control_rpi.sh pi 192.168.1.100 status

# Backup de reportes
bash remote_control_rpi.sh pi 192.168.1.100 backup-reports

# Reiniciar servicios
bash remote_control_rpi.sh pi 192.168.1.100 restart-services
```

---

## **PRIMEROS 3 COMANDOS**

```bash
# 1️⃣ Desktop
bash sync_to_rpi.sh pi 192.168.1.100

# 2️⃣ RPi
ssh pi@192.168.1.100
bash setup_rpi.sh

# 3️⃣ Validar
python validate_rpi_setup.py
```

**¡Listo! Ya está corriendo.**

---

## **TROUBLESHOOTING RÁPIDO**

| Problema | Solución |
|----------|----------|
| `bash: sync_to_rpi.sh: No such file` | Estás en directorio equivocado. `cd bmv_hybrid_clean_v3` |
| `Permission denied (publickey)` | Configura SSH key: `ssh-copy-id pi@192.168.1.100` |
| `setup_rpi.sh: command not found` | Ejecuta: `bash setup_rpi.sh` (no `./setup_rpi.sh`) |
| `pip: command not found` | RPi no tiene pip. Ejecuta: `sudo apt install python3-pip` |
| `No such file or directory: requirements-lite.txt` | Verifica que el archivo está en el mismo directorio |

---

## **SIGUIENTES PASOS**

1. ✅ Copiar estos archivos a tu proyecto
2. 🚀 Ejecutar `bash sync_to_rpi.sh pi 192.168.1.100` desde desktop
3. 🍓 Conectar a RPi: `ssh pi@192.168.1.100`
4. 🔧 Ejecutar `bash setup_rpi.sh` (esperar 10-15 min)
5. ✔️ Validar: `python validate_rpi_setup.py`
6. 🎯 Habilitar: `sudo systemctl enable bmv-daily-tasks.timer`
7. 🌐 Acceder: `http://192.168.1.100:5000`

---

**¿Preguntas?** Revisa `INSTALL_RPI.md` o `ARCHITECTURE.md`

**¿Necesitas debug?** Ejecuta:
```bash
sudo journalctl -u bmv-daily-tasks -n 100
```

---

🎉 **¡Tu RPi está lista para trader en paper completamente automática!**
