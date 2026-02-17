#!/usr/bin/env python3
"""
run_optimal_strategy.py
Script automatizado para ejecutar la estrategia óptima Q1 2025.

Usage:
    python run_optimal_strategy.py --month 2025-03 --mode static
    python run_optimal_strategy.py --month 2025-03 --mode dynamic
"""

import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime

def run_static_strategy(month: str, backtest: bool = True):
    """
    Ejecuta estrategia STATIC GATE (conservadora).
    """
    print("\n" + "="*80)
    print("🔒 EJECUTANDO ESTRATEGIA STATIC GATE (Conservadora)")
    print("="*80)
    
    year, mon = month.split('-')
    
    # 1. Calcular último día del mes anterior
    if mon == '01':
        prev_year = int(year) - 1
        prev_month = 12
        asof_date = f"{prev_year}-12-31"
    else:
        prev_month = int(mon) - 1
        if prev_month in [1, 3, 5, 7, 8, 10, 12]:
            last_day = 31
        elif prev_month in [4, 6, 9, 11]:
            last_day = 30
        else:
            last_day = 28
        asof_date = f"{year}-{prev_month:02d}-{last_day}"
    
    print(f"\n📅 As-of Date: {asof_date}")
    
    # 2. Correr Ticker Gate
    print("\n🎯 PASO 1: Ticker Selection (Monte Carlo Gate)")
    gate_dir = f"evidence/ticker_gate_{mon}{year}"
    
    cmd_ticker = [
        "python", "montecarlo_gate.py",
        "--asof-date", asof_date,
        "--output-dir", gate_dir,
        "--n-days", "20",
        "--mc-paths", "400",
        "--top-k", "4"
    ]
    
    print(f"   Comando: {' '.join(cmd_ticker)}")
    result = subprocess.run(cmd_ticker, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"   ❌ Error en ticker gate:\n{result.stderr}")
        return False
    
    print("   ✅ Ticker gate completado")
    
    # 3. Leer tickers seleccionados
    gate_file = Path(gate_dir) / "ticker_gate.json"
    with open(gate_file) as f:
        gate_data = json.load(f)
    
    tickers = gate_data['selected_tickers']
    print(f"\n   🏆 Tickers seleccionados: {', '.join(tickers)}")
    
    # 4. Correr Param Gate (TP/SL)
    print("\n🎯 PASO 2: Parameter Optimization (TP/SL Gate)")
    param_dir = f"evidence/param_gate_{mon}{year}"
    
    cmd_param = [
        "python", "montecarlo_param_gate.py",
        "--gate-file", str(gate_file),
        "--output-dir", param_dir
    ]
    
    print(f"   Comando: {' '.join(cmd_param)}")
    result = subprocess.run(cmd_param, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"   ❌ Error en param gate:\n{result.stderr}")
        # Usar parámetros por defecto
        print("   ⚠️ Usando TP=1.6%, SL=1.0% por defecto")
    else:
        print("   ✅ Param gate completado")
    
    # 5. Backtest (opcional)
    if backtest:
        print(f"\n🎯 PASO 3: Backtest {month}")
        backtest_dir = f"evidence/gate_backtest_{mon}{year}"
        
        cmd_backtest = [
            "python", "paper/wf_paper_month.py",
            "--month", month,
            "--intraday", "C:/Users/M3400WUAK-WA023W/bmv_hybrid_clean_v3/data/us/intraday_15m/consolidated_15m.parquet",
            "--forecast", "data/daily/signals_with_gates.parquet",
            "--tickers-file", str(gate_file),
            "--tp-sl-choice", f"{param_dir}/tp_sl_choice.json",
            "--capital", "1000",
            "--exposure-cap", "800",
            "--execution-mode", "balanced",
            "--max-hold-days", "2",
            "--output-dir", backtest_dir
        ]
        
        print(f"   Comando: {' '.join(cmd_backtest[:5])}...")
        result = subprocess.run(cmd_backtest, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"   ❌ Error en backtest:\n{result.stderr}")
            return False
        
        print("   ✅ Backtest completado")
        
        # Leer resultados
        summary_file = Path(backtest_dir) / "summary.json"
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
            
            print("\n" + "="*80)
            print("📊 RESULTADOS BACKTEST")
            print("="*80)
            print(f"\n   P&L: ${summary.get('total_pnl', 0):.2f}")
            print(f"   Win Rate: {summary.get('win_rate', 0):.1%}")
            print(f"   Trades: {summary.get('total_trades', 0)}")
            print(f"   TP Hits: {summary.get('tp_hits', 0)} ({summary.get('tp_rate', 0):.1%})")
    
    print("\n" + "="*80)
    print("✅ ESTRATEGIA STATIC GATE COMPLETADA")
    print("="*80)
    
    return True

