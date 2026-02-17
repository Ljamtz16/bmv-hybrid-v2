#!/usr/bin/env python3
"""
Simulación con MEJOR CONFIGURACIÓN en UNIVERSO COMPLETO de 18 tickers

Configuración basada en: paper_dec_2025_ab_new (mejor P&L: $68.09)
Parámetros óptimos:
  - Timeframe: 15 minutos
  - Execution: balanced
  - TP: 2.0%
  - SL: 1.2%
  - Max Hold: 2 días
  - Capital: $1000
  - Tickers: TODOS (18 tickers en lugar de 5)
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

# Configuración óptima (de paper_dec_2025_ab_new)
CONFIG = {
    # Rango solicitado: 3 meses desde enero 2025 (inclusive)
    "months": ["2025-01", "2025-02", "2025-03"],
    "capital": 1000,
    "exposure_cap": 1000,
    "execution_mode": "fast",
    "max_hold_days": 2,
    "intraday_file": "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet",
    "base_state_dir": "paper_state_all_tickers_fast",
    "base_evidence_dir": "evidence/paper_multi_2025Q1_ALL_18_TICKERS_FAST",
}

# Verificar que existe el archivo de datos
def check_prerequisites():
    """Verifica que los datos y el entorno estén listos."""
    print("="*70)
    print("🔍 VERIFICANDO PREREQUISITOS")
    print("="*70)
    
    intraday_path = Path(CONFIG["intraday_file"])
    if not intraday_path.exists():
        print(f"\n❌ ERROR: No existe {CONFIG['intraday_file']}")
        print("\n📥 Primero ejecuta:")
        print("   python download_all_tickers_15m.py")
        print("   python paper/merge_intraday_parquets.py ...")
        return False
    
    print(f"\n✅ Datos intraday: {CONFIG['intraday_file']}")
    print(f"   Tamaño: {intraday_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Verificar tickers en el archivo
    try:
        import pandas as pd
        df = pd.read_parquet(intraday_path)
        tickers = sorted(df['ticker'].unique()) if 'ticker' in df.columns else []
        print(f"\n📊 Tickers disponibles: {len(tickers)}")
        print(f"   {', '.join(tickers)}")
        
        if len(tickers) < 15:
            print(f"\n⚠️  ADVERTENCIA: Solo hay {len(tickers)} tickers")
            print("   Se esperaban 18 tickers del universo completo")
    except Exception as e:
        print(f"\n⚠️  No se pudo leer archivo: {e}")
    
    print("\n✅ Prerequisitos OK")
    return True

def initialize_broker(state_dir: str):
    """Inicializa el broker de paper trading para un mes específico."""
    print("\n" + "="*70)
    print("💼 INICIALIZANDO BROKER")
    print("="*70)
    
    cmd = [
        "python", "paper/paper_broker.py",
        "init",
        "--cash", str(CONFIG["capital"]),
        "--state-dir", state_dir
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Broker inicializado")
        return True
    else:
        print("❌ Error al inicializar broker")
        print(result.stderr)
        return False

def run_simulation(month: str, evidence_dir: str, state_dir: str):
    """Ejecuta la simulación walk-forward para un mes dado."""
    print("\n" + "="*70)
    print("🚀 EJECUTANDO SIMULACIÓN")
    print("="*70)
    
    print(f"\n📋 Configuración:")
    print(f"   Mes: {month}")
    print(f"   Capital: ${CONFIG['capital']}")
    print(f"   Exposure Cap: ${CONFIG['exposure_cap']}")
    print(f"   Execution Mode: {CONFIG['execution_mode'].upper()}")
    print(f"   Max Hold Days: {CONFIG['max_hold_days']}")
    print(f"   Datos: {CONFIG['intraday_file']}")
    print(f"   Evidence: {evidence_dir}")
    
    cmd = [
        "python", "paper/wf_paper_month.py",
        "--month", month,
        "--capital", str(CONFIG["capital"]),
        "--exposure-cap", str(CONFIG["exposure_cap"]),
        "--execution-mode", CONFIG["execution_mode"],
        "--max-hold-days", str(CONFIG["max_hold_days"]),
        "--intraday", CONFIG["intraday_file"],
        "--state-dir", state_dir,
        "--evidence-dir", evidence_dir
    ]
    
    print(f"\n⏳ Ejecutando simulación... (esto puede tomar 5-10 minutos)")
    print(f"\nComando:")
    print(" ".join(cmd))
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    return result.returncode == 0

def show_results(results):
    """Muestra los resultados por mes y un agregado simple."""
    print("\n" + "="*70)
    print("📊 RESULTADOS")
    print("="*70)
    total_trades = 0
    total_pnl = 0.0
    weighted_wr_num = 0.0
    weighted_wr_den = 0
    summaries = []

    for entry in results:
        summary_file = Path(entry["evidence_dir"]) / "summary.json"
        month = entry["month"]
        print(f"\n--- {month} ---")
        if not summary_file.exists():
            print(f"❌ No se encontró {summary_file}")
            continue

        with open(summary_file, "r") as f:
            summary = json.load(f)
        summaries.append(summary)

        trades = summary.get("total_trades", 0)
        pnl = summary.get("total_pnl", 0.0)
        wr = summary.get("win_rate", 0.0)
        total_trades += trades
        total_pnl += pnl
        weighted_wr_num += wr * trades
        weighted_wr_den += trades

        print(f"   Trades: {trades}")
        print(f"   P&L: ${pnl:.2f}")
        print(f"   Win Rate: {wr:.1f}%")
        print(f"   Max Drawdown: {summary.get('mdd_pct', 0):.2f}%")
        print(f"   Equity Final: ${summary.get('final_equity', 0):.2f}")
        print(f"   Archivos: {entry['evidence_dir']}")

    print("\n" + "-"*70)
    if weighted_wr_den > 0:
        agg_wr = weighted_wr_num / weighted_wr_den
    else:
        agg_wr = 0.0
    print("TOTAL 3 MESES")
    print(f"   Trades: {total_trades}")
    print(f"   P&L: ${total_pnl:.2f}")
    print(f"   Win Rate (ponderado): {agg_wr:.1f}%")

    # Comparación con mejor resultado anterior
    print("\n" + "="*70)
    print("📈 COMPARACIÓN vs MEJOR RESULTADO ANTERIOR")
    print("="*70)

    best_config = {
        "name": "paper_dec_2025_ab_new (5 tickers: AMD,CVX,XOM,NVDA,MSFT)",
        "pnl": 68.09,
        "win_rate": 56.3,
        "trades": 71
    }

    pnl_diff = total_pnl - best_config["pnl"]
    wr_diff = agg_wr - best_config["win_rate"]

    print(f"\nAnterior (5 tickers):")
    print(f"  P&L: ${best_config['pnl']:.2f} | WR: {best_config['win_rate']:.1f}% | Trades: {best_config['trades']}")

    print(f"\nNuevo (18 tickers, 3 meses):")
    print(f"  P&L: ${total_pnl:.2f} | WR: {agg_wr:.1f}% | Trades: {total_trades}")

    print(f"\nDiferencia:")
    pnl_symbol = "🟢" if pnl_diff > 0 else "🔴"
    wr_symbol = "🟢" if wr_diff > 0 else "🔴"
    pnl_pct = (pnl_diff / best_config["pnl"] * 100) if best_config["pnl"] != 0 else 0
    trades_mult = (total_trades / best_config["trades"]) if best_config["trades"] != 0 else 0
    print(f"  {pnl_symbol} P&L: ${pnl_diff:+.2f} ({pnl_pct:+.1f}%)")
    print(f"  {wr_symbol} WR: {wr_diff:+.1f} pp")
    print(f"  📊 Trades: {total_trades - best_config['trades']:+d} ({trades_mult:.1f}x)")

def main():
    print("="*70)
    print("🎯 SIMULACIÓN CON UNIVERSO COMPLETO - 18 TICKERS")
    print("="*70)
    print("\nConfiguración óptima aplicada:")
    print("  • Execution: FAST")
    print("  • TP: 2.0% | SL: 1.2%")
    print("  • Max Hold: 2 días")
    print("  • Timeframe: 15 minutos")
    print("  • Capital: $1,000")
    print("  • Tickers: 18 (universo completo)")
    print(f"  • Meses: {', '.join(CONFIG['months'])}")
    
    # Verificar prerequisitos
    if not check_prerequisites():
        sys.exit(1)
    
    # Confirmar ejecución
    print("\n" + "="*70)
    response = input("\n¿Ejecutar simulaciones para estos meses? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelado")
        sys.exit(0)

    results_meta = []
    for month in CONFIG["months"]:
        # Separar directorios por mes para evitar colisiones
        state_dir = f"{CONFIG['base_state_dir']}_{month}"
        evidence_dir = f"{CONFIG['base_evidence_dir']}/{month}"

        print("\n" + "="*70)
        print(f"📅 Mes en proceso: {month}")
        print("="*70)

        # Inicializar broker
        if not initialize_broker(state_dir):
            print("\n❌ Error al inicializar broker")
            sys.exit(1)

        # Ejecutar simulación
        if not run_simulation(month, evidence_dir, state_dir):
            print("\n❌ Error en la simulación")
            sys.exit(1)

        results_meta.append({"month": month, "evidence_dir": evidence_dir})

    # Mostrar resultados agregados
    show_results(results_meta)
    
    print("\n" + "="*70)
    print("✨ SIMULACIÓN COMPLETADA")
    print("="*70)

if __name__ == "__main__":
    main()
