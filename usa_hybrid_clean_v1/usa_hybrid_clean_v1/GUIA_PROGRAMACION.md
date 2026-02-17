# =============================================
# GUÍA DE PROGRAMACIÓN - H3 Daily Pipeline
# =============================================

## 📋 Opciones disponibles

### ✅ Opción 1: Con privilegios de Administrador (Recomendado)

**Ventajas:**
- Se ejecuta en segundo plano
- No requiere mantener ventana abierta
- Más robusto y profesional

**Pasos:**
1. Abre PowerShell como Administrador:
   - Click derecho en PowerShell → "Ejecutar como administrador"

2. Navega al directorio del proyecto:
   ```powershell
   cd "C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1"
   ```

3. Ejecuta el setup:
   ```powershell
   .\setup_scheduler.ps1 -Time "22:30"
   ```

4. Verificar que se creó:
   ```powershell
   Get-ScheduledTask -TaskName "H3_Daily_Forward_Trading"
   ```

5. Probar manualmente (opcional):
   ```powershell
   Start-ScheduledTask -TaskName "H3_Daily_Forward_Trading"
   ```

---

### ✅ Opción 2: Sin privilegios (Alternativa simple)

**Ventajas:**
- No requiere permisos de administrador
- Fácil de iniciar/detener

**Desventajas:**
- Debes mantener la ventana PowerShell abierta (puede estar minimizada)
- Si apagas la PC, debes reiniciarlo

**Pasos:**
1. Abre PowerShell normal (sin admin)

2. Navega al directorio:
   ```powershell
   cd "C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1"
   ```

3. Inicia el scheduler:
   ```powershell
   .\start_scheduler_no_admin.ps1 -Time "22:30"
   ```

4. Minimiza la ventana (NO la cierres)

**Para detener:**
- Presiona `Ctrl+C` en la ventana PowerShell
- O simplemente cierra la ventana

---

### 📱 Opción 3: Ejecución manual diaria

Si prefieres control total, ejecuta manualmente después del cierre del mercado:

```powershell
.\run_daily_h3_forward.ps1 -SendTelegram
```

---

## ⏰ Horarios recomendados

| Zona horaria | Horario | Comentario |
|--------------|---------|------------|
| **US Eastern (ET)** | 5:30 PM | 1.5h después del cierre (4:00 PM) |
| **UTC** | 10:30 PM | Equivalente a 5:30 PM ET |
| **Europe (CET)** | 11:30 PM | Para usuarios europeos |

**Importante:** El mercado cierra a las 4:00 PM ET. Espera al menos 30-60 minutos para que Yahoo Finance actualice datos.

---

## 🔧 Comandos útiles

### Ver estado de la tarea programada (Opción 1)
```powershell
Get-ScheduledTask -TaskName "H3_Daily_Forward_Trading" | fl
```

### Ver historial de ejecuciones
```powershell
Get-ScheduledTask -TaskName "H3_Daily_Forward_Trading" | Get-ScheduledTaskInfo
```

### Ejecutar manualmente ahora
```powershell
Start-ScheduledTask -TaskName "H3_Daily_Forward_Trading"
```

### Eliminar tarea programada
```powershell
.\setup_scheduler.ps1 -Remove
```

### Ver última ejecución del runner simple (Opción 2)
El script imprime en consola cada vez que ejecuta.

---

## 📊 Verificar que funciona

Después de la primera ejecución programada, verifica:

1. **Archivos generados:**
   ```powershell
   ls reports\forecast\2025-11\trade_plan_tth*.* | select Name, LastWriteTime
   ```

2. **Mensaje en Telegram:**
   Deberías recibir el plan con las señales del día.

3. **Log del sistema (Opción 1):**
   ```powershell
   Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 10 | Where-Object {$_.Message -like "*H3_Daily*"}
   ```

---

## 🐛 Troubleshooting

### "Acceso denegado" al crear tarea
→ Ejecuta PowerShell como Administrador

### "No se encuentra run_daily_h3_forward.ps1"
→ Asegúrate de estar en el directorio correcto

### Tarea no se ejecuta
→ Verifica que la hora esté en formato 24h: "22:30" no "10:30 PM"

### No recibo mensajes de Telegram
→ Verifica `.env` tiene `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` correctos

### Pipeline falla en algún paso
→ Ejecuta manualmente para ver el error:
```powershell
.\run_daily_h3_forward.ps1
```

---

## 💡 Recomendación final

**Para uso personal/dev:** Usa Opción 2 (sin admin)
**Para producción/servidor:** Usa Opción 1 (tarea programada)

Si quieres que se ejecute incluso cuando no estés logueado, necesitas la Opción 1 con privilegios de administrador.
