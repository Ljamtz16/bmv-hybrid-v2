#!/usr/bin/env python3
"""
validate_rpi_setup.py
Script para validar que la setup de la RPi está completa y funcional.
Uso: python validate_rpi_setup.py
"""

import sys
import os
from pathlib import Path
import subprocess
import json

REPO_ROOT = Path(__file__).parent
STATUS = {"passed": 0, "failed": 0, "warnings": 0}

def test(name, condition, details=""):
    """Registra resultado de test."""
    global STATUS
    if condition:
        print(f"✅ {name}")
        STATUS["passed"] += 1
    else:
        print(f"❌ {name}")
        if details:
            print(f"   → {details}")
        STATUS["failed"] += 1

def warn(name, details=""):
    """Registra warning."""
    global STATUS
    print(f"⚠️  {name}")
    if details:
        print(f"   → {details}")
    STATUS["warnings"] += 1

def section(title):
    """Imprime sección."""
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

# ============================================================================
# TESTS
# ============================================================================

print("""
╔════════════════════════════════════════════════╗
║    VALIDACIÓN DE SETUP - BMV HYBRID RPI      ║
╚════════════════════════════════════════════════╝
""")

# ============================================================================
# 1. Python & Venv
# ============================================================================
section("1. Python & Virtual Environment")

test("Python 3 disponible", 
     Path(sys.executable).name == "python3" or "python3" in sys.executable,
     f"Ejecutable: {sys.executable}")

test("Versión Python >= 3.10",
     sys.version_info >= (3, 10),
     f"Versión actual: {sys.version_info.major}.{sys.version_info.minor}")

test("Dentro de Virtual Environment",
     hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix),
     "Ejecuta: source .venv/bin/activate")

# ============================================================================
# 2. Librerías
# ============================================================================
section("2. Librerías Principales")

required_libs = ["pandas", "numpy", "sklearn", "yaml", "yfinance", "requests", "joblib"]
for lib in required_libs:
    try:
        __import__(lib if lib != "sklearn" else "sklearn")
        test(f"Librería: {lib}", True)
    except ImportError as e:
        test(f"Librería: {lib}", False, str(e))

# ============================================================================
# 3. Estructura de Directorios
# ============================================================================
section("3. Estructura de Directorios")

dirs = {
    "data/raw/1d": "Datos históricos 1D",
    "data/raw/1h": "Datos históricos 1H",
    "data/interim": "Datos intermedios",
    "models": "Modelos entrenados",
    "config": "Configuración",
    "reports": "Reportes",
    "scripts": "Scripts",
    "src": "Código fuente",
    "logs": "Logs"
}

for dir_name, desc in dirs.items():
    path = REPO_ROOT / dir_name
    test(f"Directorio: {dir_name}", path.exists(), desc)

# ============================================================================
# 4. Archivos Críticos
# ============================================================================
section("4. Archivos Críticos")

files = {
    "config/base.yaml": "Configuración base",
    "config/paper.yaml": "Configuración paper (trading en vivo)",
    "models/prob_win_calibrated.joblib": "Modelo de probabilidad",
    "models/return_model_H3.joblib": "Modelo de retornos H3",
    "models/thresholds_by_ticker.json": "Umbrales de decisión",
}

for file_name, desc in files.items():
    path = REPO_ROOT / file_name
    if file_name.endswith(".yaml") and not path.exists():
        warn(f"Archivo: {file_name}", desc)
    else:
        test(f"Archivo: {file_name}", path.exists(), desc)

# ============================================================================
# 5. Scripts Esenciales
# ============================================================================
section("5. Scripts Esenciales")

scripts = {
    "scripts/01_download_data.py": "Descarga datos",
    "scripts/02_build_features.py": "Construye features",
    "scripts/04_generate_signals.py": "Genera señales",
    "scripts/paper_run_daily.py": "Paper trading",
    "scripts/monitor_forecast_live.py": "Monitoreo en vivo",
}

for script_name, desc in scripts.items():
    path = REPO_ROOT / script_name
    test(f"Script: {Path(script_name).name}", path.exists(), desc)

