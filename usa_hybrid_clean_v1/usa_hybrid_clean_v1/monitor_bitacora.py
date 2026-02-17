"""
Monitor continuo de predicciones H3 - Actualiza bitácora cada 5 minutos.
Se ejecuta durante horario de mercado y monitorea todas las posiciones activas.
"""
import time
import pandas as pd
from datetime import datetime, time as dtime
import sys
import os

# Agregar path de scripts
sys.path.insert(0, 'scripts')
sys.path.insert(0, 'utils')

from bitacora_excel import update_prices

# Configuración
UPDATE_INTERVAL_SECONDS = 5 * 60  # 5 minutos
DAILY_PRICES_PATH = "data/us/ohlcv_us_daily.csv"
MARKET_OPEN = dtime(9, 30)   # 9:30 AM ET
MARKET_CLOSE = dtime(16, 0)  # 4:00 PM ET

def is_market_hours():
    """Verificar si estamos en horario de mercado (lunes a viernes, 9:30-16:00 ET)."""
    now = datetime.now()
    
    # Verificar día de la semana (0=Lunes, 6=Domingo)
    if now.weekday() >= 5:  # Sábado o Domingo
        return False
    
    # Verificar hora
    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

def download_latest_prices():
    """Descargar precios más recientes."""
    try:
        import subprocess
        result = subprocess.run(
            ["python", "scripts/download_us_prices.py", "--universe", "master"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return True
        else:
            print(f"⚠️  Error descargando precios: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def monitor_loop(run_continuously=False):
    """
    Loop principal de monitoreo.
    
    Args:
        run_continuously: Si True, ejecuta 24/7. Si False, solo en horario de mercado.
    """
    print("=" * 80)
    print("🔄 MONITOR CONTINUO DE PREDICCIONES H3")
    print("=" * 80)
    print(f"⏱️  Intervalo de actualización: {UPDATE_INTERVAL_SECONDS // 60} minutos")
    
    if not run_continuously:
        print(f"📅 Horario de mercado: {MARKET_OPEN.strftime('%H:%M')} - {MARKET_CLOSE.strftime('%H:%M')} ET")
        print("   (Solo lunes a viernes)")
    else:
        print("🌍 Modo continuo: 24/7")
    
    print("\n💡 Presiona Ctrl+C para detener")
    print("=" * 80)
    print()
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            now = datetime.now()
            
            # Verificar si debemos ejecutar
            should_run = run_continuously or is_market_hours()
            
            if should_run:
                print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Actualización #{iteration}")
                
                # Descargar precios más recientes
                print("📥 Descargando precios actuales...")
                if download_latest_prices():
                    print("✅ Precios actualizados")
                    
                    # Actualizar bitácora
                    try:
                        update_prices(DAILY_PRICES_PATH)
                    except Exception as e:
                        print(f"❌ Error actualizando bitácora: {e}")
                else:
                    print("⚠️  Usando precios en cache")
                    try:
                        update_prices(DAILY_PRICES_PATH)
                    except Exception as e:
                        print(f"❌ Error actualizando bitácora: {e}")
                
                print(f"⏳ Próxima actualización en {UPDATE_INTERVAL_SECONDS // 60} minutos...")
                
            else:
                # Fuera de horario de mercado
                if iteration == 1 or (iteration - 1) % 12 == 0:  # Cada hora cuando está cerrado
                    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 💤 Fuera de horario de mercado")
                    print(f"   Próxima apertura: {MARKET_OPEN.strftime('%H:%M')} ET")
            
            # Esperar hasta la próxima iteración
            time.sleep(UPDATE_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitor detenido por usuario")
        print("=" * 80)
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error inesperado: {e}")
        print("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Monitor continuo de predicciones H3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  
  # Monitor durante horario de mercado solamente (9:30-16:00 ET, lunes-viernes)
  python monitor_bitacora.py
  
  # Monitor continuo 24/7 (útil para mercados internacionales)
  python monitor_bitacora.py --continuous
  
  # Monitor con intervalo personalizado (cada 10 minutos)
  python monitor_bitacora.py --interval 10
  
  # Monitor solo una vez (no loop)
  python monitor_bitacora.py --once
        """
    )
    
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Ejecutar 24/7 sin restricción de horario de mercado"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Intervalo entre actualizaciones en minutos (default: 5)"
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar solo una vez y salir (no loop)"
    )
    
    args = parser.parse_args()
    
    # Actualizar intervalo
    UPDATE_INTERVAL_SECONDS = args.interval * 60
    
    if args.once:
        # Ejecutar solo una vez
        print("🔍 Ejecutando actualización única...")
        download_latest_prices()
        update_prices(DAILY_PRICES_PATH)
        print("✅ Actualización completada")
    else:
        # Ejecutar loop
        monitor_loop(run_continuously=args.continuous)
