# Dashboard USA Hybrid Clean - Resumen de Mejoras

**Fecha:** 23 Noviembre 2025  
**Estado:** Completado y funcional en puerto 5001

---

## 🎯 Objetivos Alcanzados

1. ✅ **Pipeline Forward Integrado:** Botón único "Predicciones Mañana" ejecuta daily + forward desde el dashboard.
2. ✅ **Descarga Intradía Automatizada:** Botón "Refrescar Buffers" actualiza datos intradía para tickers del plan.
3. ✅ **Rediseño UI Profesional:** Glassmorphism, tipografía Inter, sistema de colores coherente, animaciones suaves.
4. ✅ **Puerto 5001 Forzado:** Modo estricto STRICT_PORT + script `force_port_5001.ps1` para liberar/arrancar.
5. ✅ **Detección Dinámica API:** Frontend detecta puerto activo vía `api_port.json` y escaneo fallback.
6. ✅ **Endpoints Extendidos:** Meta port, plan/download_intraday, pipeline/run_forward con daily_step.

---

## 📂 Archivos Modificados/Creados

### Backend (`dashboard_api.py`)
**Cambios clave:**
- **Puerto dinámico con modo estricto:** Variable `STRICT_PORT` para forzar 5001 y abortar si ocupado.
- **Endpoint `/api/meta/port`:** Expone puerto activo para detección frontend.
- **Endpoint `/api/plan/download_intraday`:** Ejecuta `download_intraday_for_plan.py` con parámetros JSON (interval, days, max_workers, etc.).
- **Extensión `/api/pipeline/run_forward`:** Parámetro `run_daily_first` ejecuta daily pipeline antes de forward; abort si daily falla.
- **Helper `_run_python_script()`:** Función genérica para ejecutar scripts Python vía subprocess con captura stdout/stderr.
- **Persistencia `outputs/api_port.json`:** Escribe puerto elegido + timestamp para descubrimiento frontend.

**Funciones añadidas:**
```python
@app.get("/api/meta/port")
def api_meta_port():
    # Devuelve puerto activo leído desde api_port.json

@app.post("/api/plan/download_intraday")
def api_plan_download_intraday():
    # Ejecuta download_intraday_for_plan.py con argumentos JSON
```

**Configuración puerto:**
```python
# Variables de entorno
API_PORT=5001          # Puerto preferido (default)
STRICT_PORT=1          # Modo estricto: aborta si puerto ocupado
```

---

### Frontend (`intraday_dashboard.html`)
**Cambios clave:**
- **Rediseño completo CSS:**
  - Paleta: `--accent: #3dbff7`, `--accent-alt: #6366f1`, gradientes, glassmorphism.
  - Tipografía: Inter (Google Fonts), pesos 400/500/600/700.
  - KPI uniformes: min-height 180px, spacing consistente.
  - Tablas: zebra, sticky headers, hover refinado.
  - Botones: estados hover/active, spinner integrado con `::after`.
  - Layout: full-width sin márgenes laterales del body, padding interno en container.
  - Custom scrollbar: gradiente accent con borde bg-card.

- **Botón "Predicciones Mañana":**
  - Envía `run_daily_first: true` a `/api/pipeline/run_forward`.
  - Muestra loader global "Generando predicciones…".
  - Alert con resultado (daily OK, plan generado o razón vacía).

- **Botón "Refrescar Buffers":**
  - Fuerza redetección de puerto antes de llamar (await detectApiBase()).
  - POST a `/api/plan/download_intraday` con parámetros predefinidos.
  - Tras éxito: relanza `loadAll()` para actualizar KPI de buffers.

- **Detección dinámica puerto (`detectApiBase()`):**
  1. Intenta leer `outputs/api_port.json`.
  2. Escanea puertos 5001–5005 con `/api/meta/port` (timeout 900ms).
  3. Fallback con `/api/status` si meta/port no responde.
  4. Fallback final a 5001 para mensajes de error.

- **Función `callApi()` mejorada:**
  - Catch error de red → redetección automática y reintento una vez.
  - Diferencia error de red vs HTTP vs parse JSON.
  - Mensajes claros con API_BASE actual (no hardcodeado a 5001).

- **Overlay ayuda API:**
  - Se muestra si no se detecta servidor en ningún puerto.
  - Instrucciones paso a paso para arrancar `dashboard_api.py` o usar script.
  - Botón dismiss que reinicia detección.

