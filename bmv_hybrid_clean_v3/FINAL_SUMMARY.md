# ✅ RESUMEN FINAL: Setup Production-Ready Raspberry Pi

## Tu Pregunota vs Nuestra Solución

### ❓ "¿Qué es lo mínimo para crear el plan y ejecutar el dashboard en una RPi?"

### ✅ "Listo. Aquí está el setup profesional 24/7"

---

## 📦 LO QUE TIENE QUE HABER

### **A. Código (~/bmv_hybrid_clean_v3/)**

```
✅ Copiado automáticamente por sync_to_rpi.sh
   ├─ config/          (base.yaml, paper.yaml)
   ├─ src/             (módulos: config, io, features, signals, models)
   ├─ scripts/         (6 scripts esenciales)
   ├─ models/          (.joblib entrenados)
   └─ setup_rpi_v2.sh  (INSTALA TODO)
```

### **B. Runtime (~/bmv_runtime/)**

```
Creado automáticamente por setup_rpi_v2.sh
   ├─ data/raw/1d     (datos históricos)
   ├─ data/raw/1h     (intradía - descargado en vivo)
   ├─ reports/paper_trading/ (trades.csv, signals.csv)
   ├─ logs/            (dashboard.log, daily.log)
   ├─ state/           (lock_daily, last_run.json)
   └─ config/runtime.env (CONFIGURACIÓN CENTRALIZADA)
```

---

## 🚀 INSTALACIÓN (Una línea por terminal)

### **Paso 1: Desktop (Windows)**

```bash
cd bmv_hybrid_clean_v3 && bash sync_to_rpi.sh pi 192.168.1.100
```

### **Paso 2: RPi**

```bash
ssh pi@192.168.1.100 && cd ~/bmv_hybrid_clean_v3 && bash setup_rpi_v2.sh
```

*(Espera 15-20 minutos la primera vez)*

### **Paso 3: Validar**

```bash
python validate_rpi_setup.py && curl http://localhost:5000/health
```

---

## ⏰ ¿QUÉ HACE AUTOMÁTICAMENTE?

| Hora | Acción | Archivo | Output |
|------|--------|--------|--------|
| **06:00** | Descarga, features, señales, **paper trading** | `paper_run_daily.py` | `reports/paper_trading/YYYY-MM-DD/trades.csv` |
| **09:30-16:30 (L-V)** | Monitoreo en vivo c/5 min | `monitor_forecast_live.py` | `bitacora_intraday.csv`, `active_positions.json` |
| **24/7** | Dashboard + health check | `dashboard_app_v2.py` | `http://192.168.1.100:5000` |

---

## 📊 OUTPUTS (¿Dónde están los reportes?)

```
~/bmv_runtime/reports/paper_trading/
├─ 2025-01-24/
│  ├─ trades.csv         (entry, exit, PnL, status)
│  ├─ signals.csv        (BUY/SELL signal + probabilidad)
│  └─ equity.csv         (capital por hora)
└─ equity_curve.csv      (histórico diario de capital)

bitacora_intraday.csv     (posiciones abiertas ahora)
```

**¿Cómo acceso?**
1. **Web:** `http://192.168.1.100:5000`
2. **SSH:** `journalctl -u bmv-daily-tasks -f`
3. **SCP:** `scp -r pi@192.168.1.100:~/bmv_runtime/reports ./backup`

---

## 🛡️ PRODUCTION-READY (Lo que no falla)

### **Doble ejecución?**
→ Lock file: `state/lock_daily` (flock previene)

### **Dashboard cae?**
→ `Restart=always` + `RestartSec=10` (reinicia automático)

### **RPi apagada?**
→ `Persistent=true` (reejecutar al prender)

### **Memoria descontrolada?**
→ `MemoryLimit=768M` (mata el proceso si excede)

### **CPU disparada?**
→ `CPUQuota=80%` (limita a 80% de 1 core)

### **Disco lleno?**
→ `DATA_RETENTION_DAYS=90` (borra automático)

### **Logs sin control?**
→ `LOG_MAX_SIZE_MB=100` (rota cada 100MB)

### **No sé qué pasó?**
→ `state/last_run.json` + `logs/*.log` (todo trackeable)

---

## 📈 ARCHIVOS CREADOS PARA TI

