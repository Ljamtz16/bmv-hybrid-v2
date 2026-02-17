########################################
# FIX FIREWALL FOR PUBLIC NETWORK
########################################

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "CONFIGURANDO FIREWALL PARA RED PUBLIC" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

# Remover regla anterior
$existingRule = Get-NetFirewallRule -DisplayName "Trading Dashboard Port 7777" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "[1/2] Removiendo regla anterior..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName "Trading Dashboard Port 7777"
    Write-Host "      Regla anterior removida" -ForegroundColor Gray
} else {
    Write-Host "[1/2] No hay regla anterior" -ForegroundColor Gray
}

# Crear nueva regla para TODOS los perfiles (incluyendo Public)
Write-Host "[2/2] Creando regla para perfil PUBLIC..." -ForegroundColor Yellow

try {
    New-NetFirewallRule `
        -DisplayName "Trading Dashboard Port 7777" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort 7777 `
        -Action Allow `
        -Profile Private,Domain,Public `
        -Description "Permite acceso al Trading Dashboard desde la red local (incluye Public)" `
        -ErrorAction Stop | Out-Null
    
    Write-Host "      ✅ Regla creada exitosamente!" -ForegroundColor Green
} catch {
    Write-Host "      ❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Verificar la regla
$rule = Get-NetFirewallRule -DisplayName "Trading Dashboard Port 7777"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "VERIFICACION" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "Estado: " -NoNewline
if ($rule.Enabled) {
    Write-Host "✅ ACTIVA" -ForegroundColor Green
} else {
    Write-Host "❌ INACTIVA" -ForegroundColor Red
}

Write-Host "Perfiles: $($rule.Profile)" -ForegroundColor White

# Mostrar IP
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | 
            Where-Object {$_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.'} | 
            Where-Object {$_.PrefixOrigin -eq 'Dhcp' -or $_.PrefixOrigin -eq 'Manual'} |
            Select-Object -First 1).IPAddress

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ACCESO DESDE CELULAR" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "URL: http://$localIP:7777" -ForegroundColor Green
Write-Host "`n✅ Ahora deberías poder acceder desde tu celular!" -ForegroundColor Green
Write-Host "`nNOTA: Asegúrate de que el dashboard esté corriendo:" -ForegroundColor Yellow
Write-Host "      ./.venv/Scripts/python.exe dashboard_unified.py" -ForegroundColor Gray
Write-Host ""
