# 🎯 FLUJO COMPLETO: De tu Desktop a Raspberry Pi

## **ARQUITECTURA DEL SISTEMA**

```
┌─────────────────────────────────────────────────────────────────┐
│                          DESKTOP (Windows)                       │
│                                                                   │
│  • Archivos fuente (src/)                                        │
│  • Modelos entrenados (models/)                                  │
│  • Datos históricos (data/raw/1d)                               │
│  • Configuración (config/)                                       │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ bash sync_to_rpi.sh pi 192.168.1.100                     │   │
│  │ (Sincroniza todos los archivos esenciales a la RPi)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓ SSH + SCP
┌─────────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 4B+ (Debian)                     │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ bash setup_rpi.sh                                        │   │
│  │ - Python 3.10+ + venv                                    │   │
│  │ - Dependencias (pandas, sklearn, yfinance, etc)         │   │
│  │ - Servicios systemd (timers)                            │   │
│  │ - Estructura de directorios                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↓                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ AUTOMATIZACIÓN (systemd timers)                          │   │
│  │                                                          │   │
│  │  06:00 — bmv-daily-tasks.timer                          │   │
│  │  ├─ 01_download_data.py        (yfinance)              │   │
│  │  ├─ 02_build_features.py       (indicadores)           │   │
│  │  ├─ 04_generate_signals.py     (RF/SVM/LSTM)          │   │
│  │  ├─ paper_run_daily.py         (SIMULA TRADES) ⭐      │   │
│  │  └─ Guarda en reports/paper_trading/YYYY-MM-DD/       │   │
│  │                                                          │   │
│  │  09:30-16:30 — bmv-monitor-live.timer (L-V)           │   │
│  │  ├─ monitor_forecast_live.py   (cada 5 min)           │   │
│  │  ├─ Actualiza posiciones activas                       │   │
│  │  ├─ Notificaciones Telegram (opcional)                │   │
│  │  └─ Export CSV para dashboard                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↓                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ DATOS GENERADOS EN VIVO                                 │   │
│  │                                                          │   │
│  │ active_positions.json              (posiciones abiertas)│   │
│  │ reports/paper_trading/YYYY-MM-DD/                      │   │
│  │  ├─ signals.csv      (señales del día)                │   │
│  │  ├─ trades.csv       (trades ejecutados + PnL)        │   │
│  │  └─ equity.csv       (curva de capital)               │   │
│  │                                                          │   │
│  │ bitacora_intraday.csv              (posiciones intradía)│   │
│  │ logs/                               (stderr/stdout)    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↑ SCP / HTTP
┌─────────────────────────────────────────────────────────────────┐
│                     MONITOREO REMOTO                             │
│                                                                   │
│  1. Web Browser (Dashboard)                                      │
│     → http://192.168.1.100:5000                                  │
│     → Posiciones en vivo, equity curve, últimos trades          │
│                                                                   │
│  2. Terminal (SSH)                                               │
│     → journalctl -u bmv-daily-tasks -f                          │
│     → Ver logs en tiempo real                                   │
│                                                                   │
│  3. Script de Control Remoto                                     │
│     → bash remote_control_rpi.sh pi 192.168.1.100 logs-daily   │
│     → Backup de reportes, reinicio de servicios, etc           │
│                                                                   │
│  4. Transferencia de Datos                                       │
│     → scp pi@192.168.1.100:~/bmv/reports ./local_backup        │
│     → Copiar CSVs de trades a tu PC                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## **TIMELINE COMPLETO**

### **Día 1: Instalación (1-2 horas)**

```
09:00 | Desktop
      ├─ Preparar archivos en bmv_hybrid_clean_v3/
      └─ bash sync_to_rpi.sh pi 192.168.1.100
         (↓ Copia modelos, datos, config a la RPi)

