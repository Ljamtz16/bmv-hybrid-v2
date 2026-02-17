# 🔄 Monitor Continuo de Bitácora H3

Sistema de monitoreo automático cada 5 minutos para actualizar precios y detectar TP/SL en tiempo real.

---

## 🎯 ¿Qué hace?

- ✅ Descarga precios actualizados cada 5 minutos
- ✅ Actualiza bitácora en Google Drive automáticamente
- ✅ Detecta cuando se alcanza TP o SL
- ✅ Calcula P&L en tiempo real
- ✅ Notifica cambios de estado
- ✅ Funciona durante horario de mercado (9:30-16:00 ET)
- ✅ Soporte para posiciones LONG y SHORT

---

## 🚀 Opciones de Uso

### **Opción 1: Ejecución Manual** (Ventana abierta) ⭐ RECOMENDADO

Mantener una ventana PowerShell abierta con el monitor ejecutándose.

```powershell
# Monitor cada 5 minutos (solo horario de mercado)
.\monitor_bitacora.ps1

# Monitor cada 3 minutos
.\monitor_bitacora.ps1 -IntervalMinutes 3

# Monitor continuo 24/7 (útil para mercados internacionales)
.\monitor_bitacora.ps1 -Continuous

# Ejecutar solo una vez
.\monitor_bitacora.ps1 -Once
```

**Ventajas:**
- ✅ Sin permisos de administrador
- ✅ Fácil de iniciar/detener (Ctrl+C)
- ✅ Ver salida en tiempo real
- ✅ No requiere configuración adicional

**Desventajas:**
- ⚠️ Debes mantener la ventana abierta
- ⚠️ Se detiene si cierras la ventana

---

### **Opción 2: Servicio de Windows / Tarea Programada** (Background)

Ejecutar en segundo plano como servicio del sistema.

#### **Instalación:**
```powershell
# Ejecutar PowerShell como Administrador y luego:
.\setup_monitor_service.ps1 -Action Install

# Iniciar servicio
.\setup_monitor_service.ps1 -Action Start

# Ver estado
.\setup_monitor_service.ps1 -Action Status
```

#### **Control:**
```powershell
# Detener servicio
.\setup_monitor_service.ps1 -Action Stop

# Reiniciar
.\setup_monitor_service.ps1 -Action Stop
.\setup_monitor_service.ps1 -Action Start

# Desinstalar
.\setup_monitor_service.ps1 -Action Uninstall
```

**Ventajas:**
- ✅ Ejecuta en background (sin ventana)
- ✅ Inicia automáticamente con Windows
- ✅ No se detiene al cerrar sesión
- ✅ Ideal para servidores/VPS

**Desventajas:**
- ⚠️ Requiere permisos de administrador
- ⚠️ Setup más complejo
- ⚠️ No ves salida en tiempo real (usa logs)

---

### **Opción 3: Script Python** (Multiplataforma)

Usar versión Python en lugar de PowerShell.

```bash
# Monitor cada 5 minutos (solo horario de mercado)
python monitor_bitacora.py

# Monitor continuo 24/7
python monitor_bitacora.py --continuous

# Monitor cada 10 minutos
python monitor_bitacora.py --interval 10

# Ejecutar solo una vez
python monitor_bitacora.py --once
```

**Ventajas:**
- ✅ Funciona en Windows, Linux, Mac
- ✅ Mismo comportamiento que PowerShell
- ✅ Fácil de personalizar

---

## 📊 Ejemplo de Salida

```
============================================
  MONITOR CONTINUO BITACORA H3
============================================

Intervalo: 5 minutos
Modo: Solo horario de mercado (9:30-16:00 ET, lun-vie)

Presiona Ctrl+C para detener
============================================

[2025-11-06 10:15:00] 🔍 Actualización #1
📥 Descargando precios actuales...
[*********************100%***********************]  18 of 18 completed
✅ Precios actualizados

📁 Usando Google Drive: G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx
📅 Fecha de precios: 2025-11-06
  ✅ QQQ TP HIT @ $625.50 (+3.85%)
✅ Actualizadas 6 predicciones
   🎯 1 alcanzaron TP
✅ Hoja de resumen actualizada
   Total: 6 | Activas: 5 | Win Rate: 16.7%

⏳ Próxima actualización en 5 minutos...

[2025-11-06 10:20:00] 🔍 Actualización #2
📥 Descargando precios actuales...
...
```

---

## ⏱️ Horario de Mercado

Por defecto, el monitor solo funciona durante horario de mercado:

- **Días:** Lunes a Viernes
- **Horario:** 9:30 AM - 4:00 PM ET (Eastern Time)
- **Excluye:** Fines de semana y horario extendido

