# 🔧 SETUP ROBUSTO v2 - PRODUCCIÓN

## ✅ VALIDACIÓN DE TU PLAN

Tu propuesta es **profesional y production-ready**. Hemos implementado:

### 1️⃣ **Estructura de Directorios Separada** ✓
```
~/bmv_hybrid_clean_v3/    (código - estático, versionado)
~/bmv_runtime/            (datos - volátil, crece)
  ├── data/raw/1d, 1h
  ├── reports/paper_trading
  ├── logs/
  ├── state/              (locks, last_run.json)
  └── config/runtime.env  (centralizado)
```

### 2️⃣ **Requirements Optimizado para ARM** ✓
- Sin `matplotlib` server-side (usa Chart.js en cliente)
- `pyarrow` opcional (fallback a CSV)
- Pre-requisitos por `apt` (no compilar)

### 3️⃣ **setup_rpi_v2.sh - Profesional** ✓
- `python3-dev build-essential libatlas-base-dev` (ARM stack)
- Crea `~/bmv_runtime/` con permisos correctos
- Instala servicios systemd con logging robusto
- Health check integrado
- Detecta problemas de swap/recursos

### 4️⃣ **dashboard_app_v2.py - Ligero & Robusto** ✓
- Cache de 15 segundos (no recalcular)
- Endpoint `/health` con telemetría (CPU, RAM, disk, temp)
- Lee solo archivos procesados (CSV, JSON)
- Logging estructurado
- Manejo de errores
- `EnvironmentFile=runtime.env` en systemd

### 5️⃣ **systemd Services - Blindado** ✓
- `bmv-dashboard.service` con gunicorn (no Flask dev)
- `bmv-daily-tasks.service` + timer (oneshot)
- Locks en `state/lock_daily` (evita doble ejecución)
- `Restart=always` + `RestartSec=10`
- `TimeoutStartSec=1800` (si tarda descarga)
- `StandardOutput/Error` → archivos en `logs/`
- `Persistent=true` (si RPi se apaga, corre al prender)
- Límites: `MemoryLimit=768M`, `CPUQuota=80%`

### 6️⃣ **runtime.env - Centralizado** ✓
- **Todo** configurable desde 1 archivo
- `BVM_RUNTIME`, `BVM_CODE`, `BVM_LOGS`, etc.
- Zona horaria: `America/Mexico_City`
- Credenciales (Telegram, Sentry) sin hardcodear
- Tiempos: `DAILY_TASK_HOUR=06`, `MONITOR_INTERVAL_SEC=300`

---

## 🚀 FLUJO DE INSTALACIÓN (3 pasos)

### **Paso 1: Desktop (Windows)**

```bash
cd bmv_hybrid_clean_v3
bash sync_to_rpi.sh pi 192.168.1.100
```

*(Copia: `config/`, `models/`, `data/raw/1d/`, `src/`, `scripts/`)*

### **Paso 2: RPi SSH**

```bash
ssh pi@192.168.1.100
cd ~/bmv_hybrid_clean_v3
bash setup_rpi_v2.sh
```

*(Instala: Python, venv, deps, servicios systemd, estructura runtime, health check)*

**Tiempo total:** ~15-20 minutos (la primera vez).

### **Paso 3: Activar Servicios**

```bash
sudo systemctl enable bmv-dashboard.service
sudo systemctl enable bmv-daily-tasks.timer
sudo systemctl enable bmv-monitor-live.timer

sudo systemctl start bmv-dashboard.service
sudo systemctl start bmv-daily-tasks.timer
```

*(Ya está corriendo automáticamente)*

---

## 📊 ¿QUÉ EJECUTA AUTOMÁTICAMENTE?

### **06:00 - Tareas Diarias** (systemd timer)

```bash
ExecStart=$VENV/bin/python scripts/paper_run_daily.py \
    --start "$(date -d yesterday +%Y-%m-%d)" \
    --end "$(date +%Y-%m-%d)"
```

**Genera:**
- `reports/paper_trading/YYYY-MM-DD/trades.csv` (entry, exit, pnl)
- `reports/paper_trading/YYYY-MM-DD/signals.csv` (señales)
- `state/last_run.json` (exit_code, duration, artifacts)

### **09:30-16:30 - Monitor en Vivo** (L-V)

```bash
scripts/monitor_forecast_live.py --loop --interval 300
```

**Genera:**
- `bitacora_intraday.csv` (posiciones + PnL horario)
- `active_positions.json` (actualizado cada 5 min)

### **Continuo - Dashboard**

```
http://192.168.1.100:5000
├─ /health             (CPU, RAM, disk, temp, last_run)
├─ /api/positions      (activas ahora)
├─ /api/equity         (curva de capital + stats)
├─ /api/trades/latest  (últimos 20 trades)
└─ /api/status         (general system status)
```

---

## 🔍 HEALTH CHECK & MONITOREO

