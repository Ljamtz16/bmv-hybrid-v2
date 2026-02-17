# Script para habilitar acceso al dashboard desde la red local
# Ejecutar como Administrador

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CONFIGURANDO FIREWALL PARA DASHBOARD" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si ya existe la regla
$existingRule = Get-NetFirewallRule -DisplayName "Trading Dashboard Port 7777" -ErrorAction SilentlyContinue

if ($existingRule) {
    Write-Host "[INFO] Regla ya existe. Eliminando regla anterior..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName "Trading Dashboard Port 7777"
}

# Crear nueva regla para permitir conexiones entrantes
Write-Host "[INFO] Creando regla de firewall para puerto 7777..." -ForegroundColor Green

New-NetFirewallRule `
    -DisplayName "Trading Dashboard Port 7777" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 7777 `
    -Action Allow `
    -Profile Private,Domain `
    -Description "Permite acceso al Trading Dashboard desde la red local"

Write-Host ""
Write-Host "[OK] Regla de firewall creada exitosamente!" -ForegroundColor Green
Write-Host ""

# Obtener IP local
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.'} | Select-Object -First 1).IPAddress

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "INFORMACION DE ACCESO" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Desde tu PC:" -ForegroundColor Yellow
Write-Host "  http://localhost:7777" -ForegroundColor White
Write-Host ""
Write-Host "Desde tu celular (misma red WiFi):" -ForegroundColor Yellow
Write-Host "  http://$localIP:7777" -ForegroundColor White
Write-Host ""
Write-Host "[IMPORTANTE] Asegurate de que:" -ForegroundColor Red
Write-Host "  1. Tu celular este conectado a la MISMA red WiFi" -ForegroundColor White
Write-Host "  2. El dashboard este corriendo (python dashboard_unified.py)" -ForegroundColor White
Write-Host "  3. No tengas VPN activo en el celular" -ForegroundColor White
Write-Host ""