def run_dynamic_strategy(month: str):
    """
    Ejecuta estrategia DYNAMIC GATE (adaptativa).
    """
    print("\n" + "="*80)
    print("🔄 EJECUTANDO ESTRATEGIA DYNAMIC GATE (Adaptativa)")
    print("="*80)
    
    year, mon = month.split('-')
    
    # Correr Dynamic Gate
    print(f"\n📅 Mes: {month}")
    print("\n🎯 PASO 1: Dynamic Monte Carlo Gate (Rebalance Semanal)")
    
    dynamic_dir = f"evidence/dynamic_gate_{mon}{year}"
    
    cmd_dynamic = [
        "python", "montecarlo_gate_dynamic_v2.py",
        "--month", month,
        "--rebalance-freq", "weekly",
        "--top-k", "4",
        "--max-rotation", "2",
        "--output-dir", dynamic_dir,
        "--mc-paths", "400",
        "--n-days", "20"
    ]
    
    print(f"   Comando: {' '.join(cmd_dynamic)}")
    result = subprocess.run(cmd_dynamic, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"   ❌ Error en dynamic gate:\n{result.stderr}")
        return False
    
    print("   ✅ Dynamic gate completado")
    
    # Leer resultados
    dynamic_file = Path(dynamic_dir) / "dynamic_gate.json"
    with open(dynamic_file) as f:
        dynamic_data = json.load(f)
    
    print("\n" + "="*80)
    print("📊 EVOLUCIÓN DEL PORTAFOLIO")
    print("="*80)
    
    for rb in dynamic_data['rebalance_history']:
        num = rb['rebalance_number']
        date = rb['rebalance_date']
        portfolio = ' | '.join(rb['portfolio'])
        
        print(f"\n   {num}. {date}: {portfolio}")
        
        if rb['changes']['added'] or rb['changes']['dropped']:
            if rb['changes']['added']:
                print(f"      ➕ {', '.join(rb['changes']['added'])}")
            if rb['changes']['dropped']:
                print(f"      ➖ {', '.join(rb['changes']['dropped'])}")
    
    print("\n   🏆 Portafolio Final: {}", ' | '.join(dynamic_data['final_portfolio']))
    
    print("\n" + "="*80)
    print("✅ ESTRATEGIA DYNAMIC GATE COMPLETADA")
    print("="*80)
    print("\n💡 Nota: Para backtest con dynamic gate, usar portafolio final")
    print(f"   o implementar load_dynamic_tickers() en wf_paper_month.py")
    
    return True

def run_q1_complete():
    """
    Ejecuta estrategia completa para Q1 2025.
    """
    print("\n" + "="*80)
    print("🚀 EJECUTANDO ESTRATEGIA COMPLETA Q1 2025")
    print("="*80)
    
    months = ['2025-01', '2025-02', '2025-03']
    
    for month in months:
        print(f"\n{'='*80}")
        print(f"📅 PROCESANDO {month.upper()}")
        print(f"{'='*80}")
        
        # Static gate
        success = run_static_strategy(month, backtest=True)
        if not success:
            print(f"   ⚠️ Error en {month}, continuando...")
        
        # Dynamic gate
        success = run_dynamic_strategy(month)
        if not success:
            print(f"   ⚠️ Error en dynamic gate {month}, continuando...")
    
    print("\n" + "="*80)
    print("✅ ESTRATEGIA Q1 2025 COMPLETADA")
    print("="*80)
    
    # Análisis final
    print("\n🔍 Generando análisis comparativo...")
    result = subprocess.run(["python", "analyze_optimal_gates_q1.py"], 
                          capture_output=True, text=True)
    
    if result.returncode == 0:
        print(result.stdout)
    
    print("\n📄 Documentación completa en: OPTIMAL_STRATEGY_Q1_2025.md")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecutar estrategia óptima Q1 2025")
    parser.add_argument("--month", help="Mes en formato YYYY-MM (ej: 2025-03)")
    parser.add_argument("--mode", choices=['static', 'dynamic', 'q1-complete'], 
                       default='static',
                       help="Modo de ejecución")
    parser.add_argument("--no-backtest", action='store_true',
                       help="No ejecutar backtest (solo gate)")
    
    args = parser.parse_args()
    
    if args.mode == 'q1-complete':
        run_q1_complete()
    elif args.mode == 'static':
        if not args.month:
            print("❌ Error: --month requerido para modo static")
            exit(1)
        run_static_strategy(args.month, backtest=not args.no_backtest)
    elif args.mode == 'dynamic':
        if not args.month:
            print("❌ Error: --month requerido para modo dynamic")
            exit(1)
        run_dynamic_strategy(args.month)