# ============================================================================
# 6. Módulos Source
# ============================================================================
section("6. Módulos Fuente (src/)")

src_modules = [
    "src/config.py",
    "src/io/loader.py",
    "src/features/builder.py",
    "src/signals/generator.py",
    "src/models/inference.py",
]

for module in src_modules:
    path = REPO_ROOT / module
    test(f"Módulo: {module}", path.exists())

# ============================================================================
# 7. Servicios Systemd
# ============================================================================
section("7. Servicios Systemd (si está en RPi)")

try:
    result = subprocess.run(["sudo", "systemctl", "list-timers", "--all"], 
                          capture_output=True, text=True, timeout=5)
    has_daily = "bmv-daily-tasks" in result.stdout
    has_monitor = "bmv-monitor-live" in result.stdout
    
    if has_daily or has_monitor:
        test("Timer: bmv-daily-tasks", has_daily)
        test("Timer: bmv-monitor-live", has_monitor)
    else:
        warn("Servicios systemd", "No se encontraron timers (normal si no están activados)")
except Exception as e:
    warn("Verificación systemd", "No se pudo verificar (puede no ser RPi o falta sudo)")

# ============================================================================
# 8. Conectividad
# ============================================================================
section("8. Conectividad")

import socket
try:
    # Test DNS
    socket.gethostbyname("query1.finance.yahoo.com")
    test("Conectividad Internet", True, "Yahoo Finance accesible")
except Exception as e:
    test("Conectividad Internet", False, str(e))

# ============================================================================
# 9. Datos Disponibles
# ============================================================================
section("9. Datos Disponibles")

data_1d_dir = REPO_ROOT / "data/raw/1d"
if data_1d_dir.exists():
    csv_files = list(data_1d_dir.glob("*.csv"))
    test(f"Datos 1D: {len(csv_files)} archivos", len(csv_files) > 0,
         f"Archivos: {', '.join([f.name for f in csv_files[:3]])}")
else:
    warn("Directorio data/raw/1d no existe", "Ejecuta: python scripts/01_download_data.py")

# ============================================================================
# 10. Espacio Disco
# ============================================================================
section("10. Espacio en Disco")

import shutil
try:
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024**3)
    test(f"Espacio libre: {free_gb:.1f} GB", free_gb > 2,
         f"Total: {total/(1024**3):.1f} GB | Usado: {used/(1024**3):.1f} GB")
except Exception as e:
    warn("Espacio disco", str(e))

# ============================================================================
# 11. Test de Importación
# ============================================================================
section("11. Test de Importación de Módulos")

sys.path.insert(0, str(REPO_ROOT))

try:
    from src.config import load_cfg
    test("Import: src.config", True)
except Exception as e:
    test("Import: src.config", False, str(e))

try:
    from src.io.loader import load_daily_map
    test("Import: src.io.loader", True)
except Exception as e:
    test("Import: src.io.loader", False, str(e))

try:
    from src.features.builder import build_features
    test("Import: src.features", True)
except Exception as e:
    test("Import: src.features", False, str(e))

# ============================================================================
# RESUMEN
# ============================================================================

print(f"\n{'='*50}")
print(f"  RESUMEN")
print(f"{'='*50}")
print(f"✅ Pasados:  {STATUS['passed']}")
print(f"❌ Fallidos: {STATUS['failed']}")
print(f"⚠️  Warnings: {STATUS['warnings']}")
print(f"{'='*50}\n")

if STATUS['failed'] == 0:
    print("🎉 SETUP COMPLETADO CON ÉXITO!")
    print("\nPróximos pasos:")
    print("  1. Verificar config/paper.yaml está configurado")
    print("  2. Activar servicios: sudo systemctl enable bmv-daily-tasks.timer")
    print("  3. Ver logs: journalctl -u bmv-daily-tasks -f")
    sys.exit(0)
else:
    print("⚠️  ERRORES ENCONTRADOS")
    print("\nRevisa los errores arriba y ejecuta:")
    print("  - pip install -r requirements-lite.txt")
    print("  - python scripts/01_download_data.py")
    print("  - Ver INSTALL_RPI.md para más detalles")
    sys.exit(1)