09:15 | RPi Terminal
      ├─ ssh pi@192.168.1.100
      ├─ cd ~/bmv_hybrid_clean_v3
      ├─ bash setup_rpi.sh
      │  (↓ Instala Python, venv, dependencias — tarda ~10-15 min)
      └─ python validate_rpi_setup.py
         (↓ Verifica que todo está OK)

09:45 | RPi Terminal (pruebas manuales)
      ├─ source .venv/bin/activate
      ├─ python scripts/01_download_data.py
      ├─ python scripts/02_build_features.py
      ├─ python scripts/04_generate_signals.py
      ├─ python scripts/paper_run_daily.py --start 2025-01-20 --end 2025-01-24
      └─ ls reports/paper_trading/
         (↓ Verifica que hay trades generados)

10:15 | RPi Terminal (activar automatización)
      ├─ sudo systemctl enable bmv-daily-tasks.timer
      ├─ sudo systemctl enable bmv-monitor-live.timer
      ├─ sudo systemctl start bmv-daily-tasks.timer
      ├─ sudo systemctl start bmv-monitor-live.timer
      └─ sudo systemctl list-timers
         (↓ Verifica próximas ejecuciones)

10:30 | ✅ LISTO - RPi corriendo automáticamente
```

### **Días Posteriores: Ejecución Automática**

```
06:00 | RPi (trigger systemd)
      ├─ 01_download_data.py           (2-3 min)
      ├─ 02_build_features.py          (1-2 min)
      ├─ 04_generate_signals.py        (1-2 min)
      └─ paper_run_daily.py            (2-3 min)
      
      📊 OUTPUT: reports/paper_trading/2025-01-24/trades.csv
                 ├─ entry_time, ticker, entry_price, exit_price
                 ├─ pnl, pnl_pct, status, reason
                 └─ Signal: BUY/SELL con probabilidad y retorno esperado

09:30-16:30 | RPi (trigger systemd)
            ├─ monitor_forecast_live.py (cada 5 min)
            │   ├─ Actualiza active_positions.json
            │   ├─ Calcula TP/SL en tiempo real
            │   ├─ Exporta bitacora_intraday.csv
            │   └─ [OPCIONAL] Notificaciones Telegram
            └─ 📊 OUTPUT: bitacora_intraday.csv (posiciones + PnL horario)

17:00 | Desktop (o cualquier dispositivo)
      ├─ Acceder web: http://192.168.1.100:5000
      │   └─ Ver: posiciones, equity, últimos trades
      ├─ SSH: journalctl -u bmv-daily-tasks -f
      │   └─ Ver logs en tiempo real
      └─ SCP: scp pi@192.168.1.100:~/bmv/reports ./backup
          └─ Descargar CSVs para análisis offline
```

---

## **¿QUÉ SE REPORTEA AUTOMÁTICAMENTE?**

### **Archivo: `reports/paper_trading/2025-01-24/trades.csv`**

```csv
datetime,ticker,signal_type,entry_price,exit_price,pnl,pnl_pct,status,reason
2025-01-24 06:15:00,AMXL,BUY,2.45,2.51,0.06,2.45%,CLOSED,TP_HIT
2025-01-24 07:30:00,WALMEX,SELL,64.30,63.90,-0.40,0.62%,CLOSED,HOLD_EXIT
2025-01-24 10:45:00,GAPPXL,BUY,1.88,1.85,-0.03,1.60%,CLOSED,SL_HIT
...
```

**Columnas importantes:**
- `signal_type`: BUY o SELL generado por el modelo
- `entry_price / exit_price`: Precios de entrada/salida
- `pnl`: Ganancia/Pérdida en valores absolutos
- `pnl_pct`: Ganancia/Pérdida en porcentaje
- `status`: CLOSED (completado), ACTIVE (abierto)
- `reason`: TP_HIT (take profit), SL_HIT (stop loss), HOLD_EXIT (cierre por tiempo)

### **Archivo: `bitacora_intraday.csv`** (intradía, cada 5 min)

```csv
datetime,ticker,entry_time,current_price,pnl_horario,pnl_pct,status,reason
2025-01-24 09:35:00,AMXL,06:15,2.47,0.02,0.82%,ACTIVE,TRAILING_ATR
2025-01-24 10:00:00,GAPPXL,07:30,63.88,-0.42,0.66%,ACTIVE,BREAK_EVEN
```

### **Archivo: `equity_curve.csv`**

```csv
date,capital,pnl_day,pnl_cumulative
2025-01-20,100000.00,250.00,250.00
2025-01-21,100250.00,-150.00,100.00
2025-01-22,100100.00,425.00,525.00
2025-01-23,100525.00,0.00,525.00
2025-01-24,100525.00,175.00,700.00
```

---

## **CONTROL REMOTO DESDE DESKTOP**

### **Script `remote_control_rpi.sh`**

```bash
# Ver logs en vivo
bash remote_control_rpi.sh pi 192.168.1.100 logs-daily