### **Validar Instalación**

```bash
cd ~/bmv_hybrid_clean_v3
python validate_rpi_setup.py
```

**10 tests:** Python, venv, imports, directorios, modelos, servicios, conectividad, etc.

### **Ver Logs en Vivo**

```bash
# Dashboard
journalctl -u bmv-dashboard -f

# Tareas diarias
journalctl -u bmv-daily-tasks -f

# Monitor en vivo
journalctl -u bmv-monitor-live -f

# Últimas 50 líneas
journalctl -u bmv-dashboard -n 50
```

### **Ver Estado de Timers**

```bash
sudo systemctl list-timers
sudo systemctl status bmv-daily-tasks.timer
sudo systemctl status bmv-monitor-live.timer
```

### **Ver Health del Sistema**

```bash
# En RPi
curl http://localhost:5000/health | jq

# Desde desktop
curl http://192.168.1.100:5000/health | jq
```

**Responde:**
```json
{
  "status": "ok",
  "system": {
    "cpu_percent": 25,
    "memory_percent": 45,
    "disk_free_gb": 8.5,
    "cpu_temp_c": 52
  }
}
```

---

## 🛡️ BLINDAJE (Lo que evita "fantasmas")

| Problema | Solución |
|----------|----------|
| Doble ejecución de daily tasks | Lock file: `state/lock_daily` (flock en systemd) |
| Script tarda mucho | `TimeoutStartSec=1800` (30 min para descarga) |
| RPi apagada, se pierde ejecución | `Persistent=true` en timer (corre al prender) |
| Dashboard se cae | `Restart=always` + `RestartSec=10` |
| Memoria se llena | `MemoryLimit=768M` (mata el proceso si excede) |
| CPU descontrolada | `CPUQuota=80%` (limita a 80% de 1 core) |
| Disco lleno | Retention en `data/` y `logs/` (90 días) |
| Logs sin límite | `LOG_MAX_SIZE_MB=100` (rota logs) |
| Temperaturas altas | Health check envía alerts si > 75°C |
| No sé qué pasó ayer | `state/last_run.json` + `logs/*.log` (todo trackeable) |

---

## 🔧 CAMBIOS KEY vs v1

| Aspecto | v1 | v2 |
|--------|----|----|
| **Paths** | Relativos (frágiles) | `BVM_RUNTIME` centralizado |
| **Config** | Hardcodeada | `runtime.env` (todo parametrizable) |
| **Logs** | `journalctl` solo | `journalctl` + archivos (máx 100MB) |
| **Dashboard** | Flask dev (slow) | Gunicorn (production) |
| **Cache** | Ninguno | 15 seg (menos carga) |
| **Health** | Manual | Endpoint `/health` automático |
| **Locks** | Ninguno | `state/lock_daily` evita doble corrida |
| **Retry** | Manual | systemd restart automático |
| **Permisos** | Default | `chmod 600` en secrets |
| **Telemetría** | Manual | psutil integrado (CPU temp, RAM, disk) |

---

## 📝 ARCHIVOS NUEVOS

```
✅ setup_rpi_v2.sh              (Instalación mejorada)
✅ dashboard_app_v2.py          (Dashboard robusto)
✅ runtime_env_template.txt     (Config centralizada)
✅ PRO_SETUP_GUIDE.md           (Esta guía)
```

**Los anteriores siguen siendo válidos pero la v2 es más robusta.**

---

## ⚡ NEXT STEPS

### Immediate

1. Copiar nuevos archivos a tu repo:
   - `setup_rpi_v2.sh`
   - `dashboard_app_v2.py`
   - `runtime_env_template.txt`

2. En RPi, ejecutar **solo**:
   ```bash
   bash setup_rpi_v2.sh
   ```
   *(El script hace TODO)*

3. Validar:
   ```bash
   python validate_rpi_setup.py
   curl http://localhost:5000/health
   ```

### Optional

- [ ] Agregar Telegram token en `~/bmv_runtime/config/runtime.env`
- [ ] Configurar backup en NFS/USB
- [ ] Agregar monitoreo con Sentry
- [ ] Setup de alertas en Slack

---

## 🎯 RESULTADO FINAL

**Una RPi 4B+** que:

✅ **06:00** - Ejecuta paper trading automáticamente  
✅ **09:30-16:30** - Monitorea posiciones en vivo cada 5 min  
✅ **24/7** - Dashboard accesible en `http://192.168.1.100:5000`  
✅ **Smart retry** - Si falla, reinicia automáticamente  
✅ **Health tracked** - CPU, RAM, temp, disk, last_run en `health`  
✅ **Logs completos** - TODO se registra (journalctl + archivos)  
✅ **No doble ejecución** - Locks evitan conflictos  
✅ **Seguro para 24/7** - Límites de memoria/CPU

---

**Esta es la setup que yo usaría en producción.** 🚀
