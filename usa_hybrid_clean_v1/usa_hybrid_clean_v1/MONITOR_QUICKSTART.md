# 🚀 QUICK START - Monitor Cada 5 Minutos

## ▶️ Iniciar Monitor

```powershell
# Opción 1: Ventana abierta (RECOMENDADO - más simple)
.\monitor_bitacora.ps1

# Opción 2: Background / Servicio (requiere admin)
.\setup_monitor_service.ps1 -Action Install
.\setup_monitor_service.ps1 -Action Start
```

## ⏹️ Detener Monitor

```powershell
# Opción 1: Si está en ventana
Ctrl + C

# Opción 2: Si está como servicio
.\setup_monitor_service.ps1 -Action Stop
```

## 📊 Ver Estado

```powershell
# Actualización única
.\monitor_bitacora.ps1 -Once

# Abrir Excel
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"

# Resumen en terminal
python scripts\bitacora_excel.py --summary
```

## ⚙️ Opciones

```powershell
# Cada 3 minutos
.\monitor_bitacora.ps1 -IntervalMinutes 3

# 24/7 (sin restricción de horario)
.\monitor_bitacora.ps1 -Continuous

# Solo una vez (testing)
.\monitor_bitacora.ps1 -Once
```

## 🎯 Workflow Típico

```powershell
# 1. Generar plan diario (después del cierre 4-5 PM)
.\run_daily_h3_forward.ps1 -SendTelegram

# 2. Iniciar monitor al día siguiente (antes apertura 9:00 AM)
.\monitor_bitacora.ps1

# 3. Durante el día - Revisar Excel cuando quieras
# (El monitor actualiza automáticamente cada 5 min)

# 4. Al finalizar el día - Detener monitor
Ctrl + C
```

## ✅ ¿Qué hace cada 5 minutos?

1. ✅ Descarga precios actuales (18 tickers)
2. ✅ Actualiza bitácora en Google Drive
3. ✅ Calcula progreso hacia TP
4. ✅ Detecta si alcanzó TP o SL
5. ✅ Calcula P&L actual
6. ✅ Verifica expiración (por horizonte de días)
7. ✅ Guarda cambios con formato visual

## 🎨 Formato Visual en Excel

- 🟢 **Verde** = TP alcanzado (ganador)
- 🔴 **Rojo** = SL alcanzado (perdedor)
- 🟡 **Amarillo** = Activa (en progreso)

## 📱 Acceso desde Móvil

1. Abrir Google Drive app
2. Buscar: "Trading proyecto"
3. Abrir: `H3_BITACORA_PREDICCIONES.xlsx`
4. Ver actualizaciones en tiempo real

---

**¿Preguntas?** Ver `MONITOR_README.md` para documentación completa.