# Ejecutar manualmente (si no está automático)
bash remote_control_rpi.sh pi 192.168.1.100 start-daily

# Ver estado de timers
bash remote_control_rpi.sh pi 192.168.1.100 status

# Backup de reportes
bash remote_control_rpi.sh pi 192.168.1.100 backup-reports
# (Los archivos se copian a ./rpi_backups/)

# Ver logs monitor en vivo
bash remote_control_rpi.sh pi 192.168.1.100 logs-monitor
```

---

## **OPCIONES DE MONITOREO**

### **Opción 1: Web Dashboard (Recomendado para RPi)**

```bash
pip install flask flask-cors
python dashboard_app.py
# Acceso: http://192.168.1.100:5000
```

✅ Ligero, accesible desde cualquier dispositivo
✅ Gráficos en tiempo real
✅ Última información de posiciones

---

### **Opción 2: Telegram Notifications (Opcional)**

```bash
# En scripts/.env
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOP
TELEGRAM_CHAT_ID=1234567890

# El script monitor_forecast_live.py enviará alertas
# Cuando se abra/cierre posición
```

---

### **Opción 3: SSH Terminal**

```bash
ssh pi@192.168.1.100
journalctl -u bmv-daily-tasks -f
# Ver logs en tiempo real
```

---

## **TROUBLESHOOTING**

| Problema | Solución |
|----------|----------|
| **Scripts tardan mucho** | RPi tiene CPU lenta. Normal. Aumenta swap si es necesario. |
| **No descarga datos (yfinance falla)** | Verificar conexión: `ping 8.8.8.8` |
| **Modelos no carga** | Verifica que `.joblib` se sincronizaron correctamente: `ls -lh models/` |
| **No genera trades** | Verifica `config/paper.yaml` está bien configurado |
| **Systemd timers no ejecutan** | Verificar: `sudo systemctl status bmv-daily-tasks.timer` |
| **Falta espacio disco** | `df -h` + limpiar logs antiguos |

---

## **CHECKLIST PRE-PRODUCCIÓN**

- [ ] ✅ RPi conectada a Internet (WiFi o Ethernet)
- [ ] ✅ Setup completado sin errores: `python validate_rpi_setup.py`
- [ ] ✅ Datos descargados: `ls data/raw/1d/ | wc -l` (debe haber múltiples CSVs)
- [ ] ✅ Modelos cargados: `ls models/*.joblib` (debe haber al menos 2)
- [ ] ✅ Config `paper.yaml` creada/configurada
- [ ] ✅ Prueba manual de paper trading: `python scripts/paper_run_daily.py --start 2025-01-20 --end 2025-01-24`
- [ ] ✅ Servicios habilitados: `sudo systemctl enable bmv-daily-tasks.timer`
- [ ] ✅ Dashboard accesible: `http://192.168.1.100:5000`
- [ ] ✅ Backup preparado (scripts de backup configurados)

---

**¡Sistema listo para trading en paper totalmente automatizado! 🚀**
