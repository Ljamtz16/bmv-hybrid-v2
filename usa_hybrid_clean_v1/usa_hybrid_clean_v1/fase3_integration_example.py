#!/usr/bin/env python3
"""
FASE 3: Example Integration Script
Muestra cómo registrar trades reales en el dashboard de validación.
"""

import requests
import json
from datetime import datetime, timedelta
import random
import time

API_BASE = 'http://localhost:8050'

def print_section(title):
    """Imprime una sección con título"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def check_readiness():
    """Verifica si el sistema está listo para Fase 3"""
    print_section("PHASE 3: READINESS CHECK")
    
    try:
        response = requests.get(f'{API_BASE}/api/phase3/checklist', timeout=5)
        data = response.json()
        
        print(f"Status: {data.get('phase')}")
        print(f"Ready: {'YES ✓' if data.get('ready') else 'NO ✗'}")
        
        print("\nCode Status:")
        for component, status in data.get('checks', {}).get('code_ready', {}).items():
            print(f"  {component}: {status}")
        
        print("\nValidation Status:")
        for check, status in data.get('checks', {}).get('validation', {}).items():
            print(f"  {check}: {status}")
        
        return data.get('ready', False)
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False


def get_phase2_metrics():
    """Obtiene métricas actuales de Fase 2"""
    print_section("PHASE 2: CURRENT METRICS")
    
    try:
        response = requests.get(f'{API_BASE}/api/phase2/metrics', timeout=5)
        data = response.json()
        
        metrics = data.get('metrics', {})
        
        print(f"Timestamp: {data.get('timestamp')}")
        
        # Swing
        swing = metrics.get('swing', {})
        print(f"\n[SWING] Trades: {swing.get('trades')}")
        print(f"  PnL: ${swing.get('pnl', 0):.2f}")
        print(f"  PF: {swing.get('pf', 0):.2f}")
        print(f"  Winrate: {swing.get('winrate', 0):.1f}%")
        print(f"  Avg Win/Loss: ${swing.get('avg_win', 0):.2f} / ${swing.get('avg_loss', 0):.2f}")
        
        # Intraday
        intraday = metrics.get('intraday', {})
        print(f"\n[INTRADAY] Trades: {intraday.get('trades')}")
        print(f"  PnL: ${intraday.get('pnl', 0):.2f}")
        print(f"  PF: {intraday.get('pf', 0):.2f}")
        print(f"  Winrate: {intraday.get('winrate', 0):.1f}%")
        print(f"  Avg Win/Loss: ${intraday.get('avg_win', 0):.2f} / ${intraday.get('avg_loss', 0):.2f}")
        
        # Capital
        cm = data.get('capital_manager', {})
        print(f"\n[CAPITAL]")
        print(f"  Swing: ${cm.get('open_swing', 0):.0f} / ${cm.get('swing_bucket', 0):.0f}")
        print(f"  Intraday: ${cm.get('open_intraday', 0):.0f} / ${cm.get('intraday_bucket', 0):.0f}")
        
        # Risk
        rm = data.get('risk_manager', {})
        print(f"\n[RISK]")
        print(f"  Daily PnL: ${rm.get('daily_pnl', 0):.2f}")
        print(f"  Drawdown: {rm.get('drawdown_pct', 0):.2f}%")
        print(f"  Intraday Enabled: {rm.get('intraday_enabled')}")
        
        return data
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None


def get_weekly_report():
    """Obtiene reporte semanal"""
    print_section("PHASE 2: WEEKLY REPORT")
    
    try:
        response = requests.get(f'{API_BASE}/api/phase2/weekly-report', timeout=5)
        data = response.json()
        
        report = data.get('report', {})
        decision = data.get('decision', {})
        
        swing = report.get('swing', {})
        print(f"\n[SWING] Week Summary")
        print(f"  Trades: {swing.get('trades')}")
        print(f"  PnL: ${swing.get('pnl', 0):.2f}")
        print(f"  PF: {swing.get('pf', 0):.2f}")
        print(f"  Winrate: {swing.get('winrate', 0):.1f}%")
        
        intraday = report.get('intraday', {})
        print(f"\n[INTRADAY] Week Summary")
        print(f"  Trades: {intraday.get('trades')}")
        print(f"  PnL: ${intraday.get('pnl', 0):.2f}")
        print(f"  PF: {intraday.get('pf', 0):.2f}")
        print(f"  Winrate: {intraday.get('winrate', 0):.1f}%")
        
        print(f"\n[DECISION]")
        print(f"  Recommendation: {decision.get('recommendation')}")
        print(f"  Intraday Enabled: {decision.get('intraday_enabled')}")
        
        return data
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None


def log_trade(book, ticker, side, entry, exit_price, qty, pnl, reason='TP'):
    """Registra un trade cerrado en Fase 3"""
    
    payload = {
        'book': book,
        'ticker': ticker,
        'side': side,
        'entry': entry,
        'exit': exit_price,
        'qty': qty,
        'pnl': pnl,
        'reason': reason
    }
    
    try:
        response = requests.post(
            f'{API_BASE}/api/phase3/log-trade',
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Trade logged: {book} {ticker} {side} @ {entry} -> {exit_price} (PnL: ${pnl:+.2f})")
            return True
        else:
            print(f"✗ Error: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        print(f"✗ Error logging trade: {str(e)}")
        return False


def simulate_phase3_trades(num_trades=10):
    """
    Simula ejecución de Fase 3 con trades de ejemplo.
    En producción, estos vendrían de tu sistema de ejecución.
    """
    print_section("PHASE 3: SIMULATE REAL TRADES")
    
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'META', 'SPY', 'QQQ']
    books = ['swing', 'swing', 'swing', 'intraday', 'intraday']  # 60% swing, 40% intraday
    
    logged = 0
    
    for i in range(num_trades):
        book = random.choice(books)
        ticker = random.choice(tickers)
        side = random.choice(['BUY', 'SELL'])
        
        # Precio base aproximado
        base_prices = {
            'AAPL': 225, 'MSFT': 415, 'GOOGL': 155,
            'TSLA': 240, 'META': 485, 'SPY': 510, 'QQQ': 395
        }
        base = base_prices.get(ticker, 200)
        
        # Entry con algo de variación
        entry = base * (1 + random.uniform(-0.02, 0.02))
        
        # Exit con probabilidad de ganancias (70% de probabilidad)
        if random.random() < 0.70:
            # Ganancia
            exit_price = entry * (1 + random.uniform(0.002, 0.015))
            pnl = (exit_price - entry) * (3 if book == 'swing' else 2)  # qty=3 swing, qty=2 intraday
        else:
            # Pérdida
            exit_price = entry * (1 - random.uniform(0.001, 0.008))
            pnl = (exit_price - entry) * (3 if book == 'swing' else 2)
        
        reason = random.choice(['TP', 'SL', 'TIME'])
        qty = 3 if book == 'swing' else 2
        
        # Log trade
        if log_trade(book, ticker, side, entry, exit_price, qty, pnl, reason):
            logged += 1
        
        time.sleep(0.1)  # Pequeña pausa para no saturar
    
    print(f"\n✓ Total trades logged: {logged}/{num_trades}")
    return logged > 0


def get_validation_plan():
    """Obtiene plan de validación actual para Fase 3"""
    print_section("PHASE 3: VALIDATION PLAN")
    
    try:
        response = requests.get(f'{API_BASE}/api/phase3/validation-plan', timeout=5)
        data = response.json()
        
        criteria = data.get('decision_criteria', {})
        
        print(f"\nCurrent Metrics:")
        metrics = data.get('current_metrics', {})
        print(f"  Swing PF: {metrics.get('swing', {}).get('pf', 0):.2f}")
        print(f"  Intraday PF: {metrics.get('intraday', {}).get('pf', 0):.2f}")
        
        print(f"\nDecision Criteria:")
        print(f"  Swing PF: {criteria.get('swing_pf', {}).get('value', 0):.2f} (req: {criteria.get('swing_pf', {}).get('requirement')})")
        print(f"  Intraday PF: {criteria.get('intraday_pf', {}).get('value', 0):.2f} (req: {criteria.get('intraday_pf', {}).get('requirement')})")
        print(f"  Intraday DD: {criteria.get('intraday_dd', {}).get('value', 0):.2f}% (req: {criteria.get('intraday_dd', {}).get('requirement')})")
        print(f"  Weeks: {criteria.get('weeks_collected', {}).get('value', 0)}/12 (req: {criteria.get('weeks_collected', {}).get('requirement')})")
        
        decision = data.get('next_decision', 'UNKNOWN')
        print(f"\nNext Decision: {decision}")
        
        # Mostrar últimas semanas
        reports = data.get('weekly_reports', [])
        if reports:
            print(f"\nLast {len(reports)} Weekly Reports:")
            for report in reports[-3:]:
                print(f"  Week {report.get('week', 'N/A')}: Swing PF={report.get('swing_pf', 0):.2f}, Intraday PF={report.get('intraday_pf', 0):.2f}")
        
        return data
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None


def main():
    """Script principal de demostración"""
    
    print_section("FASE 2-3: INTEGRATION EXAMPLE")
    print(f"API Base: {API_BASE}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Step 1: Verificar readiness
    print("\n[1/6] Checking system readiness...")
    if not check_readiness():
        print("\nERROR: System not ready. Make sure dashboard_unified_temp.py is running.")
        return
    
    # Step 2: Obtener métricas actuales
    print("\n[2/6] Getting Fase 2 metrics...")
    metrics = get_phase2_metrics()
    
    # Step 3: Obtener reporte semanal
    print("\n[3/6] Getting weekly report...")
    report = get_weekly_report()
    
    # Step 4: Simular trades Fase 3
    print("\n[4/6] Simulating Fase 3 trades...")
    simulate_phase3_trades(num_trades=5)
    
    # Step 5: Obtener métricas actualizadas
    print("\n[5/6] Getting updated metrics...")
    metrics_updated = get_phase2_metrics()
    
    # Step 6: Obtener plan de validación
    print("\n[6/6] Getting validation plan...")
    plan = get_validation_plan()
    
    # Final summary
    print_section("SUMMARY")
    print("\nFASE 2-3 integration complete!")
    print("\nNext steps:")
    print("  1. Monitor /api/phase2/metrics weekly")
    print("  2. Log trades via /api/phase3/log-trade")
    print("  3. Review /api/phase3/validation-plan at week 8-12")
    print("  4. Make final decision (Fase 2 afinada, Swing only, etc.)")


if __name__ == '__main__':
    main()
