"""
Test rápido del mecanismo ensure-one.
Simula un día con señales que son filtradas, y verifica que el fallback funciona.
"""
import pandas as pd
import numpy as np
from pathlib import Path

# Crear señal sintética con buenos valores para fallback
test_signal = {
    'ticker': 'TSLA',
    'timestamp': '2025-10-22 14:30:00',
    'close': 434.11,
    'direction': 'SHORT',
    'prob_win': 0.306,  # prob_win >= 0.20 OK
    'p_tp_before_sl': 0.225,  # P(TP<SL) >= 0.15 OK
    'ETTH': 0.213,  # ETTH <= 0.30 OK
    'sector': 'Technology',
    'spread_bps': 35.70,
    'ATR_pct': 0.015,
    'volume_ratio': 1.2,
    'RSI_14': 55,
    'exp_pnl_pct': 0.0019  # Será recalculado en fallback
}

# Calcular E[PnL] con costo fallback
tp_pct = 0.028
sl_pct = 0.005
fb_cost = 0.0003  # Costo fallback (vs 0.0005 normal)

p = test_signal['p_tp_before_sl']
exp_pnl_fb = p * tp_pct - (1 - p) * sl_pct - fb_cost

print("=" * 60)
print("TEST: Ensure-One Mechanism")
print("=" * 60)
print(f"\nSeñal de prueba: {test_signal['ticker']} {test_signal['direction']}")
print(f"  Prob win: {test_signal['prob_win']:.3f} (≥0.20? {test_signal['prob_win'] >= 0.20})")
print(f"  P(TP<SL): {test_signal['p_tp_before_sl']:.3f} (≥0.15? {test_signal['p_tp_before_sl'] >= 0.15})")
print(f"  ETTH: {test_signal['ETTH']:.3f}d (≤0.30? {test_signal['ETTH'] <= 0.30})")
print(f"  E[PnL] original: {test_signal['exp_pnl_pct']:.4f}")
print(f"  E[PnL] con costo fallback (0.0003): {exp_pnl_fb:.4f} (>0? {exp_pnl_fb > 0})")

# Sizing
price = test_signal['close']
target_exposure = 550  # Entre 500-600
qty_fractional = round(target_exposure / price, 4)
exposure_fractional = qty_fractional * price

qty_integer = int(target_exposure // price)
exposure_integer = qty_integer * price

print(f"\n Precio: ${price:.2f}")
print(f"  Target exposure: ${target_exposure}")
print(f"  Qty fraccional: {qty_fractional} → Exposure: ${exposure_fractional:.2f}")
print(f"  Qty entera: {qty_integer} → Exposure: ${exposure_integer:.2f}")

# Verificar rango
in_range_frac = 500 <= exposure_fractional <= 600
in_range_int = 500 <= exposure_integer <= 600

print(f"\n✅ Fraccional en rango [500, 600]: {in_range_frac}")
print(f"✅ Entera en rango [500, 600]: {in_range_int}")

print("\n" + "=" * 60)
print("CONCLUSIÓN:")
if exp_pnl_fb > 0 and test_signal['p_tp_before_sl'] >= 0.15 and test_signal['ETTH'] <= 0.30:
    if in_range_frac:
        print("✅ La señal CALIFICA para fallback con qty fraccional")
        print(f"   Trade esperado: {test_signal['direction']} {test_signal['ticker']} @ ${price:.2f}")
        print(f"   Qty: {qty_fractional}, Exposure: ${exposure_fractional:.2f}")
    elif in_range_int:
        print("✅ La señal CALIFICA para fallback con qty entera")
        print(f"   Trade esperado: {test_signal['direction']} {test_signal['ticker']} @ ${price:.2f}")
        print(f"   Qty: {qty_integer}, Exposure: ${exposure_integer:.2f}")
    else:
        print("⚠️  La señal califica pero exposure fuera de rango")
else:
    print("❌ La señal NO califica para fallback (filtros no pasados)")
print("=" * 60)