- **Layout editable persistente:**
  - Toggle "Editar layout" muestra controles en cada tarjeta.
  - Ajusta columnas (span), altura (px), ancho sidebar.
  - Guarda en localStorage (`dashboardLayoutV1`).
  - Botón "Reset" limpia preferencias.

---

### Script PowerShell (`force_port_5001.ps1`)
**Propósito:** Libera puerto 5001 (netstat + taskkill) y arranca servidor con STRICT_PORT=1.

**Parámetros:**
- `-Force`: Omite confirmación antes de matar proceso.
- `-Background`: Lanza en segundo plano (Start-Process + job de captura).
- `-PythonExe`: Ruta custom Python (default `python`).
- `-WorkingDir`: Directorio de trabajo (default carpeta del script).
- `-LogDir`: Carpeta logs (default `logs`, se crea si no existe).

**Flujo:**
1. Ejecuta `netstat -ano | findstr :5001` para detectar PID.
2. Si ocupado: `taskkill /PID <PID> /F` (opcional confirmación).
3. Valida existencia `dashboard_api.py`.
4. Setea `$env:API_PORT=5001`, `$env:STRICT_PORT=1`.
5. Genera log `logs/dashboard_api_YYYYMMDD_HHMMSS.log`.
6. Lanza Python:
   - Foreground: salida en consola + archivo (Tee-Object).
   - Background: proceso desacoplado + job captura salida en log.

**Uso típico:**
```powershell
# Foreground interactivo (recomendado primera vez)
powershell -ExecutionPolicy Bypass -File .\force_port_5001.ps1 -Force

# Background con logs
powershell -ExecutionPolicy Bypass -File .\force_port_5001.ps1 -Force -Background
Get-Content -Wait .\logs\dashboard_api_<TIMESTAMP>.log
```

---

## 🛠️ Flujo Operativo Típico

### 1. Arranque del servidor
```powershell
# Opción A: Script automático (recomendado)
powershell -ExecutionPolicy Bypass -File .\force_port_5001.ps1 -Force

# Opción B: Manual
$env:API_PORT=5001; $env:STRICT_PORT=1; python -u dashboard_api.py
```

### 2. Apertura del dashboard
- Navegar a `intraday_dashboard.html` en navegador.
- Si lo abres con `file://`, servir con HTTP simple para permitir fetch de `outputs/api_port.json`:
  ```powershell
  python -m http.server 8088
  # Luego: http://127.0.0.1:8088/intraday_dashboard.html
  ```
- El dashboard detecta automáticamente el puerto (5001 o alterno) y muestra overlay de ayuda si no responde.

### 3. Uso de botones principales
**"Predicciones Mañana"** (Pipeline completo: Daily + Forward)
- Confirma: "¿Generar predicciones y plan para mañana?"
- Ejecuta:
  1. `run_daily_pipeline.ps1` (genera forecast_with_patterns_tth.csv).
  2. `run_daily_h3_forward.ps1` (filtra y genera trade_plan_tth.csv).
- Resultado:
  - Alert con estado daily (OK/ERROR).
  - Plan generado o razón vacía (filtros).
  - Historial en `outputs/forward_pipeline_history.json`.

**"Refrescar Buffers"** (Descarga intradía para plan)
- Confirma: "¿Descargar intradía para tickers del trade plan?"
- Ejecuta `download_intraday_for_plan.py` con:
  - Interval: 5m
  - Days: 1
  - Max workers: 1
  - Skip recent: False
  - Save history: False
- Salidas:
  - `outputs/intraday_metrics.csv` (latencias, smart cache hits).
  - `outputs/intraday_missing.csv` (tickers fallidos).
  - Buffers parquet y CSV.
- Tras éxito: KPI "Buffers" se actualiza con frescura (<10 min).

**"Actualizar"**
- Refresca bitácora, equity, progreso, calendario, health.
- Auto-refresh configurable (Manual / 30s / 60s / 5min).

---

## 🔍 Diagnóstico y Verificación

### Confirmar servidor activo
```powershell
# Status básico
python -c "import urllib.request,ssl;print(urllib.request.urlopen('http://127.0.0.1:5001/api/status',context=ssl.create_default_context()).read().decode()[:300])"

# Puerto detectado
python -c "import urllib.request,ssl;print(urllib.request.urlopen('http://127.0.0.1:5001/api/meta/port',context=ssl.create_default_context()).read().decode())"

# Listar endpoints
python -c "import urllib.request,ssl,json;r=urllib.request.urlopen('http://127.0.0.1:5001/api/meta/routes',context=ssl.create_default_context());data=json.loads(r.read());print('\n'.join([f\"{rt['rule']} [{','.join(rt['methods'])}]\" for rt in data['routes'][:20]]))"
```

