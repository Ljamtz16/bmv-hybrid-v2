# =============================================
# README_DAILY_RUNNER.md
# =============================================

# 🚀 Runner Diario H3 Forward-Looking

Script automatizado para ejecutar el pipeline completo de predicciones H3 con señales actuales (forward-looking).

## 📋 Uso básico

```powershell
# Ejecutar con valores por defecto
.\run_daily_h3_forward.ps1

# Ejecutar para un mes específico
.\run_daily_h3_forward.ps1 -Month 2025-11

# Ejecutar con parámetros personalizados
.\run_daily_h3_forward.ps1 -RecentDays 3 -MaxOpen 5 -Capital 2000

# Ejecutar y enviar a Telegram
.\run_daily_h3_forward.ps1 -SendTelegram

# Dry run (sin enviar a Telegram)
.\run_daily_h3_forward.ps1 -SendTelegram -DryRun
```

## 🔧 Parámetros

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `-Month` | string | Mes actual | Mes del forecast (formato: YYYY-MM) |
| `-RecentDays` | int | 2 | Filtrar señales de los últimos N días |
| `-MaxOpen` | int | 3 | Máximo de posiciones ejecutables |
| `-Capital` | double | 1000.0 | Capital total para sizing |
| `-SendTelegram` | switch | false | Enviar plan a Telegram al finalizar |
| `-DryRun` | switch | false | No enviar mensajes (solo testing) |

## 📊 Pipeline ejecutado

1. **Actualizar precios** - Descarga datos hasta hoy
2. **Generar features** - Calcula indicadores técnicos
3. **Inferencia H3** - Aplica modelos RandomForest
4. **Detectar patrones** - Identifica double tops/bottoms
5. **Features de patrones** - Integra patrones al forecast
6. **Mezclar forecast** - Combina señales + patrones
7. **Modelo TTH** - Predice tiempo hasta TP/SL con Monte Carlo
8. **Trade plan** - Selecciona top señales forward-looking
9. **Validar precios** - Compara entry vs precios actuales

## 📂 Archivos generados

```
reports/forecast/{YYYY-MM}/
├── trade_plan_tth.csv              # Plan ejecutable (top N trades)
├── trade_candidates_tth.csv        # Top 15 candidatos
├── trade_plan_tth_telegram.txt     # Mensaje formateado para Telegram
└── trade_plan_tth_stats.json       # Estadísticas agregadas
```

## ⏰ Programar ejecución automática

### Windows Task Scheduler

```powershell
# Crear tarea programada (ejecutar después del cierre: 5:30 PM ET / 10:30 PM UTC)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File C:\path\to\run_daily_h3_forward.ps1 -SendTelegram"
$trigger = New-ScheduledTaskTrigger -Daily -At "10:30PM"
Register-ScheduledTask -TaskName "H3_Daily_Forward" -Action $action -Trigger $trigger
```

### Alternativa: Cron-like con PowerShell

```powershell
# Guardar como run_daily_scheduler.ps1
while ($true) {
    $now = Get-Date
    if ($now.Hour -eq 22 -and $now.Minute -eq 30) {
        .\run_daily_h3_forward.ps1 -SendTelegram
        Start-Sleep -Seconds 3600  # Dormir 1h para no reejecutar
    }
    Start-Sleep -Seconds 60
}
```

## 🔄 Monitoreo continuo

Después de ejecutar el pipeline, monitorear trades activos:

```powershell
python scripts\35_check_predictions_and_notify.py `
    --log data\trading\predictions_log.csv `
    --daily data\us\ohlcv_us_daily.csv `
    --notify TP_SL_ONLY
```

## ⚠️ Notas importantes

1. **Horario**: Ejecutar después del cierre del mercado (4:00 PM ET)
2. **Internet**: Requiere conexión para descargar precios de Yahoo Finance
3. **Telegram**: Configurar `.env` con `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`
4. **Modelos**: Asegurarse de tener `prob_win_clean.joblib` y `return_model_H3.joblib` actualizados

## 🐛 Troubleshooting

**Error: "No hay señales que cumplan criterios"**
- Normal si no hay oportunidades ese día
- El script aplica fallback automático con umbrales relajados

**Error: "Missing env var: TELEGRAM_BOT_TOKEN"**
- Verificar que `.env` existe y tiene credenciales correctas
- Ejecutar sin `-SendTelegram` para saltear notificación

**Error: "forecast_with_patterns_tth.csv no existe"**
- Algún paso del pipeline falló antes
- Revisar logs de cada paso para identificar el problema

## 📈 Ejemplo de salida

```
================================================
🚀 PIPELINE H3 FORWARD-LOOKING - 2025-11
================================================

[1/9] 📥 Actualizando precios del universo master...
[download] Guardado data/us/ohlcv_us_daily.csv (26442 filas, 18 tickers)

[2/9] 🧮 Generando features y targets...
[features] Guardado features_labeled.csv (26442 filas)

[3/9] 🧠 Ejecutando inferencia H3...
[infer] Señales guardadas -> reports/forecast\2025-11

...

[8/9] 🎯 Generando trade plan forward-looking...
[trade_plan_tth] === TOP 3 SEÑALES ===
 1. QQQ    | Score=100.0 | ETTH= 2.0d | P(TP≺SL)=  92% | P(win)=  62%
 2. MSFT   | Score= 87.0 | ETTH= 2.1d | P(TP≺SL)=  92% | P(win)=  62%
 3. WMT    | Score= 79.0 | ETTH= 2.2d | P(TP≺SL)=  91% | P(win)=  66%

================================================
✅ PIPELINE COMPLETADO
================================================
```

## 🔗 Scripts relacionados

- `run_h3_daily.ps1` - Runner anterior (histórico, no forward-looking)
- `show_h3_status.py` - Ver estado de trades activos
- `validate_plan_prices.py` - Validar entry vs precios actuales
- `scripts/show_available_signals_today.py` - Ver señales del día sin filtros
