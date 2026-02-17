"""
PROFIT MODE - Pipeline diario para 1-2 trades con ganancias decentes
=====================================================================

Estrategia:
- Plan A (estricto): prob_win≥7%, P(TP<SL)≥18%, ETTH≤0.28d
- Plan B (fallback): prob_win≥3%, P(TP<SL)≥15%, ETTH≤0.30d
- Objetivo: 1-2 trades/día con $500 c/u
- E[PnL] esperado: $1-$2.4/día en paper
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

def run_command(cmd, description):
    """Run command and show output"""
    print(f"\n{'='*80}")
    print(f"▶️  {description}")
    print(f"{'='*80}")
    print(f"$ {cmd}")
    print()
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # Show relevant output
    for line in result.stdout.split('\n'):
        if any(keyword in line for keyword in [
            'señales', 'filas', 'tickers', 'ETTH', 'P(TP<SL)',
            'trades', 'Exposure', 'Prob win', 'Plan final', 'Total'
        ]):
            print(line)
    
    if result.returncode != 0:
        print(f"❌ ERROR: {result.stderr}")
        return False
    
    return True

def count_trades_in_plan(date):
    """Count trades in generated plan"""
    plan_path = Path(f"reports/intraday/{date}/trade_plan_intraday.csv")
    if not plan_path.exists():
        return 0
    
    plan = pd.read_csv(plan_path)
    return len(plan)

# Config
date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

print("="*80)
print("🚀 PROFIT MODE - Pipeline Intraday")
print("="*80)
print(f"Fecha: {date}")
print(f"Config: TP=2.0%, SL=0.4%, $500/trade, cap=$2,000")
print(f"Objetivo: 1-2 trades con E[PnL] $1-$2.4/día")
print()

# Step 1: Inference (relaxed prob_win for more signals)
if not run_command(
    f"python scripts\\11_infer_and_gate_intraday.py --date {date} --prob-min 0.03",
    "PASO 1: Inferencia (prob_win≥3%)"
):
    sys.exit(1)

# Step 2: TTH Prediction
if not run_command(
    f"python scripts\\39_predict_tth_intraday.py --date {date}",
    "PASO 2: Predicción TTH"
):
    sys.exit(1)

# Step 3: Plan A (ESTRICTO - alta calidad)
print(f"\n{'='*80}")
print("PASO 3A: Plan ESTRICTO (prob_win≥7%, P(TP<SL)≥18%, ETTH≤0.28d)")
print(f"{'='*80}")

cmd_plan_a = (
    f"python scripts\\40_make_trade_plan_intraday.py --date {date} "
    f"--tp-pct 0.02 --sl-pct 0.004 "
    f"--per-trade-cash 500 --capital-max 2000 "
    f"--prob-win-min 0.07 --p-tp-sl-min 0.18 --etth-max 0.28 "
    f"--ensure-one"
)

run_command(cmd_plan_a, "Generando Plan A")

# Check if we got 1-2 trades
trades_plan_a = count_trades_in_plan(date)
print(f"\n📊 Plan A: {trades_plan_a} trade(s) generado(s)")

# Step 4: Plan B (FALLBACK - si Plan A < 2 trades)
if trades_plan_a < 2:
    print(f"\n{'='*80}")
    print("PASO 3B: Plan FALLBACK (prob_win≥3%, P(TP<SL)≥15%, ETTH≤0.30d)")
    print(f"{'='*80}")
    print("⚠️  Plan A generó <2 trades, ejecutando fallback...")
    
    cmd_plan_b = (
        f"python scripts\\40_make_trade_plan_intraday.py --date {date} "
        f"--tp-pct 0.02 --sl-pct 0.004 "
        f"--per-trade-cash 500 --capital-max 2000 "
        f"--prob-win-min 0.03 --p-tp-sl-min 0.15 --etth-max 0.30 "
        f"--ensure-one"
    )
    
    run_command(cmd_plan_b, "Generando Plan B (fallback)")
    
    trades_plan_b = count_trades_in_plan(date)
    print(f"\n📊 Plan B: {trades_plan_b} trade(s) generado(s)")
    total_trades = trades_plan_b
else:
    total_trades = trades_plan_a
    print("\n✅ Plan A suficiente, no se requiere fallback")

# Final summary
print(f"\n{'='*80}")
print("📊 RESUMEN FINAL")
print(f"{'='*80}")

plan_path = Path(f"reports/intraday/{date}/trade_plan_intraday.csv")
if plan_path.exists():
    plan = pd.read_csv(plan_path)
    
    if len(plan) > 0:
        total_exposure = plan['exposure'].sum()
        avg_prob_win = plan['prob_win'].mean() * 100
        avg_etth = plan['ETTH'].mean()
        
        # Calculate expected PnL
        plan['exp_pnl_usd'] = plan['exp_pnl_pct'] * plan['exposure']
        total_exp_pnl = plan['exp_pnl_usd'].sum()
        
        print(f"\n✅ Plan generado exitosamente:")
        print(f"   • Trades: {len(plan)}")
        print(f"   • Tickers: {', '.join(plan['ticker'].unique())}")
        print(f"   • Exposure total: ${total_exposure:.2f}")
        print(f"   • Prob win promedio: {avg_prob_win:.1f}%")
        print(f"   • ETTH promedio: {avg_etth:.2f} días ({avg_etth*6.5:.1f} horas)")
        print(f"   • E[PnL] esperado: ${total_exp_pnl:.2f}")
        
        print(f"\n📋 Detalle de trades:")
        for idx, trade in plan.iterrows():
            direction_emoji = "🔴" if trade['direction'] == 'SHORT' else "🟢"
            print(f"\n   {direction_emoji} Trade #{idx+1}: {trade['ticker']} {trade['direction']}")
            print(f"      Entry: ${trade['entry_price']:.2f}")
            print(f"      TP: ${trade['tp_price']:.2f} (+2.0%)")
            print(f"      SL: ${trade['sl_price']:.2f} (-0.4%)")
            print(f"      Qty: {trade['qty']:.0f}, Exposure: ${trade['exposure']:.2f}")
            print(f"      Prob win: {trade['prob_win']*100:.1f}%, P(TP<SL): {trade['p_tp_before_sl']*100:.1f}%")
            print(f"      ETTH: {trade['ETTH']:.2f}d ({trade['ETTH']*6.5:.1f}h)")
            print(f"      E[PnL]: ${trade['exp_pnl_usd']:.2f}")
        
        print(f"\n💰 Expectativa: ${total_exp_pnl:.2f} en paper (sin comisiones reales)")
        print(f"   Riesgo/Reward: TP=2.0% vs SL=0.4% (R=5:1)")
        
    else:
        print("\n⚠️  Plan vacío (0 trades)")
        print("   Posibles causas:")
        print("   • Señales no cumplen filtros E[PnL]>0")
        print("   • Spreads muy altos en tickers disponibles")
        print("   • ETTH demasiado largo (>0.30d)")
else:
    print("\n❌ No se generó archivo de plan")

print(f"\n📂 Archivos generados:")
print(f"   • Forecast: reports/intraday/{date}/forecast_intraday.parquet")
print(f"   • Candidatos: reports/intraday/{date}/trade_candidates_intraday.csv")
print(f"   • Plan: reports/intraday/{date}/trade_plan_intraday.csv")
print()