### Probar endpoints clave desde terminal
```powershell
# Run forward completo (daily + forward)
python -c "import json,urllib.request,ssl;data=json.dumps({'send_telegram':False,'recent_days':3,'max_open':3,'capital':1000,'run_daily_first':True}).encode();req=urllib.request.Request('http://127.0.0.1:5001/api/pipeline/run_forward',data=data,headers={'Content-Type':'application/json'});print(urllib.request.urlopen(req,context=ssl.create_default_context()).read().decode()[:800])"

# Descarga intradía
python -c "import json,urllib.request,ssl;data=json.dumps({'interval':'5m','days':1,'max_workers':1}).encode();req=urllib.request.Request('http://127.0.0.1:5001/api/plan/download_intraday',data=data,headers={'Content-Type':'application/json'});print(urllib.request.urlopen(req,context=ssl.create_default_context()).read().decode()[:600])"
```

### Identificar proceso en puerto 5001
```powershell
netstat -ano | findstr :5001
# Buscar PID en columna final de línea LISTENING

tasklist /FI "PID eq <PID>" /FO LIST
# Ver detalles del proceso

wmic process where "ProcessId=<PID>" get CommandLine,ProcessId
# Ver comando completo
```

### Logs del servidor
Si se usó el script con `-Background` o logging habilitado:
```powershell
Get-Content -Wait .\logs\dashboard_api_<TIMESTAMP>.log
```

---

## 🎨 Guía de Estilos (CSS)

**Paleta principal:**
```css
--bg: #0b0f18;              /* Background oscuro principal */
--bg-soft: #121a26;         /* Background secundario */
--bg-card: #0e1622;         /* Cards opacas */
--bg-glass: rgba(17,27,39,0.55); /* Glassmorphism */
--accent: #3dbff7;          /* Azul cian (principal) */
--accent-alt: #6366f1;      /* Indigo (secundario) */
--text: #e2e8f0;            /* Texto claro */
--muted: #94a3b8;           /* Texto atenuado */
--danger: #fb6e6e;          /* Rojo alertas */
--ok: #4ade80;              /* Verde éxito */
--warn: #facc15;            /* Amarillo warning */
```

**Espaciado vertical:**
- Bloques principales: `margin-top: 2.0rem` (var `--section-block`).
- KPI cards: `min-height: 180px`.
- Tablas: `margin-top: 0.4rem` primera, `1rem` subsiguientes.

**Botones:**
- Border radius: 14px.
- Padding: `0.55rem 1rem`.
- Font size: 0.78rem, weight 500.
- Hover: `translateY(-2px)`, box-shadow elevado, border más brillante.
- Loading: `::after` con spinner circular.

**Cards:**
- Border radius: 18px.
- Background: glassmorphism con blur(18px) saturate(170%).
- Shadow: `var(--shadow-deep)` = múltiples capas.
- `::after` overlay con gradiente accent sutil.

**Tipografía:**
- Familia: `'Inter', system-ui, -apple-system, ...`.
- H1 header: 1.1rem, weight 600, gradient clip accent.
- H2 cards: 0.95rem, weight 600.
- Subtítulos: 0.8rem, color muted.

**Extensión futura:**
- Agregar nuevas tarjetas: usar `data-card-id` en `.card` y `.grid`.
- Botones adicionales: `.btn` con `.icon` y span para texto.
- KPIs: estructura `.kpi-card > .kpi-value + .kpi-label`.
- Layout editable: el sistema de controles detecta cards con `data-card-id` automáticamente.

---

## 📝 Checklist Pendiente / Mejoras Futuras

- [ ] **Responsive fine-tuning:** Ajustar breakpoints <900px y <600px para tablets/móviles.
- [ ] **Tests unitarios backend:** Añadir pytest para endpoints críticos (run_forward, download_intraday).
- [ ] **Documentación API OpenAPI/Swagger:** Exponer `/api/docs` con especificación completa.
- [ ] **Rotación de logs:** Script para comprimir/archivar logs antiguos en `logs/`.
- [ ] **Auto-restart del servidor:** Watchdog para reiniciar dashboard_api.py si cae (opcional systemd/supervisor en Linux, nssm en Windows).
- [ ] **Notificaciones Telegram:** Integrar alertas a canal privado tras pipeline forward (usar flag `send_telegram` ya presente).
- [ ] **Dashboard móvil dedicado:** Variante minimalista con KPIs esenciales y botones grandes.
- [ ] **Cache frontend:** Service Worker para offline-first en lecturas (bitácora, equity) si red falla.
- [ ] **Alertas en tiempo real:** WebSocket o SSE para push de eventos (nuevo trade abierto, TP hit, buffer stale).

