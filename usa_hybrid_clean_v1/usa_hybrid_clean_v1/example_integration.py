#!/usr/bin/env python3
"""
EJEMPLO: Integración de CapitalManager + RiskManager + Intraday Gates
Muestra cómo orquestar un trade desde generación hasta ejecución.
"""
import sys
sys.path.insert(0, '.')

from dashboard_unified_temp import (
    CapitalManager, RiskManager, intraday_gates_pass,
    logger
)
from datetime import datetime

# ============================================================================
# SETUP INICIAL
# ============================================================================

# Instancias globales (ya existen en dashboard_unified_temp.py)
from dashboard_unified_temp import CAPITAL_MANAGER, RISK_MANAGER

# Simulamos estado del mercado
MARKET_CONTEXT = {
    'SPY_change_pct': 1.3,
    'QQQ_change_pct': 1.5,
    'event_day': False,
    'timestamp': datetime.now()
}

# Registro de trades ejecutados (para demo)
executed_trades = []
pnl_history = []

print("\n" + "="*70)
print("EJEMPLO: Orquestación de Swing + Fase 2 (Intraday)")
print("="*70)

# ============================================================================
# FUNCIÓN: Ejecutar trade con validaciones
# ============================================================================

def execute_signal(signal):
    """
    Procesa una señal a través de todas las capas de validación.
    Retorna: (executed: bool, reason: str)
    """
    
    book = signal.get('book', 'swing')
    ticker = signal.get('ticker', '')
    
    logger.info(f"\n[FLOW] Processing {book.upper()} signal for {ticker}")
    
    # PASO 1: CapitalManager valida disponibilidad
    if not CAPITAL_MANAGER.allows(signal):
        reason = "CapitalManager denied (insufficient capital or limit exceeded)"
        logger.warning(f"[FLOW] {reason}")
        return False, reason
    
    logger.info(f"[FLOW] CapitalManager: PASS")
    
    # PASO 2: Si es Intraday, chequea RiskManager
    if book == 'intraday':
        if not RISK_MANAGER.is_intraday_enabled():
            reason = "Intraday disabled (kill-switch active)"
            logger.warning(f"[FLOW] {reason}")
            return False, reason
        
        logger.info(f"[FLOW] RiskManager: intraday ENABLED")
        
        # PASO 3: Intraday pasa por 4 Gates
        gates_passed, gate_reason = intraday_gates_pass(signal, MARKET_CONTEXT)
        
        if not gates_passed:
            reason = f"Intraday gates rejected: {gate_reason}"
            logger.warning(f"[FLOW] {reason}")
            return False, reason
        
        logger.info(f"[FLOW] Intraday Gates: ALL PASS")
    
    # PASO 4: EJECUTAR
    logger.info(f"[FLOW] EXECUTING: {book.upper()} {signal['side']} {ticker} @ {signal['entry']}")
    
    executed_trades.append({
        'timestamp': datetime.now(),
        'book': book,
        'ticker': ticker,
        'side': signal['side'],
        'entry': signal['entry'],
        'qty': signal['qty'],
        'sl': signal.get('sl'),
        'tp': signal.get('tp'),
        'status': 'OPEN'
    })
    
    CAPITAL_MANAGER.add_open(book, ticker, signal['qty'])
    
    return True, "Executed successfully"

# ============================================================================
# FUNCIÓN: Cerrar trade y actualizar RiskManager
# ============================================================================

def close_trade(ticker, book, exit_price, book_):
    """Cierra un trade y actualiza PnL"""
    
    trade = next((t for t in executed_trades if t['ticker'] == ticker and t['book'] == book and t['status'] == 'OPEN'), None)
    
    if not trade:
        logger.warning(f"[CLOSE] Trade not found: {book} {ticker}")
        return
    
    entry_price = trade['entry']
    qty = trade['qty']
    pnl = (exit_price - entry_price) * qty
    
    logger.info(f"[CLOSE] {book.upper()} {ticker}: entry={entry_price}, exit={exit_price}, PnL=${pnl:.2f}")
    
    trade['status'] = 'CLOSED'
    trade['exit_price'] = exit_price
    trade['pnl'] = pnl
    
    # Actualiza RiskManager
    RISK_MANAGER.update_pnl(pnl)
    
    # Libera capital
    CAPITAL_MANAGER.remove_open(book, ticker)
    
    pnl_history.append({
        'book': book,
        'ticker': ticker,
        'pnl': pnl
    })

# ============================================================================
# ESCENARIO 1: Swing Trade válido
# ============================================================================

print("\n[SCENARIO 1] Swing Trade válido")
print("-" * 70)

swing_signal_1 = {
    'book': 'swing',
    'ticker': 'AAPL',
    'entry': 180.0,
    'qty': 3,
    'side': 'BUY',
    'sl': 175.0,
    'tp': 190.0
}

executed, reason = execute_signal(swing_signal_1)
print(f"Result: {executed} ({reason})")

# ============================================================================
# ESCENARIO 2: Swing Trade #2
# ============================================================================

print("\n[SCENARIO 2] Segundo Swing Trade")
print("-" * 70)

