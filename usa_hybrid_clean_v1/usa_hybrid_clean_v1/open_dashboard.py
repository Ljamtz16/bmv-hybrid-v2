#!/usr/bin/env python
"""
Script para abrir el dashboard en el navegador
Uso: python open_dashboard.py
"""

import os
import sys
import webbrowser
from pathlib import Path
import time

REPO_ROOT = Path(__file__).resolve().parent
DASHBOARD_PATH = REPO_ROOT / "analysis_dashboard.html"

def open_dashboard():
    """Abrir dashboard en navegador."""
    if not DASHBOARD_PATH.exists():
        print(f"❌ No encontrado: {DASHBOARD_PATH}")
        print("\nPasos:")
        print("1. Ejecutar: python analysis_pred_vs_real.py")
        print("2. Ejecutar: python analysis_trading_results.py")
        print("3. Luego ejecutar: python open_dashboard.py")
        return
    
    # Convertir a URL file://
    dashboard_url = DASHBOARD_PATH.as_uri()
    
    print("=" * 80)
    print("📊 ABRIENDO DASHBOARD")
    print("=" * 80)
    print(f"\n📁 Ruta: {DASHBOARD_PATH}")
    print(f"🌐 URL:  {dashboard_url}")
    print(f"\n⏳ Abriendo navegador en 2 segundos...")
    print()
    
    time.sleep(2)
    
    try:
        webbrowser.open(dashboard_url)
        print("✅ Dashboard abierto en tu navegador por defecto")
        print("\nSi no se abre automáticamente, copia esta URL:")
        print(f"   {dashboard_url}")
    except Exception as e:
        print(f"⚠️  Error al abrir navegador: {e}")
        print(f"\nAbre manualmente: {dashboard_url}")

if __name__ == "__main__":
    open_dashboard()
