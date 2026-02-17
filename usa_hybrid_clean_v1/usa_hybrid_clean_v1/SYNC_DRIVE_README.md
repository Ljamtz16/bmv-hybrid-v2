# 📊 Sincronización de Bitácora H3 con Google Drive

Este documento explica cómo mantener tu bitácora de predicciones H3 sincronizada con Google Drive para acceso en línea.

## 🎯 Opciones Disponibles

### **Opción 1: Google Drive Desktop** (RECOMENDADA ✅)

La forma más simple. Requiere tener Google Drive Desktop instalado.

#### Setup Inicial:
1. **Instalar Google Drive Desktop** (si no lo tienes):
   - Descargar: https://www.google.com/drive/download/
   - Instalar y hacer login con tu cuenta de Google
   - Esperar a que sincronice

2. **Primera sincronización:**
   ```powershell
   # Detectar y copiar automáticamente
   .\sync_bitacora_to_gdrive.ps1
   
   # O especificar ruta manualmente
   .\sync_bitacora_to_gdrive.ps1 -GDrivePath "C:\Users\TuUsuario\Google Drive"
   
   # Configurar como ubicación permanente
   .\sync_bitacora_to_gdrive.ps1 -Auto
   ```

3. **Integrar en pipeline diario:**
   ```powershell
   # Ejecutar pipeline con sincronización automática
   .\run_daily_h3_forward.ps1 -SendTelegram -SyncDrive
   ```

#### Ventajas:
- ✅ Setup de 5 minutos
- ✅ Sincronización automática en segundo plano
- ✅ No requiere credenciales de API
- ✅ Funciona offline (sincroniza cuando vuelve internet)

---

### **Opción 2: Google Drive API** (Avanzada)

Para sincronización programática directa a Drive sin Desktop app.

#### Setup Inicial:
1. **Instalar dependencias:**
   ```powershell
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

2. **Crear proyecto en Google Cloud:**
   - Ir a: https://console.cloud.google.com/
   - Crear nuevo proyecto: "H3 Trading Bot"
   - Habilitar **Google Drive API**
   - Crear credenciales OAuth 2.0:
     - Tipo: Desktop app
     - Descargar JSON → renombrar a `credentials.json`
     - Colocar en la raíz del proyecto

3. **Primera autenticación:**
   ```powershell
   python scripts\sync_bitacora_to_drive.py
   # Se abrirá navegador para autorizar
   # Aceptar permisos
   # El token se guardará en token_gdrive.pickle
   ```

4. **Uso:**
   ```powershell
   # Subir/actualizar bitácora manualmente
   python scripts\sync_bitacora_to_drive.py
   
   # Integrar en pipeline (agregar al final de run_daily_h3_forward.ps1)
   python scripts\sync_bitacora_to_drive.py
   ```

#### Ventajas:
- ✅ No requiere Drive Desktop instalado
- ✅ Funciona en servidores/VPS sin GUI
- ✅ Control total sobre permisos y carpetas
- ✅ Puede obtener link compartible automáticamente

#### Desventajas:
- ⚠️ Setup más complejo (requiere Google Cloud Console)
- ⚠️ Token expira cada cierto tiempo (requiere re-autenticación)

---

### **Opción 3: Ruta Directa en Drive**

Si tienes Drive Desktop, puedes hacer que la bitácora se cree directamente allí.

#### Setup:
1. **Configurar variable de entorno:**
   ```powershell
   # PowerShell (persistente)
   [System.Environment]::SetEnvironmentVariable(
       "H3_BITACORA_PATH", 
       "C:\Users\TuUsuario\Google Drive\H3_Trading\H3_BITACORA_PREDICCIONES.xlsx",
       "User"
   )
   
   # O agregar a .env
   echo H3_BITACORA_PATH="C:\Users\TuUsuario\Google Drive\H3_Trading\H3_BITACORA_PREDICCIONES.xlsx" >> .env
   ```

2. **Crear bitácora en Drive:**
   ```powershell
   # Los scripts usarán automáticamente la ruta de Drive
   python scripts\bitacora_excel.py --init
   python scripts\bitacora_excel.py --add-plan reports\forecast\2025-11\trade_plan_tth.csv
   ```

#### Ventajas:
- ✅ No requiere copias/sincronizaciones
- ✅ Siempre actualizada en Drive
- ✅ Un solo archivo (no duplicados)

---

## 🔄 Workflows Recomendados

### **A. Pipeline Diario con Sincronización**
```powershell
# Ejecutar pipeline completo + sincronizar Drive
.\run_daily_h3_forward.ps1 -SendTelegram -SyncDrive -RecentDays 3 -MaxOpen 3 -Capital 10000
```

### **B. Actualización Manual de Precios**
```powershell
# Solo actualizar precios en la bitácora y sincronizar
python scripts\bitacora_excel.py --update
.\sync_bitacora_to_gdrive.ps1
```

### **C. Scheduler Automático**
```powershell
# Configurar ejecución diaria a las 17:00 (después del cierre)
# Editar setup_scheduler.ps1 y cambiar la línea del comando a:
-Action (New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-File `"$PSScriptRoot\run_daily_h3_forward.ps1`" -SendTelegram -SyncDrive")
```

---

## 📱 Compartir Bitácora en Línea

### **Obtener Link Compartible:**
1. Abrir Google Drive en navegador
2. Buscar: `H3_Trading\H3_BITACORA_PREDICCIONES.xlsx`
3. Clic derecho → **Compartir**
4. **Cambiar acceso** → "Cualquier persona con el enlace"
5. Rol: "Lector" o "Comentador"
6. **Copiar enlace**

### **Convertir a Google Sheets (Opcional):**
- Google Drive → Clic derecho en archivo → "Abrir con Google Sheets"
- Ventaja: Editable desde móvil/tablet
- Desventaja: Pierde algunos formatos de Excel

---

## 🔧 Troubleshooting

### **"No se encuentra Google Drive Desktop"**
- Verificar instalación en `C:\Users\TuUsuario\Google Drive`
- Revisar si está sincronizando (icono en bandeja del sistema)
- Usar ruta manual: `.\sync_bitacora_to_gdrive.ps1 -GDrivePath "C:\RutaCorrecta"`

### **"Error de permisos OAuth 2.0"**
- Eliminar `token_gdrive.pickle`
- Re-ejecutar `python scripts\sync_bitacora_to_drive.py`
- Volver a autorizar en navegador

### **"Archivo no se sincroniza"**
- Verificar que Drive Desktop está activo
- Revisar espacio disponible en Drive
- Forzar sincronización: clic derecho → "Sincronizar ahora"

---

## 📊 Estructura de Carpetas en Drive

Recomendación de organización:

```
Google Drive/
└── H3_Trading/
    ├── H3_BITACORA_PREDICCIONES.xlsx (principal)
    ├── Planes_Historicos/
    │   ├── trade_plan_2025-11.csv
    │   └── trade_plan_2025-10.csv
    └── Reportes/
        └── kpi_monthly_summary.csv
```

---

## 🚀 Próximos Pasos

1. **Elegir tu opción preferida** (recomendamos Opción 1)
2. **Configurar según instrucciones**
3. **Probar sincronización manual** primero
4. **Integrar en pipeline automático**
5. **Compartir link con equipo/monitores**

¿Preguntas? Revisa los scripts con `--help` o consulta la documentación.
