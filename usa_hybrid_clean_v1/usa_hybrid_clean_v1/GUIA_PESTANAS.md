# 📋 GUÍA: Cómo Ver las Pestañas del Dashboard

## ✅ CONFIRMADO: Las pestañas están implementadas

He verificado el código y **las 4 pestañas están correctamente implementadas** en el dashboard:

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 Trade Monitor  │  ⚖️ Plan Comparison  │  📋 Historial  │  📈 Reporte Historico  │
└─────────────────────────────────────────────────────────────────┘
```

## 🔍 Verificación Técnica Completada

- ✅ **HTML generado:** 63,501 caracteres
- ✅ **Botones tab-btn:** 13 encontrados  
- ✅ **4 Pestañas presentes:**
  - `tab0` - 📊 Trade Monitor
  - `tab1` - ⚖️ Plan Comparison
  - `tab2` - 📋 Historial
  - `tab3` - 📈 Reporte Historico
- ✅ **CSS aplicado:** Clase `.tabs` con estilos
- ✅ **JavaScript:** Función `switchTab()` implementada

## 🎯 Cómo Acceder al Dashboard

1. **Abrir en navegador:**
   ```
   http://localhost:8050/
   ```

2. **Si no ves las pestañas, limpia el cache:**
   - Windows/Linux: `Ctrl + Shift + R` o `Ctrl + F5`
   - Mac: `Cmd + Shift + R`

3. **Ubicación visual:**
   ```
   ┌──────────────────────────────────────────────┐
   │  TRADE DASHBOARD                              │
   │  Estado del Mercado: [OPEN/CLOSED]           │
   ├──────────────────────────────────────────────┤
   │                                               │
   │  [📊 Trade Monitor]  [⚖️ Plan Comparison]    │
   │  [📋 Historial]      [📈 Reporte Historico]  │  ← AQUÍ ESTÁN LAS PESTAÑAS
   │                                               │
   ├──────────────────────────────────────────────┤
   │                                               │
   │  [Contenido de la pestaña activa]           │
   │                                               │
   └──────────────────────────────────────────────┘
   ```

## 📊 Contenido de Cada Pestaña

### Tab 0: 📊 Trade Monitor (Activa por defecto)
- Muestra trades activos en tiempo real
- Estadísticas: PnL, Win Rate, Exposición
- Cards con información de cada trade

### Tab 1: ⚖️ Plan Comparison  
- Comparación STANDARD vs PROBWIN_55
- Tabla resumen con posiciones
- Detalles expandibles por ticker

### Tab 2: 📋 Historial
- **Todos los trades cerrados** (20 trades actualmente)
- Grid con información detallada
- Exit reason (TP/SL), PnL, fechas

### Tab 3: 📈 Reporte Historico
- **4 vistas diferentes:**
  - Agrupado por Fecha
  - Detalles y Duración
  - Timeline Visual
  - Comparativa por Plan

## 🔧 Diagnóstico Si No Se Ven

### 1. Verificar que el servidor está corriendo
```powershell
Get-Process python
```

### 2. Verificar que el puerto 8050 está escuchando
```powershell
netstat -ano | findstr :8050
```

### 3. Abrir consola del navegador (F12)
Buscar errores en la consola JavaScript

### 4. Verificar que el CSS está cargando
En la consola del navegador:
```javascript
document.querySelectorAll('.tab-btn').length  // Debe ser 4
```

### 5. Forzar click programático
En la consola del navegador:
```javascript
switchTab(2)  // Cambia a Historial
switchTab(3)  // Cambia a Reporte Historico
```

## 📸 ¿Qué Deberías Ver?

Cuando abres http://localhost:8050 debes ver:

1. **Header azul** con título "TRADE DASHBOARD"
2. **Barra de estado** del mercado (verde si abierto, rojo si cerrado)
3. **4 BOTONES GRANDES** en fila horizontal:
   - Fondo gris claro para inactivos
   - Fondo blanco + borde azul inferior para el activo
4. **Área de contenido** debajo que cambia al hacer clic

## ✅ Acción Recomendada

1. Abre: http://localhost:8050/
2. Presiona: `Ctrl + Shift + R` (hard refresh)
3. Verifica que ves los 4 botones de pestañas
4. Haz clic en cada una para verificar que cambian

## 📞 Si Aún No Funciona

Proporciona la siguiente información:
- Navegador y versión (Chrome, Firefox, Edge, etc.)
- Captura de pantalla de lo que ves
- Errores en la consola del navegador (F12 → Console)

---

**Servidor activo en:** http://localhost:8050  
**Pestañas implementadas:** ✅ Sí (4/4)  
**Última verificación:** 2026-02-02
