# ✅ BITÁCORA H3 - CONFIGURADA EN GOOGLE DRIVE

## 📍 Ubicación
```
G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx
```

## 🎯 Estado: ACTIVA Y FUNCIONANDO

La bitácora se actualiza **automáticamente** en Google Drive cada vez que ejecutas los scripts.

---

## 📊 Comandos Disponibles

### 1. Ver Resumen Actual
```powershell
python scripts\bitacora_excel.py --summary
```
Muestra estadísticas: Total predicciones, Activas, Win Rate

### 2. Actualizar Precios
```powershell
python scripts\bitacora_excel.py --update
```
Actualiza precios actuales, P&L y progreso hacia TP

### 3. Agregar Nuevo Plan
```powershell
python scripts\bitacora_excel.py --add-plan reports\forecast\2025-11\trade_plan_tth.csv
```
Registra nuevas predicciones desde el plan de trading

### 4. Abrir en Excel
```powershell
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"
```
Abre el archivo directamente desde Drive

---

## 🚀 Pipeline Diario Automatizado

El pipeline **ya está integrado** para actualizar la bitácora automáticamente:

```powershell
.\run_daily_h3_forward.ps1 -SendTelegram -RecentDays 3 -MaxOpen 3 -Capital 10000
```

**Qué hace el pipeline:**
1. ✅ Descarga precios actualizados
2. ✅ Genera features y predicciones H3
3. ✅ Aplica modelo TTH
4. ✅ Crea plan de trading
5. ✅ **Actualiza bitácora en Google Drive** ⬅️ NUEVO
6. ✅ Envía plan a Telegram

**La bitácora se actualiza automáticamente en cada ejecución.**

---

## 📱 Acceso desde Cualquier Dispositivo

### Desde PC:
- Abrir carpeta: `G:\Mi unidad\Trading proyecto\`
- Doble clic en archivo Excel

### Desde Navegador:
1. Ir a: https://drive.google.com
2. Buscar: "Trading proyecto"
3. Abrir: `H3_BITACORA_PREDICCIONES.xlsx`

### Desde Móvil:
1. App Google Drive
2. Buscar: "Trading proyecto"
3. Abrir archivo (ver o editar)

### Convertir a Google Sheets (Opcional):
- Clic derecho → "Abrir con Google Sheets"
- Ventaja: Editable desde móvil/tablet
- Se actualiza cada vez que ejecutas los scripts

---

## 📈 Información Rastreada

**Por cada predicción:**
- Ticker, fecha entrada, precio entrada
- TP/SL targets y porcentajes
- Precio actual **actualizado automáticamente**
- P&L actual (USD y %)
- Progreso hacia TP (%)
- Días transcurridos
- Estado: ACTIVA / TP_HIT / SL_HIT / EXPIRED
- Sector, probabilidad, ETTH, score TTH

**Hoja de Resumen:**
- Total predicciones
- Predicciones activas
- Win Rate (%)
- P&L promedio
- Mejores y peores trades

---

## 🎨 Formato Visual

**Códigos de color automáticos:**
- 🟢 **Verde** → Trades ganadores (TP alcanzado)
- 🔴 **Rojo** → Trades perdedores (SL alcanzado)
- 🟡 **Amarillo** → Trades activos (en progreso)

---

## 🔄 Workflow Diario Recomendado

### Mañana (9:00 AM):
```powershell
# Ver estado de predicciones activas
python scripts\bitacora_excel.py --update
python scripts\bitacora_excel.py --summary
```

### Después del Cierre (5:00 PM):
```powershell
# Ejecutar pipeline completo
.\run_daily_h3_forward.ps1 -SendTelegram -RecentDays 3 -MaxOpen 3 -Capital 10000

# El pipeline hace TODO automáticamente:
# - Genera nuevas predicciones
# - Actualiza bitácora en Drive
# - Envía plan a Telegram
```

### Antes de Dormir (10:00 PM):
```powershell
# Revisar progreso en Excel desde Drive
Invoke-Item "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"

# O desde navegador/móvil:
# https://drive.google.com → Trading proyecto → H3_BITACORA_PREDICCIONES.xlsx
```

---

## ⚙️ Configuración Técnica

**Ruta configurada en el script:**
```python
# scripts/bitacora_excel.py (línea 13-18)
DRIVE_PATH = r"G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"
```

**Detección automática:**
- Si Google Drive está disponible → Usa `G:\Mi unidad\Trading proyecto\`
- Si Drive no disponible → Fallback a `reports\` (local)

**Sincronización:**
- Google Drive Desktop sincroniza automáticamente en segundo plano
- No requiere comandos manuales
- Los cambios se reflejan en línea en segundos

---

## 🎯 Ventajas de Esta Configuración

✅ **Acceso desde cualquier lugar** (PC, navegador, móvil)  
✅ **Siempre actualizada** (sincronización automática)  
✅ **No pierdas datos** (backup en nube)  
✅ **Compartible** (puedes enviar link a otros)  
✅ **Sin duplicados** (un solo archivo maestro)  
✅ **Integrada al pipeline** (cero esfuerzo manual)  

---

## 🆘 Troubleshooting

### "No se encuentra G:\Mi unidad"
**Solución:**
- Verificar que Google Drive Desktop está activo (icono en bandeja)
- Abrir Google Drive y esperar que termine de sincronizar
- Verificar letra de unidad (puede ser diferente): `G:`, `F:`, etc.

### "Error al actualizar bitácora"
**Solución:**
```powershell
# Verificar configuración
.\verificar_bitacora_drive.ps1

# O manualmente:
Test-Path "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"
```

### "Archivo está en uso"
**Solución:**
- Cerrar Excel si está abierto
- Esperar unos segundos y reintentar
- Google Drive sincronizará automáticamente cuando esté disponible

---

## 📞 Próximos Pasos

1. ✅ **LISTO:** Bitácora configurada en Drive
2. ✅ **LISTO:** Scripts actualizando automáticamente
3. ✅ **LISTO:** Integración con pipeline diario

**Todo está configurado y funcionando.** 🎉

Solo ejecuta el pipeline diario y revisa tu bitácora desde cualquier dispositivo:
```powershell
.\run_daily_h3_forward.ps1 -SendTelegram
```

---

**Última actualización:** 5 de Noviembre, 2025  
**Archivo:** `G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx`  
**Estado:** ✅ OPERATIVO