---

## 🚀 Comandos Rápidos de Referencia

```powershell
# Arrancar servidor forzando 5001
powershell -ExecutionPolicy Bypass -File .\force_port_5001.ps1 -Force

# Probar endpoint status
python -c "import urllib.request,ssl;print(urllib.request.urlopen('http://127.0.0.1:5001/api/status',context=ssl.create_default_context()).read().decode()[:200])"

# Ejecutar pipeline forward manual
python -c "import json,urllib.request,ssl;data=json.dumps({'run_daily_first':True,'recent_days':3,'max_open':3,'capital':1000}).encode();req=urllib.request.Request('http://127.0.0.1:5001/api/pipeline/run_forward',data=data,headers={'Content-Type':'application/json'});print(urllib.request.urlopen(req,context=ssl.create_default_context()).read().decode()[:600])"

# Ver logs en tiempo real (si background)
Get-Content -Wait .\logs\dashboard_api_<TIMESTAMP>.log

# Matar servidor manualmente (si no responde)
netstat -ano | findstr :5001
taskkill /PID <PID> /F

# Servir dashboard vía HTTP (para fetch relativo de api_port.json)
python -m http.server 8088
# Navegar: http://127.0.0.1:8088/intraday_dashboard.html
```

---

## 📊 Estado Final del Sistema

| Componente | Estado | Notas |
|---|---|---|
| **Backend API** | ✅ Operativo (puerto 5001) | Modo STRICT_PORT activo |
| **Frontend Dashboard** | ✅ Funcional | Detección dinámica puerto, layout editable |
| **Pipeline Forward** | ✅ Integrado | Daily + Forward desde botón único |
| **Descarga Intradía** | ✅ Automatizado | Botón refrescar buffers, métricas capturadas |
| **Script force_port_5001** | ✅ Creado y probado | Libera puerto y arranca con logging |
| **Endpoint /api/meta/port** | ✅ Disponible | Facilita detección frontend |
| **Persistencia api_port.json** | ✅ Habilitado | Escritura automática tras bind |
| **Rediseño UI** | ✅ Completado | Glassmorphism, Inter, KPIs uniformes |
| **Tests manuales** | ✅ Pasados | Buffers refresh OK, servidor responde 200 |
| **Responsive** | ⚠️ Pendiente fine-tuning | Breakpoints básicos presentes, ajustar tablet/móvil |

---

## 🎓 Lecciones Aprendidas / Notas Técnicas

1. **PowerShell variable escaping:** `$_` en strings entre comillas dobles debe delimitarse como `$($_.Exception.Message)` para evitar confusión con drive paths.

2. **CORS preflight:** Flask-CORS responde OPTIONS automáticamente; logs muestran doble request (OPTIONS + GET/POST) como esperado.

3. **Detección de puerto robusta:** Escaneo con timeout corto (900ms) evita bloqueos; priorizar `/api/meta/port` antes de `/api/status` para velocidad.

4. **Subprocess en Windows:** `subprocess.run(..., shell=False)` más seguro; usar lista de args en vez de string para evitar injection.

5. **Glassmorphism performance:** `backdrop-filter: blur()` puede ser pesado en mobile; considerar fallback sin blur para dispositivos débiles.

6. **Layout editable localStorage:** Guardar como JSON con versión (`dashboardLayoutV1`) permite migraciones futuras si estructura cambia.

7. **STRICT_PORT modo:** Útil para ambientes CI/CD donde puerto fijo es mandatorio; fallback flexible mejor para dev local.

8. **Script PowerShell background jobs:** `Start-Job` + captura stdout/stderr requiere polling manual; para producción usar nssm o Task Scheduler con redirects nativos.

---

**Resumen ejecutivo:** El dashboard está completamente operativo en puerto 5001 con todas las funcionalidades integradas (predicciones automáticas, descarga intradía, rediseño profesional). Servidor Flask estable, frontend detecta puerto dinámicamente, script `force_port_5001.ps1` simplifica arranque. Listo para uso diario; responsive fine-tuning y alertas en tiempo real son mejoras futuras opcionales.

---

*Documento generado automáticamente tras completar integración dashboard v1.1 - USA Hybrid Clean Trading System.*
