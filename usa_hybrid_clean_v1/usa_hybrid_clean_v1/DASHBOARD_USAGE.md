# Dashboard - Guía de Uso

## Iniciar el Sistema

### Paso 1: Iniciar el servidor API (puerto 5001)

```powershell
# Opción 1: Usando force_port_5001.ps1 (recomendado)
.\force_port_5001.ps1

# Opción 2: Manual con modo estricto
$env:STRICT_PORT="1"
python dashboard_api.py
```

El servidor debe mostrar:
```
[INFO] STRICT_PORT: iniciando en puerto fijo 5001.
* Running on http://127.0.0.1:5001
```

### Paso 2: Servir el dashboard por HTTP (puerto 8080)

**IMPORTANTE:** El dashboard DEBE ser servido por HTTP, NO abrirlo como `file://` debido a restricciones CORS.

```powershell
.\serve_dashboard.ps1
```

El servidor mostrará:
```
[INFO] Dashboard disponible en: http://localhost:8080/intraday_dashboard.html
```

### Paso 3: Abrir el dashboard en el navegador

Ir a: **http://localhost:8080/intraday_dashboard.html**

## Funcionalidad de Botones

### Panel "Control del sistema"

#### Monitor Intradía
- **▶ Iniciar monitor**: Inicia el monitoreo automático cada N segundos
- **■ Detener monitor**: Detiene el monitor activo
- Estado se actualiza automáticamente cada 15 segundos

#### Limpieza de Workspace (Soft)
- **🧪 Soft Clean (DryRun)**: Muestra qué archivos se eliminarían SIN borrar nada
- **🧹 Soft Clean (Real)**: Ejecuta limpieza real (requiere confirmación)
- La salida se muestra en el área de texto debajo de los botones

### Panel Principal

#### Botones de Acción
- **🤖 Predicciones Mañana**: Ejecuta pipeline completo (daily + forward) para generar plan T+1
- **📡 Refrescar Buffers**: Descarga datos intradía para los tickers del plan actual
- **🔄 Recargar**: Actualiza todos los KPIs y gráficas

## Verificación de Endpoints

Todos los endpoints están funcionando correctamente:

```powershell
# Verificar estado monitor
python -c "import urllib.request,json; print(json.loads(urllib.request.urlopen('http://127.0.0.1:5001/api/status').read()))"

# Probar iniciar monitor
python -c "import urllib.request,json; req = urllib.request.Request('http://127.0.0.1:5001/api/monitor/start', data=json.dumps({'interval_seconds':300}).encode(), headers={'Content-Type':'application/json'}, method='POST'); print(json.loads(urllib.request.urlopen(req).read()))"

# Probar detener monitor
python -c "import urllib.request,json; req = urllib.request.Request('http://127.0.0.1:5001/api/monitor/stop', data=b'{}', headers={'Content-Type':'application/json'}, method='POST'); print(json.loads(urllib.request.urlopen(req).read()))"

# Probar clean (dry run)
python -c "import urllib.request,json; req = urllib.request.Request('http://127.0.0.1:5001/api/clean/soft', data=json.dumps({'dry_run':True}).encode(), headers={'Content-Type':'application/json'}, method='POST'); print(json.loads(urllib.request.urlopen(req).read())['ok'])"
```

## Troubleshooting

### Error: "Access to fetch blocked by CORS policy"
**Causa**: Dashboard abierto como `file://` en lugar de `http://`  
**Solución**: Usar `serve_dashboard.ps1` para servir por HTTP

### Error: "Failed to fetch" o "Connection refused"
**Causa**: Servidor API no está corriendo  
**Solución**: Iniciar `dashboard_api.py` o usar `force_port_5001.ps1`

### Error: "btnShowForward is not defined"
**Causa**: JavaScript antiguo con referencias a botones eliminados  
**Solución**: Ya corregido en última versión del HTML

### Botones no responden
1. Abrir consola del navegador (F12 → Console)
2. Verificar errores de JavaScript
3. Confirmar que ambos servidores estén corriendo (API:5001 + HTTP:8080)

## Arquitectura

```
┌─────────────────────┐
│   Navegador         │
│  localhost:8080     │
│  intraday_dashboard │
└──────────┬──────────┘
           │ HTTP
           ▼
┌─────────────────────┐
│   serve_dashboard   │
│   (Python HTTP)     │
│   Puerto 8080       │
└─────────────────────┘

┌──────────┐
│ Navegador│ ──fetch()──▶ ┌──────────────┐
└──────────┘              │dashboard_api │
                          │ Flask API    │
                          │ Puerto 5001  │
                          └──────────────┘
```

## Endpoints Disponibles

- `GET /api/status` - Estado general y monitor
- `POST /api/monitor/start` - Iniciar monitor
- `POST /api/monitor/stop` - Detener monitor
- `POST /api/clean/soft` - Limpieza workspace
- `POST /api/pipeline/run_forward` - Pipeline completo
- `POST /api/plan/download_intraday` - Descarga intradía
- `GET /api/bitacora` - Datos de bitácora
- `GET /api/equity` - Curva de equity
- `GET /api/calendar/today` - Calendario día actual
- `GET /api/calendar/upcoming` - Próximos eventos

## Scripts Útiles

- `serve_dashboard.ps1` - Servidor HTTP para dashboard
- `force_port_5001.ps1` - Inicia API liberando puerto si está ocupado
- `run_dashboard_api.ps1` - Lanzador estable del API
- `check_setup.ps1` - Verifica instalación completa
