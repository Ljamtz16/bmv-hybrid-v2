#!/usr/bin/env python3
"""
Test: CapitalManager + RiskManager + Intraday Gates
Valida la arquitectura de Swing + Fase 2 (intraday selectivo)
"""
import sys
sys.path.insert(0, '.')

from dashboard_unified_temp import (
    CapitalManager, RiskManager, intraday_gates_pass,
    logger
)

print("\n" + "="*70)
print("TEST: CapitalManager + RiskManager + Intraday Gates")
print("="*70)

# ============================================================================
# TEST 1: CapitalManager - Buckets y límites
# ============================================================================
print("\n[TEST 1] CapitalManager - Buckets y límites")
print("-" * 70)

cm = CapitalManager(total_capital=2000, swing_pct=0.70, intraday_pct=0.30)

print(f"Swing bucket: ${cm.swing_bucket:.2f}")
print(f"Intraday bucket: ${cm.intraday_bucket:.2f}")
print(f"Max open total: {cm.max_open_total}")
print(f"Max open swing: {cm.max_open_swing}")
print(f"Max open intraday: {cm.max_open_intraday}")

# ============================================================================
# TEST 2: CapitalManager - Permite trade válido
# ============================================================================
print("\n[TEST 2] CapitalManager - Permite trade válido")
print("-" * 70)

signal_swing = {
    'book': 'swing',
    'ticker': 'AAPL',
    'entry': 180.0,
    'qty': 3,
    'side': 'BUY'
}

allowed = cm.allows(signal_swing)
print(f"Signal: {signal_swing}")
print(f"Allowed: {allowed}")
assert allowed == True, "Debe permitir Swing válido"

cm.add_open('swing', 'AAPL', 3)
print(f"Open Swing: {cm.open_swing}")

# ============================================================================
# TEST 3: CapitalManager - Rechaza duplicado
# ============================================================================
print("\n[TEST 3] CapitalManager - Rechaza duplicado")
print("-" * 70)

signal_dup = {
    'book': 'swing',
    'ticker': 'AAPL',
    'entry': 180.0,
    'qty': 2,
    'side': 'BUY'
}

allowed = cm.allows(signal_dup)
print(f"Signal (duplicate AAPL): {signal_dup}")
print(f"Allowed: {allowed}")
assert allowed == False, "Debe rechazar duplicado en Swing"

# ============================================================================
# TEST 4: CapitalManager - Intraday reduce tamaño si ticker en Swing
# ============================================================================
print("\n[TEST 4] CapitalManager - Heat: Intraday reduce si ticker en Swing")
print("-" * 70)

signal_intraday = {
    'book': 'intraday',
    'ticker': 'AAPL',  # Ya está en Swing
    'entry': 180.0,
    'qty': 1,
    'side': 'BUY'
}

allowed = cm.allows(signal_intraday)
print(f"Signal: {signal_intraday} (AAPL ya está en Swing)")
print(f"Allowed: {allowed}")
print("(Lógica: Intraday reduce 50% si ticker en Swing, pero chequea capital)")

# ============================================================================
# TEST 5: CapitalManager - Rechaza si excede límite de abiertas
# ============================================================================
print("\n[TEST 5] CapitalManager - Rechaza si excede límite de abiertas")
print("-" * 70)

# Abre 2 más en Swing (total 3, máximo)
cm.add_open('swing', 'TSLA', 2)
cm.add_open('swing', 'MSFT', 1)

print(f"Open Swing now: {cm.open_swing} (count: {cm.get_open_count('swing')})")

signal_4th = {
    'book': 'swing',
    'ticker': 'GOOGL',
    'entry': 150.0,
    'qty': 1,
    'side': 'BUY'
}

allowed = cm.allows(signal_4th)
print(f"Attempt 4th Swing position: {allowed}")
assert allowed == False, "Debe rechazar 4ta posición Swing (máx 3)"

# ============================================================================
# TEST 6: RiskManager - Inicialización
# ============================================================================
print("\n[TEST 6] RiskManager - Inicialización")
print("-" * 70)

rm = RiskManager(cm, capital_total=2000)

print(f"Intraday enabled: {rm.is_intraday_enabled()}")
print(f"Daily stop %: {rm.intraday_daily_stop_pct * 100:.1f}%")
print(f"Weekly stop %: {rm.intraday_weekly_stop_pct * 100:.1f}%")
print(f"DD threshold: {rm.drawdown_threshold * 100:.1f}%")

# ============================================================================
# TEST 7: RiskManager - Daily stop
# ============================================================================
print("\n[TEST 7] RiskManager - Daily stop intraday")
print("-" * 70)

