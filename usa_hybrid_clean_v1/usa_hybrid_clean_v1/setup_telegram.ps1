<#
.SYNOPSIS
    Configuración de credenciales de Telegram para notificaciones intraday.

.DESCRIPTION
    Script interactivo para configurar TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.
    Crea/actualiza archivo .env con las credenciales.

.PARAMETER Token
    Token del bot de Telegram (obtener desde @BotFather).

.PARAMETER ChatId
    Chat ID destino (obtener desde @userinfobot).

.EXAMPLE
    .\setup_telegram.ps1
    # Modo interactivo

.EXAMPLE
    .\setup_telegram.ps1 -Token "123456789:ABCdefGHIjklMNOpqrsTUVwxyz" -ChatId "987654321"
    # Modo directo
#>

param(
    [string]$Token,
    [string]$ChatId
)

$ErrorActionPreference = "Stop"
$envFile = ".env"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  CONFIGURACIÓN TELEGRAM - INTRADAY" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Función para validar formato token
function Test-TelegramToken {
    param([string]$token)
    return $token -match '^\d+:[A-Za-z0-9_-]{35}$'
}

# Función para validar chat ID
function Test-TelegramChatId {
    param([string]$chatId)
    return $chatId -match '^-?\d+$'
}

# Obtener token (interactivo si no se pasó)
if (-not $Token) {
    Write-Host "[INFO] Obtén tu token desde @BotFather en Telegram" -ForegroundColor Yellow
    Write-Host "       Formato: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz`n" -ForegroundColor Gray
    $Token = Read-Host "Ingresa TELEGRAM_TOKEN"
}

# Validar token
if (-not (Test-TelegramToken -token $Token)) {
    Write-Host "[ERROR] Token inválido. Formato esperado: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz" -ForegroundColor Red
    exit 1
}

# Obtener chat ID (interactivo si no se pasó)
if (-not $ChatId) {
    Write-Host "`n[INFO] Obtén tu Chat ID desde @userinfobot en Telegram" -ForegroundColor Yellow
    Write-Host "       Formato: 987654321 (o -987654321 para grupos)`n" -ForegroundColor Gray
    $ChatId = Read-Host "Ingresa TELEGRAM_CHAT_ID"
}

# Validar chat ID
if (-not (Test-TelegramChatId -chatId $ChatId)) {
    Write-Host "[ERROR] Chat ID inválido. Debe ser un número entero" -ForegroundColor Red
    exit 1
}

Write-Host "`n[INFO] Configuración validada:" -ForegroundColor Green
Write-Host "  Token: $($Token.Substring(0,15))...$($Token.Substring($Token.Length-5))" -ForegroundColor Gray
Write-Host "  Chat ID: $ChatId" -ForegroundColor Gray

# Leer .env existente (si existe)
$envLines = @()
$foundToken = $false
$foundChatId = $false

if (Test-Path $envFile) {
    Write-Host "`n[INFO] Actualizando archivo .env existente..." -ForegroundColor Cyan
    
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^TELEGRAM_TOKEN=') {
            $envLines += "TELEGRAM_TOKEN=$Token"
            $foundToken = $true
        } elseif ($line -match '^TELEGRAM_CHAT_ID=') {
            $envLines += "TELEGRAM_CHAT_ID=$ChatId"
            $foundChatId = $true
        } else {
            $envLines += $line
        }
    }
} else {
    Write-Host "`n[INFO] Creando nuevo archivo .env..." -ForegroundColor Cyan
}

# Agregar si no existían
if (-not $foundToken) {
    $envLines += "TELEGRAM_TOKEN=$Token"
}
if (-not $foundChatId) {
    $envLines += "TELEGRAM_CHAT_ID=$ChatId"
}

# Escribir archivo
$envLines | Out-File -FilePath $envFile -Encoding UTF8

Write-Host "[OK] Archivo .env guardado exitosamente" -ForegroundColor Green

# Test de conexión (opcional)
Write-Host "`n[INFO] ¿Deseas probar la conexión? (s/n): " -ForegroundColor Yellow -NoNewline
$test = Read-Host

if ($test -eq 's' -or $test -eq 'S') {
    Write-Host "`n[TEST] Enviando mensaje de prueba..." -ForegroundColor Cyan
    
    $testDate = Get-Date -Format "yyyy-MM-dd"
    python scripts\33_notify_telegram_intraday.py --date $testDate --send-plan --dry-run
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Script ejecutado correctamente (dry-run mode)" -ForegroundColor Green
        Write-Host "`nPara enviar mensaje real:" -ForegroundColor Yellow
        Write-Host "  python scripts\33_notify_telegram_intraday.py --date $testDate --send-plan" -ForegroundColor Gray
    } else {
        Write-Host "[ERROR] Script falló. Revisa configuración." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n[DONE] Configuración completada!" -ForegroundColor Green
Write-Host "`nPróximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Ejecuta pipeline completo: .\run_intraday.ps1 -Date 2025-11-03 -NotifyTelegram" -ForegroundColor Gray
Write-Host "  2. Revisa mensaje en reports\intraday\2025-11-03\telegram_message.txt" -ForegroundColor Gray
Write-Host "  3. Si es correcto, las notificaciones se enviarán automáticamente`n" -ForegroundColor Gray
