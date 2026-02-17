#!/usr/bin/env python3
"""
Simulación con 5 tickers seleccionados (NVDA, AMD, XOM, META, TSLA)
Modo FAST, 3 meses Q1 2025
Capital: $1000, Exposure: $1000
TP: 0.8% (en lugar de 2.0%)
SL: 1.2%
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

# Configuración para 5 tickers con TP reducido
CONFIG = {
    "months": ["2025-01", "2025-02", "2025-03"],
    "capital": 1000,
    "exposure_cap": 1000,
    "execution_mode": "fast",
    "max_hold_days": 2,
    "tp_pct": 0.008,  # 0.8% en lugar de 2.0%
    "sl_pct": 0.012,  # 1.2% (mantener)
    "tickers": ["NVDA", "AMD", "XOM", "META", "TSLA"],  # 5 tickers específicos
    "intraday_file": "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet",
    "base_state_dir": "paper_state_5_tickers_tp08",
    "base_evidence_dir": "evidence/paper_multi_2025Q1_5_TICKERS_TP08",
}

def check_prerequisites():
    """Verifica que los datos estén disponibles."""
    print("="*70)
    print("🔍 VERIFICANDO PREREQUISITOS")
    print("="*70)
    
    intraday_path = Path(CONFIG["intraday_file"])
    if not intraday_path.exists():
        print(f"\n❌ ERROR: No existe {CONFIG['intraday_file']}")
        return False
    
    print(f"\n✅ Datos intraday: {CONFIG['intraday_file']}")
    return True

def initialize_broker(state_dir: str):
    """Inicializa el broker de paper trading."""
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
    """Ejecuta la simulación para un mes dado."""
    print("\n" + "="*70)
    print("🚀 EJECUTANDO SIMULACIÓN")
    print("="*70)
    
    print(f"\n📋 Configuración:")
    print(f"   Mes: {month}")
    print(f"   Tickers: {', '.join(CONFIG['tickers'])}")
    print(f"   Capital: ${CONFIG['capital']}")
    print(f"   Exposure Cap: ${CONFIG['exposure_cap']}")
    print(f"   Execution Mode: {CONFIG['execution_mode'].upper()}")
    print(f"   TP: {CONFIG['tp_pct']*100:.1f}%")
    print(f"   SL: {CONFIG['sl_pct']*100:.1f}%")
    print(f"   Max Hold Days: {CONFIG['max_hold_days']}")
    print(f"   Evidence: {evidence_dir}")
    
    cmd = [
        "python", "paper/wf_paper_month.py",
        "--month", month,
        "--capital", str(CONFIG["capital"]),
        "--exposure-cap", str(CONFIG["exposure_cap"]),
        "--execution-mode", CONFIG["execution_mode"],
        "--max-hold-days", str(CONFIG["max_hold_days"]),
        "--tp-pct", str(CONFIG["tp_pct"]),
        "--sl-pct", str(CONFIG["sl_pct"]),
        "--intraday", CONFIG["intraday_file"],
        "--state-dir", state_dir,
        "--evidence-dir", evidence_dir
    ]
    
    print(f"\n⏳ Ejecutando simulación...")
    print(f"\nComando:")
    print(" ".join(cmd))
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    return result.returncode == 0

def show_results(results):
    """Muestra resultados aggregados."""
    print("\n" + "="*70)
    print("📊 RESULTADOS")
    print("="*70)
    
    total_trades = 0
    total_pnl = 0.0
    weighted_wr_num = 0.0
    weighted_wr_den = 0

    for entry in results:
        summary_file = Path(entry["evidence_dir"]) / "summary.json"
        month = entry["month"]
        print(f"\n--- {month} ---")
        
        if not summary_file.exists():
            print(f"❌ No se encontró {summary_file}")
            continue

        with open(summary_file, "r") as f:
            summary = json.load(f)

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
        print(f"   TP Hits: {summary.get('tp_count', 0)}, SL Hits: {summary.get('sl_count', 0)}, TO: {summary.get('timeout_count', 0)}")
        print(f"   Equity Final: ${summary.get('final_equity', 0):.2f}")

    print("\n" + "-"*70)
    if weighted_wr_den > 0:
        agg_wr = weighted_wr_num / weighted_wr_den
    else:
        agg_wr = 0.0
    
    print("TOTAL 3 MESES (5 TICKERS: NVDA, AMD, XOM, META, TSLA | TP=0.8%)")
    print(f"   Trades: {total_trades}")
    print(f"   P&L: ${total_pnl:.2f}")
    print(f"   Win Rate (ponderado): {agg_wr:.1f}%")

    # Comparación
    print("\n" + "="*70)
    print("📈 COMPARACIÓN vs 5 TICKERS FAST (TP=2.0%)")
    print("="*70)
    
    baseline_5tp2 = {
        "name": "5 Tickers FAST TP=2.0% Q1 2025",
        "pnl": 6.37,
        "win_rate": 42.4,
        "trades": 59,
        "tp_rate": 1.7
    }

    pnl_diff = total_pnl - baseline_5tp2["pnl"]
    wr_diff = agg_wr - baseline_5tp2["win_rate"]
    trades_diff = total_trades - baseline_5tp2["trades"]

    print(f"\n5 Tickers FAST (TP=2.0%):")
    print(f"  P&L: ${baseline_5tp2['pnl']:.2f} | WR: {baseline_5tp2['win_rate']:.1f}% | Trades: {baseline_5tp2['trades']} | TP Rate: {baseline_5tp2['tp_rate']:.1f}%")

    print(f"\n5 Tickers FAST (TP=0.8%) - ESTE BACKTEST:")
    print(f"  P&L: ${total_pnl:.2f} | WR: {agg_wr:.1f}% | Trades: {total_trades}")

    print(f"\nDiferencia (TP=0.8% vs TP=2.0%):")
    pnl_symbol = "🟢" if pnl_diff > 0 else "🔴" if pnl_diff < 0 else "⚪"
    wr_symbol = "🟢" if wr_diff > 0 else "🔴" if wr_diff < 0 else "⚪"
    trade_symbol = "🟢" if trades_diff > 0 else "🔴" if trades_diff < 0 else "⚪"
    
    print(f"  P&L: {pnl_symbol} ${pnl_diff:+.2f}")
    print(f"  WR:  {wr_symbol} {wr_diff:+.1f} pp")
    print(f"  Trades: {trade_symbol} {trades_diff:+d}")

def main():
    """Orquesta la simulación 3 meses."""
    print("="*70)
    print("🎯 SIMULACIÓN CON 5 TICKERS - TP REDUCIDO A 0.8%")
    print("="*70)
    print(f"\n✅ Tickers: {', '.join(CONFIG['tickers'])}")
    print(f"✅ Modo: {CONFIG['execution_mode'].upper()}")
    print(f"✅ TP/SL: {CONFIG['tp_pct']*100:.1f}% / {CONFIG['sl_pct']*100:.1f}%")
    print(f"✅ Meses: {', '.join(CONFIG['months'])}")
    print(f"✅ Capital: ${CONFIG['capital']}")
    print(f"✅ Exposure: ${CONFIG['exposure_cap']}")
    print(f"✅ Max Hold: {CONFIG['max_hold_days']} días")
    
    if not check_prerequisites():
        sys.exit(1)
    
    results_meta = []
    
    for month in CONFIG["months"]:
        state_dir = f"{CONFIG['base_state_dir']}_{month}"
        evidence_dir = f"{CONFIG['base_evidence_dir']}/{month}"
        
        print(f"\n\n{'='*70}")
        print(f"PROCESANDO MES: {month}")
        print(f"{'='*70}")
        
        if not initialize_broker(state_dir):
            print(f"❌ Fallo en inicialización del broker para {month}")
            sys.exit(1)
        
        if not run_simulation(month, evidence_dir, state_dir):
            print(f"❌ Fallo en simulación para {month}")
            sys.exit(1)
        
        results_meta.append({"month": month, "evidence_dir": evidence_dir})
    
    # Mostrar resultados
    show_results(results_meta)
    
    print("\n" + "="*70)
    print("✅ SIMULACIÓN COMPLETADA")
    print("="*70)
    print(f"\nEvidencias guardadas en: {CONFIG['base_evidence_dir']}")

if __name__ == "__main__":
    main()