```
✅ setup_rpi_v2.sh              (Instalación mejorada)
✅ dashboard_app_v2.py          (Dashboard robusto)
✅ runtime_env_template.txt     (Config centralizada)
✅ PRO_SETUP_GUIDE.md           (Documentación completa)
✅ SETUP_V2_SUMMARY.txt         (Resumen visual)
✅ validate_rpi_setup.py        (10 tests end-to-end)
✅ rpi_health_check.sh          (Verificación de salud)
✅ remote_control_rpi.sh        (Control desde desktop)
```

---

## ⚡ OPCIONES DE MONITOREO

### **1. Web Dashboard (Recomendado)**
```
http://192.168.1.100:5000
├─ /health         (CPU 25%, RAM 45%, disk 8.5GB free, temp 52°C)
├─ /api/positions  (posiciones activas)
├─ /api/equity     (curva de capital)
└─ /api/trades     (últimos 20 trades)
```

### **2. SSH Terminal**
```bash
ssh pi@192.168.1.100
journalctl -u bmv-dashboard -f
```

### **3. Control Remoto**
```bash
bash remote_control_rpi.sh pi 192.168.1.100 logs-daily
bash remote_control_rpi.sh pi 192.168.1.100 status
bash remote_control_rpi.sh pi 192.168.1.100 backup-reports
```

---

## 🔑 LO MÁS IMPORTANTE

| Aspecto | Setup v2 |
|---------|---------|
| **Simplicidad** | 1 comando: `bash setup_rpi_v2.sh` |
| **Config** | Centralizada en `runtime.env` (no hardcoding) |
| **Logs** | Estructurados: `journalctl` + archivos |
| **Robustez** | Locks, retries, límites, health checks |
| **Monitoreo** | `/health` endpoint + dashboard |
| **Troubleshooting** | `validate_rpi_setup.py` (10 tests) |
| **Escalabilidad** | Código vs datos separados |
| **Documentación** | 5 guías + ejemplos |

---

## 🎯 PRÓXIMOS PASOS

### **Immediate (Hoy)**

```bash
# 1. Desktop
bash sync_to_rpi.sh pi 192.168.1.100

# 2. RPi SSH
ssh pi@192.168.1.100
cd ~/bmv_hybrid_clean_v3
bash setup_rpi_v2.sh

# 3. Validar
python validate_rpi_setup.py
```

### **Optional (Esta semana)**

- [ ] Agregar Telegram token en `runtime.env`
- [ ] Configurar backup automático
- [ ] Setup alertas Sentry/DataDog
- [ ] Dashboard mobile-responsive

---

## 💡 DIFERENCIA v1 vs v2

| Feature | v1 | v2 |
|---------|----|----|
| Paths | Relativos (frágil) | `BVM_RUNTIME` (robusto) |
| Config | Hardcodeada | `runtime.env` (parametrizable) |
| Dashboard | Flask dev | Gunicorn (production) |
| Logging | journalctl solo | journalctl + archivos |
| Cache | Ninguno | 15 seg (menos carga) |
| Health | Manual | `/health` automático |
| Locks | Ninguno | state/lock_daily |
| Retry | Manual | systemd restart |

---

## 📞 REFERENCIAS RÁPIDAS

| Tarea | Comando |
|------|---------|
| Ver logs diarios en vivo | `journalctl -u bmv-daily-tasks -f` |
| Ver logs dashboard | `journalctl -u bmv-dashboard -f` |
| Ver próximas ejecuciones | `sudo systemctl list-timers` |
| Salud del sistema | `curl http://localhost:5000/health \| jq` |
| Validar setup | `python validate_rpi_setup.py` |
| Control remoto | `bash remote_control_rpi.sh pi 192.168.1.100 status` |
| Descargar reportes | `scp -r pi@192.168.1.100:~/bmv_runtime/reports ./backup` |
| Reiniciar dashboard | `sudo systemctl restart bmv-dashboard` |

---

## 🎉 RESULTADO FINAL

Una **Raspberry Pi 4B+** que:

✅ **06:00** - Ejecuta paper trading automático  
✅ **09:30-16:30** - Monitorea posiciones en vivo cada 5 minutos  
✅ **24/7** - Dashboard accesible y sano  
✅ **Smart** - Retries, locks, health checks automáticos  
✅ **Loggeable** - Todo se registra (journalctl + archivos)  
✅ **Production-ready** - Para trading real con confianza  

---

**📖 LEE PRIMERO: `PRO_SETUP_GUIDE.md` (la biblia)**

**🚀 ENTONCES: `bash setup_rpi_v2.sh` (y listo)**

---

*Setup production-ready = RPi workhorse 24/7 sin babysitting* 🤖