**Para mercados 24/7 o internacionales:**
```powershell
.\monitor_bitacora.ps1 -Continuous
```

---

## 🔧 Configuración Avanzada

### Cambiar Intervalo

```powershell
# Cada 1 minuto (agresivo)
.\monitor_bitacora.ps1 -IntervalMinutes 1

# Cada 15 minutos (conservador)
.\monitor_bitacora.ps1 -IntervalMinutes 15

# Cada 30 minutos (para conexiones lentas)
.\monitor_bitacora.ps1 -IntervalMinutes 30
```

### Modo Silencioso

```powershell
# Sin salida verbose (solo errores)
.\monitor_bitacora.ps1 -Silent
```

### Ejecutar en Startup

**Windows (Task Scheduler):**
1. Abrir Task Scheduler
2. Crear tarea básica
3. Trigger: Al iniciar sesión
4. Acción: Ejecutar programa
5. Programa: `powershell.exe`
6. Argumentos: `-File "C:\ruta\a\monitor_bitacora.ps1" -Continuous`

---

## 📱 Integración con Telegram (Próximo)

```powershell
# Notificar a Telegram cuando hay TP/SL
.\monitor_bitacora.ps1 -NotifyTelegram
```

---

## 🆘 Troubleshooting

### "Error descargando precios"
**Causa:** Sin conexión a internet o Yahoo Finance caído  
**Solución:** El monitor usa precios en cache y reintenta en la próxima iteración

### "Error actualizando bitácora"
**Causa:** Archivo Excel abierto en otra aplicación  
**Solución:** Cerrar Excel y el monitor reintentará automáticamente

### "Google Drive no disponible"
**Causa:** Drive Desktop no está sincronizando  
**Solución:** Verificar icono de Drive en bandeja del sistema, el monitor usa copia local como fallback

### Monitor se detiene al cerrar ventana
**Solución 1:** Usar servicio de Windows (Opción 2)  
**Solución 2:** Ejecutar en VPS/servidor remoto

### Alta CPU usage
**Solución:** Aumentar intervalo a 10-15 minutos

---

## 📊 Logs y Monitoreo

### Ver últimas actualizaciones:
```powershell
# Abrir bitácora
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"

# Ver resumen
python scripts\bitacora_excel.py --summary
```

### Logs del servicio (si está instalado):
```powershell
# Task Scheduler logs
Get-ScheduledTask -TaskName "H3_BitacoraMonitor" | Get-ScheduledTaskInfo
```

---

## 🎯 Workflows Recomendados

### **A. Trader Activo (Día a día)**
```powershell
# 9:00 AM - Antes del mercado
.\run_daily_h3_forward.ps1 -SendTelegram

# 9:25 AM - Iniciar monitor
.\monitor_bitacora.ps1

# Durante el día - Revisar Excel cuando quieras
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"

# 4:30 PM - Detener monitor (Ctrl+C)
```

### **B. Trader Pasivo (Set and forget)**
```powershell
# Setup inicial (solo una vez)
.\setup_monitor_service.ps1 -Action Install
.\setup_monitor_service.ps1 -Action Start

# Pipeline diario programado (Task Scheduler)
# - Ejecuta automáticamente cada día a las 5:00 PM
# - Monitor corre en background 24/7

# Revisar bitácora cuando quieras (desde móvil/web/PC)
# https://drive.google.com → Trading proyecto
```

### **C. Desarrollador / Backtesting**
```powershell
# Actualizar una sola vez para testing
.\monitor_bitacora.ps1 -Once

# Monitor rápido (cada 1 min) para desarrollo
.\monitor_bitacora.ps1 -IntervalMinutes 1 -Continuous
```

---

## 🚀 Próximas Mejoras

- [ ] Notificaciones Telegram automáticas cuando hay TP/SL
- [ ] Dashboard web en tiempo real (Streamlit)
- [ ] Alertas de email
- [ ] Integración con brokers (Interactive Brokers, Alpaca)
- [ ] Machine learning para predecir mejor timing
- [ ] Trailing stop automático

---

## 📞 Comandos Rápidos

```powershell
# Iniciar monitor
.\monitor_bitacora.ps1

# Ver estado (una vez)
.\monitor_bitacora.ps1 -Once

# Abrir bitácora
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"

# Resumen de predicciones
python scripts\bitacora_excel.py --summary

# Actualizar precios manualmente
python scripts\bitacora_excel.py --update

# Pipeline completo
.\run_daily_h3_forward.ps1 -SendTelegram

# Detener monitor
Ctrl + C
```

---

**Última actualización:** 6 de Noviembre, 2025  
**Versión:** 1.0.0  
**Estado:** ✅ OPERATIVO