swing_signal_2 = {
    'book': 'swing',
    'ticker': 'MSFT',
    'entry': 380.0,
    'qty': 2,
    'side': 'BUY',
    'sl': 370.0,
    'tp': 395.0
}

executed, reason = execute_signal(swing_signal_2)
print(f"Result: {executed} ({reason})")

# ============================================================================
# ESCENARIO 3: Intraday Trade con Good Gates
# ============================================================================

print("\n[SCENARIO 3] Intraday Trade (todas las gates pasan)")
print("-" * 70)

intraday_signal_1 = {
    'book': 'intraday',
    'ticker': 'TSLA',
    'entry': 240.0,
    'qty': 2,
    'side': 'BUY',
    'sl': 236.0,        # 1.67% risk
    'tp': 250.0,        # 4.17% reward → RR = 2.5:1
    'daily_trend': 'UP',
    'signal_strength': 75,
}

executed, reason = execute_signal(intraday_signal_1)
print(f"Result: {executed} ({reason})")

# ============================================================================
# ESCENARIO 4: Intraday Trade rechazado por conflicto multi-TF
# ============================================================================

print("\n[SCENARIO 4] Intraday Trade (rechazado por Gate 2)")
print("-" * 70)

intraday_signal_reject = {
    'book': 'intraday',
    'ticker': 'AMD',
    'entry': 150.0,
    'qty': 2,
    'side': 'BUY',
    'sl': 145.0,
    'tp': 160.0,
    'daily_trend': 'DOWN',  # CONFLICTO: BUY but daily DOWN
    'signal_strength': 75,
}

executed, reason = execute_signal(intraday_signal_reject)
print(f"Result: {executed} ({reason})")

# ============================================================================
# ESCENARIO 5: Intenta tercer Swing pero ya hay límite de 3
# ============================================================================

print("\n[SCENARIO 5] Swing Trade #3 (cumple límite de 3)")
print("-" * 70)

swing_signal_3 = {
    'book': 'swing',
    'ticker': 'GOOGL',
    'entry': 150.0,
    'qty': 2,
    'side': 'BUY',
    'sl': 145.0,
    'tp': 160.0
}

executed, reason = execute_signal(swing_signal_3)
print(f"Result: {executed} ({reason})")

# ============================================================================
# ESTADO ACTUAL
# ============================================================================

print("\n" + "="*70)
print("ESTADO ACTUAL DEL SISTEMA")
print("="*70)

print(f"\nOpened Swing: {CAPITAL_MANAGER.open_swing}")
print(f"Opened Intraday: {CAPITAL_MANAGER.open_intraday}")
print(f"Total open: {CAPITAL_MANAGER.get_open_count('all')}")

print(f"\nSwing bucket available: ${CAPITAL_MANAGER.available_swing():.2f}")
print(f"Intraday bucket available: ${CAPITAL_MANAGER.available_intraday():.2f}")

print(f"\nRiskManager status:")
print(f"  Intraday enabled: {RISK_MANAGER.is_intraday_enabled()}")
print(f"  Loss today: ${RISK_MANAGER.intraday_loss_today:.2f}")

print(f"\nExecuted trades ({len(executed_trades)}):")
for trade in executed_trades:
    print(f"  - {trade['book'].upper()} {trade['side']} {trade['ticker']} @ {trade['entry']} (qty={trade['qty']}, status={trade['status']})")

# ============================================================================
# SIMULAR CIERRE DE TRADES Y ACTUALIZACIÓN DE PnL
# ============================================================================

print("\n" + "="*70)
print("SIMULANDO CIERRES Y ACTUALIZACIÓN DE PnL")
print("="*70)

print("\n[CLOSE] AAPL cierra con ganancia")
close_trade('AAPL', 'swing', exit_price=185.0, book_='swing')

print("\n[CLOSE] TSLA cierra con pérdida")
close_trade('TSLA', 'intraday', exit_price=238.0, book_='intraday')

# ============================================================================
# REPORTE FINAL
# ============================================================================

print("\n" + "="*70)
print("REPORTE DE PnL POR LIBRO")
print("="*70)

swing_pnl = sum(p['pnl'] for p in pnl_history if p['book'] == 'swing')
intraday_pnl = sum(p['pnl'] for p in pnl_history if p['book'] == 'intraday')
total_pnl = swing_pnl + intraday_pnl

print(f"\nSwing PnL: ${swing_pnl:.2f}")
print(f"Intraday PnL: ${intraday_pnl:.2f}")
print(f"Total PnL: ${total_pnl:.2f}")

print(f"\nDetalle:")
for p in pnl_history:
    sign = '+' if p['pnl'] > 0 else ''
    print(f"  {p['book'].upper()} {p['ticker']}: {sign}${p['pnl']:.2f}")

print(f"\nRiskManager final status:")
status = RISK_MANAGER.get_status()
print(f"  Intraday enabled: {status['intraday_enabled']}")
print(f"  Intraday loss today: ${status['intraday_loss_today']:.2f}")
print(f"  Drawdown %: {status['drawdown_pct']:.2f}%")

print("\n" + "="*70)
print("FIN DEL EJEMPLO")
print("="*70)