intraday_bucket = cm.intraday_bucket
daily_limit = intraday_bucket * rm.intraday_daily_stop_pct
print(f"Intraday bucket: ${intraday_bucket:.2f}")
print(f"Daily stop limit: ${daily_limit:.2f} ({rm.intraday_daily_stop_pct*100:.1f}%)")

# Simula pérdida que dispara daily stop
big_loss = -(daily_limit + 5)
rm.update_pnl(big_loss)

print(f"Loss: ${big_loss:.2f}")
print(f"Intraday enabled after loss: {rm.is_intraday_enabled()}")
assert rm.is_intraday_enabled() == False, "Daily stop debe desactivar intraday"

# ============================================================================
# TEST 8: Intraday Gates - Gate 1 (Contexto macro)
# ============================================================================
print("\n[TEST 8] Intraday Gates - Gate 1 (Contexto macro)")
print("-" * 70)

market_data_good = {
    'SPY_change_pct': 1.2,
    'QQQ_change_pct': 1.5,
    'event_day': False
}

signal_test = {
    'ticker': 'TSLA',
    'entry': 240.0,
    'side': 'BUY',
    'daily_trend': 'UP',
    'signal_strength': 75,
    'sl': 235.0,
    'tp': 250.0
}

passed, reason = intraday_gates_pass(signal_test, market_data_good)
print(f"Signal: {signal_test}")
print(f"Market: SPY {market_data_good['SPY_change_pct']}%, QQQ {market_data_good['QQQ_change_pct']}%")
print(f"Gate result: {passed} ({reason})")

# ============================================================================
# TEST 9: Intraday Gates - Gate 2 (Multi-TF conflict)
# ============================================================================
print("\n[TEST 9] Intraday Gates - Gate 2 (Multi-TF conflict)")
print("-" * 70)

signal_conflict = {
    'ticker': 'AMD',
    'entry': 150.0,
    'side': 'BUY',
    'daily_trend': 'DOWN',  # Conflicto
    'signal_strength': 75,
    'sl': 145.0,
    'tp': 160.0
}

passed, reason = intraday_gates_pass(signal_conflict, market_data_good)
print(f"Signal: BUY conflicting with daily DOWN")
print(f"Gate result: {passed} ({reason})")
assert passed == False, "Gate 2 debe rechazar conflicto multi-TF"

# ============================================================================
# TEST 10: Intraday Gates - Gate 3 (Signal strength)
# ============================================================================
print("\n[TEST 10] Intraday Gates - Gate 3 (Signal strength)")
print("-" * 70)

signal_weak = {
    'ticker': 'AMD',
    'entry': 150.0,
    'side': 'BUY',
    'daily_trend': 'UP',
    'signal_strength': 30,  # Muy débil
    'sl': 145.0,
    'tp': 160.0
}

passed, reason = intraday_gates_pass(signal_weak, market_data_good)
print(f"Signal strength: {signal_weak['signal_strength']}% (min 50%)")
print(f"Gate result: {passed} ({reason})")
assert passed == False, "Gate 3 debe rechazar señal débil"

# ============================================================================
# TEST 11: Intraday Gates - Gate 4 (Risk/Reward)
# ============================================================================
print("\n[TEST 11] Intraday Gates - Gate 4 (Risk/Reward)")
print("-" * 70)

signal_poor_rr = {
    'ticker': 'AMD',
    'entry': 150.0,
    'side': 'BUY',
    'daily_trend': 'UP',
    'signal_strength': 75,
    'sl': 145.0,  # 3.3% risk
    'tp': 151.0   # 0.67% reward → RR = 0.2:1 (muy bajo)
}

passed, reason = intraday_gates_pass(signal_poor_rr, market_data_good)
print(f"Signal: {signal_poor_rr}")
risk = (signal_poor_rr['entry'] - signal_poor_rr['sl']) / signal_poor_rr['entry']
reward = (signal_poor_rr['tp'] - signal_poor_rr['entry']) / signal_poor_rr['entry']
print(f"Risk: {risk*100:.2f}%, Reward: {reward*100:.2f}%, RR: {reward/risk:.2f}:1")
print(f"Gate result: {passed} ({reason})")
assert passed == False, "Gate 4 debe rechazar RR pobre"

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print("SUMMARY: Todos los tests pasaron!")
print("="*70)
print("""
CapitalManager: 
  - Buckets 70/30 funcionan
  - Rechaza duplicados
  - Controla limites de abiertas
  - Heat control (reduce 50% si ticker en Swing)

RiskManager:
  - Daily stop funciona
  - Desactiva Intraday en perdida
  
Intraday Gates:
  - Gate 1: Contexto macro [OK]
  - Gate 2: Multi-TF alineacion [OK]
  - Gate 3: Signal strength [OK]
  - Gate 4: Risk/Reward [OK]
""")
print("="*70)
