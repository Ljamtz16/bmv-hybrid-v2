# =============================================
# sync_bitacora_to_gdrive.ps1
# =============================================
# Copiar bitácora Excel a Google Drive Desktop
# Si tienes Google Drive Desktop instalado

param(
    [string]$GDrivePath = "",
    [switch]$Auto
)

$BitacoraLocal = "reports\H3_BITACORA_PREDICCIONES.xlsx"

# Detectar ruta de Google Drive automáticamente
if ([string]::IsNullOrEmpty($GDrivePath)) {
    $PossiblePaths = @(
        "$env:USERPROFILE\Google Drive\My Drive",
        "$env:USERPROFILE\Google Drive",
        "$env:USERPROFILE\GoogleDrive",
        "C:\Users\$env:USERNAME\Google Drive\My Drive",
        "C:\Users\$env:USERNAME\Google Drive"
    )
    
    foreach ($path in $PossiblePaths) {
        if (Test-Path $path) {
            $GDrivePath = $path
            Write-Host "Google Drive detectado: $GDrivePath" -ForegroundColor Green
            break
        }
    }
    
    if ([string]::IsNullOrEmpty($GDrivePath)) {
        Write-Host "ERROR: No se encontro Google Drive Desktop instalado" -ForegroundColor Red
        Write-Host "Opciones:" -ForegroundColor Yellow
        Write-Host "  1. Instalar Google Drive Desktop desde: https://www.google.com/drive/download/" -ForegroundColor Yellow
        Write-Host "  2. Especificar ruta manualmente: .\sync_bitacora_to_gdrive.ps1 -GDrivePath 'C:\Ruta\A\Drive'" -ForegroundColor Yellow
        exit 1
    }
}

# Crear carpeta H3 en Drive si no existe
$H3Folder = Join-Path $GDrivePath "H3_Trading"
if (-not (Test-Path $H3Folder)) {
    New-Item -ItemType Directory -Path $H3Folder | Out-Null
    Write-Host "Creada carpeta: $H3Folder" -ForegroundColor Green
}

$BitacoraDrive = Join-Path $H3Folder "H3_BITACORA_PREDICCIONES.xlsx"

# Verificar que existe la bitácora local
if (-not (Test-Path $BitacoraLocal)) {
    Write-Host "ERROR: No se encuentra la bitacora local: $BitacoraLocal" -ForegroundColor Red
    exit 1
}

# Copiar archivo
try {
    Copy-Item -Path $BitacoraLocal -Destination $BitacoraDrive -Force
    
    $FileSize = (Get-Item $BitacoraDrive).Length / 1KB
    Write-Host "Bitacora sincronizada con Google Drive" -ForegroundColor Green
    Write-Host "  Origen: $BitacoraLocal" -ForegroundColor Cyan
    Write-Host "  Destino: $BitacoraDrive" -ForegroundColor Cyan
    Write-Host "  Tamano: $([math]::Round($FileSize, 2)) KB" -ForegroundColor Cyan
    
    # Mostrar URL para compartir (requiere configuración manual en Drive)
    Write-Host ""
    Write-Host "Para compartir en linea:" -ForegroundColor Yellow
    Write-Host "  1. Abre Google Drive en el navegador" -ForegroundColor Yellow
    Write-Host "  2. Busca: H3_Trading\H3_BITACORA_PREDICCIONES.xlsx" -ForegroundColor Yellow
    Write-Host "  3. Clic derecho > Compartir > Copiar enlace" -ForegroundColor Yellow
    
    # Guardar ruta de Drive en variable de entorno para otros scripts
    if ($Auto) {
        [System.Environment]::SetEnvironmentVariable("H3_BITACORA_PATH", $BitacoraDrive, "User")
        Write-Host ""
        Write-Host "Variable de entorno H3_BITACORA_PATH configurada" -ForegroundColor Green
        Write-Host "Los scripts usaran automaticamente la copia de Drive" -ForegroundColor Green
    }
    
    exit 0
}
catch {
    Write-Host "ERROR: No se pudo copiar el archivo" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
