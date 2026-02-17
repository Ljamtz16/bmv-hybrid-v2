# =============================================
# 40_make_trade_plan_intraday.py
# =============================================
"""
Genera plan de trading intraday con filtros estrictos y guardrails de capital.

Filtros:
- prob_win >= 0.65
- P(TP≺SL) >= 0.75  
- ETTH <= 0.25 días (~2h)
- spread <= 5 bps
- ATR 0.6%-2%

Guardrails:
- max_open = 4
- per_trade_cash = 250
- capital_total <= 1000
- max_per_ticker = 1
- max_sector_share = 60%

Ranking: E[PnL] / ETTH

Uso:
  python scripts/40_make_trade_plan_intraday.py --date 2025-11-03
"""

import argparse
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import json
import yaml


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--forecast-dir", default="reports/intraday", help="Directorio de forecast")
    ap.add_argument("--config", default="config/intraday.yaml", help="Archivo de configuración")
    ap.add_argument("--tp-pct", type=float, help="Take profit %")
    ap.add_argument("--sl-pct", type=float, help="Stop loss %")
    ap.add_argument("--per-trade-cash", type=float, help="Capital por trade")
    ap.add_argument("--max-open", type=int, help="Máximo trades simultáneos")
    ap.add_argument("--prob-win-min", type=float, help="Probabilidad mínima")
    ap.add_argument("--p-tp-sl-min", type=float, help="P(TP≺SL) mínima")
    ap.add_argument("--etth-max", type=float, help="ETTH máximo en días")
    ap.add_argument("--capital-max", type=float, help="Capital total máximo")
    # Flags para ensure-one (fallback controlado)
    ap.add_argument("--ensure-one", action="store_true",
                    help="Si no hay trades tras filtros, forzar 1 trade en modo fallback.")
    ap.add_argument("--ensure-exposure-max", type=float, default=650.0,
                        help="Exposure máximo en USD para el trade forzado (sin mínimo).")
    ap.add_argument("--fallback-prob-min", type=float, default=0.20,
                    help="Umbral de prob_win mínimo en fallback.")
    ap.add_argument("--fallback-ptpmin", type=float, default=0.15,
                    help="Umbral de P(TP<SL) mínimo en fallback.")
    ap.add_argument("--fallback-etth-max", type=float, default=0.30,
                    help="ETTH máximo (días) en fallback.")
    ap.add_argument("--fallback-cost", type=float, default=0.0003,
                    help="Costo para E[PnL] en fallback (paper).")
    return ap.parse_args()


def load_config(config_path):
    """Cargar configuración."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def load_forecast(date_str, forecast_dir):
    """Cargar forecast del día."""
    file_path = Path(forecast_dir) / date_str / "forecast_intraday.parquet"
    if not file_path.exists():
        print(f"[plan_intraday] ERROR: No existe {file_path}")
        return None
    
    df = pd.read_parquet(file_path)
    print(f"[plan_intraday] Cargado forecast: {len(df)} señales")
    return df


def load_tickers_master(tickers_file='data/us/tickers_master.csv'):
    """Cargar info de tickers (sector, etc)."""
    if not os.path.exists(tickers_file):
        return pd.DataFrame(columns=['ticker', 'sector'])
    
    df = pd.read_csv(tickers_file)
    if 'sector' not in df.columns:
        df['sector'] = 'Unknown'
    return df[['ticker', 'sector']]


def apply_filters(df, config, args):
    """Aplicar filtros de calidad basados en valor esperado.
    
    Política: Train conservador (TP=1.2%), trade agresivo (TP=2.8%)
    - Filtros de liquidez ya aplicados en script 11 (spread, ATR, volumen)
    - Aquí: filtros TTH + valor esperado positivo
    """
    print("\n[plan_intraday] Aplicando filtros...")
    print(f"  Inicial: {len(df)} señales")
    
    # === 1. Calcular E[PnL] = p*TP - (1-p)*SL - cost ===
    TP = args.tp_pct if getattr(args, 'tp_pct', None) else config.get('risk', {}).get('tp_pct', 0.028)
    SL = args.sl_pct if getattr(args, 'sl_pct', None) else config.get('risk', {}).get('sl_pct', 0.005)
    cost = 0.0005  # 5 bps costo implícito (spread + slippage)
    
    if 'p_tp_before_sl' not in df.columns:
        print("[plan_intraday] WARN: p_tp_before_sl no encontrada, usando 0.25 default")
        df['p_tp_before_sl'] = 0.25
    
    df['exp_pnl_pct'] = (
        df['p_tp_before_sl'] * TP - 
        (1 - df['p_tp_before_sl']) * SL - 
        cost
    )
    if 'ETTH' in df.columns:
        df['exp_pnl_per_time'] = df['exp_pnl_pct'] / df['ETTH'].clip(lower=1e-6)
    else:
        print("[plan_intraday] WARN: ETTH no encontrada, usando 0.25d por defecto")
        df['ETTH'] = 0.25
        df['exp_pnl_per_time'] = df['exp_pnl_pct'] / 0.25
    
    print(f"  E[PnL] calculado: media={df['exp_pnl_pct'].mean():.4f}, mediana={df['exp_pnl_pct'].median():.4f}")
    
    # === 2. Filtros mínimos TTH (suaves para intraday TP alto) ===
    p_tp_sl_min = args.p_tp_sl_min if hasattr(args, 'p_tp_sl_min') and args.p_tp_sl_min else config.get('filters', {}).get('p_tp_before_sl_min', 0.20)
    etth_max = args.etth_max if hasattr(args, 'etth_max') and args.etth_max else config.get('filters', {}).get('etth_max_days', 0.25)
    
    df = df[df['p_tp_before_sl'] >= p_tp_sl_min]
    print(f"  P(TP<SL) >= {p_tp_sl_min}: {len(df)} senales")
    
    if 'ETTH' in df.columns:
        df = df[df['ETTH'] <= etth_max]
        print(f"  ETTH <= {etth_max}d: {len(df)} señales")
    
    # === 3. Valor esperado positivo (clave!) ===
    df = df[df['exp_pnl_pct'] > 0]
    print(f"  E[PnL] > 0: {len(df)} señales")
    
    return df


def calculate_expected_pnl(df, tp_pct, sl_pct):
    """Calcular PnL esperado (legacy - ahora en apply_filters)."""
    # Mantengo para compatibilidad pero ya no se usa
    if 'p_tp_before_sl' not in df.columns:
        df['p_tp_before_sl'] = 0.20
    
    df['exp_pnl_pct'] = (
        df['p_tp_before_sl'] * tp_pct - 
        (1 - df['p_tp_before_sl']) * sl_pct
    )
    
    return df


def rank_candidates(df, config):
    """Rankear candidatos por eficiencia temporal (E[PnL]/ETTH)."""
    # Ya calculado en apply_filters
    if 'exp_pnl_per_time' not in df.columns:
        df['exp_pnl_per_time'] = df['exp_pnl_pct'] / df['ETTH'].clip(lower=1e-6)
    
    df = df.sort_values('exp_pnl_per_time', ascending=False)
    print(f"[plan_intraday] Ranking por E[PnL]/ETTH: Top-1 = {df['exp_pnl_per_time'].iloc[0]:.6f}" if len(df) > 0 else "[plan_intraday] Sin señales para rankear")
    return df


def apply_guardrails(df, config, args, df_fallback=None):
    """Aplicar guardrails de capital y diversificación.
    
    Args:
        df: DataFrame ranked (señales ordenadas para selección)
        config: Configuración
        args: Argumentos CLI
        df_fallback: DataFrame con todas las señales filtradas (para ensure-one)
    """
    print("\n[plan_intraday] Aplicando guardrails...")
    
    # Parámetros
    max_open = args.max_open if args.max_open else config.get('capital', {}).get('max_open', 4)
    per_trade_cash = args.per_trade_cash if args.per_trade_cash else config.get('capital', {}).get('per_trade_cash', 250)
    capital_max = args.capital_max if args.capital_max else config.get('capital', {}).get('max_total', 1000)
    max_per_ticker = config.get('plan', {}).get('max_per_ticker', 1)
    max_sector_share = config.get('plan', {}).get('max_sector_share', 0.6)
    
    print(f"  max_open={max_open}, per_trade=${per_trade_cash}, capital_max=${capital_max}")
    
    # Asegurar que tenemos sector
    if 'sector' not in df.columns:
        df['sector'] = 'Unknown'
    
    # Selección con guardrails
    selected = []
    ticker_count = {}
    sector_capital = {}
    total_capital = 0.0

    for idx, row in df.iterrows():
        # Check max_open
        if len(selected) >= max_open:
            print(f"  Límite max_open alcanzado: {len(selected)}")
            break

        price = float(row.get('close', np.nan))
        if not np.isfinite(price) or price <= 0:
            continue

        # Capital restante y sizing por trade
        cash_left = max(capital_max - total_capital, 0.0)
        if cash_left < 1e-6:
            print(f"  Límite de capital alcanzado: ${total_capital:.2f}")
            break

        cash_for_trade = min(per_trade_cash, cash_left)

        # Check max_per_ticker y max_sector_share usando cash_for_trade estimado
        ticker = row['ticker']
        sector = row.get('sector', 'Unknown')
        if ticker_count.get(ticker, 0) >= max_per_ticker:
            continue
        if sector_capital.get(sector, 0.0) + cash_for_trade > capital_max * max_sector_share:
            continue

        # Calcular qty (solo cantidades enteras)
        qty = int(cash_for_trade // price)
        if qty < 1:
            # Política: saltar si no alcanza 1 acción con per_trade_cash
            continue

        exposure = qty * price
        if exposure < 1e-6:
            continue

        # Aprobar y actualizar contadores con exposure real
        selected.append(row)
        ticker_count[ticker] = ticker_count.get(ticker, 0) + 1
        sector_capital[sector] = sector_capital.get(sector, 0.0) + exposure
        total_capital += exposure
    
    # === FALLBACK: Ensure-One (si plan vacío y flag activado) ===
    if getattr(args, 'ensure_one', False) and len(selected) == 0:
        print("\n[plan_intraday] FALLBACK: Activando ensure-one (plan vacío)")
        # Usar df_fallback si está disponible (señales filtradas pre-ranking), sino df ranked
        fb = df_fallback.copy() if df_fallback is not None and not df_fallback.empty else df.copy()
        
        # Recalcular exp_pnl_pct con costo fallback si necesario
        fb_cost = getattr(args, 'fallback_cost', 0.0003)
        if 'exp_pnl_pct' not in fb.columns or fb_cost != 0.0005:
            tp_pct_fb = args.tp_pct if args.tp_pct else config.get('risk', {}).get('tp_pct', 0.028)
            sl_pct_fb = args.sl_pct if args.sl_pct else config.get('risk', {}).get('sl_pct', 0.005)
            p = fb['p_tp_before_sl'].astype(float).clip(0, 1)
            fb['exp_pnl_pct'] = p * tp_pct_fb - (1 - p) * sl_pct_fb - fb_cost
        
        # Filtros de fallback (más laxos pero con E[PnL]>0)
        fb_prob_min = getattr(args, 'fallback_prob_min', 0.20)
        fb_ptp_min = getattr(args, 'fallback_ptpmin', 0.15)
        fb_etth_max = getattr(args, 'fallback_etth_max', 0.30)
        
        fb = fb[
            (fb['exp_pnl_pct'] > 0.0) &
            (fb['ETTH'].astype(float) <= fb_etth_max) &
            (fb['prob_win'].astype(float) >= fb_prob_min) &
            (fb['p_tp_before_sl'].astype(float) >= fb_ptp_min)
        ].copy()
        
        print(f"  Candidatos fallback (E[PnL]>0, prob≥{fb_prob_min}, P(TP<SL)≥{fb_ptp_min}, ETTH≤{fb_etth_max}d): {len(fb)}")
        
        if len(fb) > 0:
            # Ranking por eficiencia temporal
            if 'rank_score' not in fb.columns:
                fb['rank_score'] = fb['exp_pnl_pct'] / fb['ETTH'].clip(lower=1e-6)
            
            # Ordenar por eficiencia
            fb_sorted = fb.sort_values('rank_score', ascending=False)
            
            # Iterar sobre candidatos hasta encontrar uno con exposure válido
            found = False
            for idx, row in fb_sorted.iterrows():
                price = float(row.get('close', row.get('entry_price', np.nan)))
                
                if not np.isfinite(price) or price <= 0:
                    continue
                
                cash_left = max(capital_max - total_capital, 0.0)
                if cash_left < 1.0:
                    print(f"  [fallback] Sin capital disponible (${cash_left:.2f})")
                    break
                
                # Objetivo de exposure: máximo $650 (sin mínimo)
                target_max = getattr(args, 'ensure_exposure_max', 650.0)

                # Solo cantidades enteras (sin fracciones)
                # Calcular qty máximo que cabe en target_max y cash_left
                qty_max_by_target = int(target_max // price)
                qty_max_by_cash = int(cash_left // price)
                qty = min(max(1, qty_max_by_target), qty_max_by_cash)
                exposure = qty * price

                # Verificar límites de exposure
                if qty >= 1 and exposure <= target_max and exposure <= cash_left:
                    row['qty'] = qty
                    row['exposure'] = exposure
                    selected.append(row)
                    total_capital += exposure
                    print(f"  ✅ Fallback: {row['ticker']} {row.get('direction', 'LONG')} @ ${price:.2f}, qty={qty}, exposure=${exposure:.2f}")
                    found = True
                    break  # Encontrado trade válido, salir del loop
                else:
                    print(f"  [fallback] {row['ticker']}: exposure ${exposure:.2f} excede máximo ${target_max:.2f} o cash disponible, probando siguiente...")
                    continue  # Probar siguiente candidato

            if not found:
                print("  [fallback] Sin candidatos válidos con E[PnL]>0")
    
    if not selected:
        return pd.DataFrame(columns=df.columns)
    
    df_selected = pd.DataFrame(selected)
    print(f"  Seleccionados: {len(df_selected)} trades")
    print(f"  Capital usado: ${total_capital:.2f} / ${capital_max}")
    
    return df_selected


def prepare_execution_plan(df, config, args, date_str):
    """Preparar plan ejecutable con precios y cantidades para LONG y SHORT."""
    tp_pct = args.tp_pct if args.tp_pct else config.get('risk', {}).get('tp_pct', 0.028)
    sl_pct = args.sl_pct if args.sl_pct else config.get('risk', {}).get('sl_pct', 0.005)
    per_trade_cash = args.per_trade_cash if args.per_trade_cash else config.get('capital', {}).get('per_trade_cash', 250)
    max_open = args.max_open if args.max_open else config.get('capital', {}).get('max_open', 4)
    capital_max = args.capital_max if args.capital_max else config.get('capital', {}).get('max_total', 1000)
    
    # ===== HARD-STOPS DE RIESGO (OBLIGATORIOS) =====
    # Calcular exposure real basado en qty × price (no per_trade_cash teórico)
    if 'exposure' in df.columns:
        total_exposure = df['exposure'].sum()
    else:
        total_exposure = per_trade_cash * len(df)
    
    # 1) Verificar capital total no excede límite
    if total_exposure > capital_max:
        print(f"[plan_intraday] WARN: Exposure ${total_exposure:.0f} > ${capital_max:.0f} - Ajustando plan")
        df = df.head(max_open)  # Limitar a max_open mejores trades
        total_exposure = df['exposure'].sum() if 'exposure' in df.columns else per_trade_cash * len(df)
    
    # 2) Hard-stop final: capital expuesto <= límite (solo si el plan tiene trades)
    if len(df) > 0:
        assert total_exposure <= capital_max, \
            f"HARD-STOP VIOLATED: total_exposure ${total_exposure:.0f} > capital_max ${capital_max}"
    
    print(f"[plan_intraday] OK Capital check: ${total_exposure:.0f} / ${capital_max:.0f} ({len(df)} trades)")
    
    df = df.copy()
    
    # Asegurar que tenemos dirección
    if 'direction' not in df.columns:
        df['direction'] = 'LONG'
    
    # Calcular precios y cantidades según dirección
    df['entry_price'] = df['close']
    
    # LONG: TP arriba, SL abajo
    df.loc[df['direction'] == 'LONG', 'tp_price'] = df['entry_price'] * (1 + tp_pct)
    df.loc[df['direction'] == 'LONG', 'sl_price'] = df['entry_price'] * (1 - sl_pct)
    
    # SHORT: TP abajo, SL arriba (invertido)
    df.loc[df['direction'] == 'SHORT', 'tp_price'] = df['entry_price'] * (1 - tp_pct)
    df.loc[df['direction'] == 'SHORT', 'sl_price'] = df['entry_price'] * (1 + sl_pct)
    
    # Recalcular qty/exposure (solo cantidades enteras)
    def _calc_qty(price):
        return float(int(per_trade_cash // price))

    if 'qty' in df.columns:
        df['qty'] = df['qty'].astype(float)
        # Completar qty faltantes usando per_trade_cash, pero preservar las ya definidas (p.ej., fallback)
        df['qty'] = df.apply(lambda r: r['qty'] if np.isfinite(r.get('qty', np.nan)) and r['qty'] > 0 else _calc_qty(r['entry_price']), axis=1)
    else:
        df['qty'] = df['entry_price'].apply(_calc_qty)
    df['exposure'] = df['qty'] * df['entry_price']
    
    # Metadata
    df['date'] = date_str
    df['created_at'] = datetime.now().isoformat()
    df['status'] = 'PENDING'
    
    # Columnas clave para el plan
    plan_cols = [
        'date', 'ticker', 'sector', 'direction',
        'entry_price', 'tp_price', 'sl_price',
        'qty', 'exposure',
        'prob_win', 'p_tp_before_sl', 'ETTH', 'exp_pnl_pct', 'rank_score',
        'ATR_pct', 'spread_bps', 'volume_ratio',
        'timestamp', 'status', 'created_at'
    ]
    
    # Seleccionar columnas disponibles
    available_cols = [c for c in plan_cols if c in df.columns]
    df_plan = df[available_cols].copy()
    
    return df_plan


def generate_telegram_message(df_plan, config):
    """Generar mensaje para Telegram con LONG y SHORT."""
    if df_plan.empty:
        return "⚠️ INTRADAY: Sin señales para hoy"
    
    date_str = df_plan['date'].iloc[0]
    n_trades = len(df_plan)
    n_long = (df_plan['direction'] == 'LONG').sum()
    n_short = (df_plan['direction'] == 'SHORT').sum()
    total_exposure = df_plan['exposure'].sum()
    
    msg = f"📊 **Plan Intraday {date_str}**\n\n"
    msg += f"Trades: {n_trades} ({n_long}L/{n_short}S)\n"
    msg += f"Exposure: ${total_exposure:,.0f}\n\n"
    
    for idx, row in df_plan.iterrows():
        ticker = row['ticker']
        direction = row.get('direction', 'LONG')
        entry = row['entry_price']
        tp = row['tp_price']
        sl = row['sl_price']
        prob = row.get('prob_win', 0)
        etth = row.get('ETTH', 0)
        
        # Calcular % correctamente según dirección
        if direction == 'LONG':
            tp_pct = ((tp - entry) / entry) * 100
            sl_pct = ((sl - entry) / entry) * 100
            emoji = "📈"
        else:  # SHORT
            tp_pct = ((entry - tp) / entry) * 100  # Invertido
            sl_pct = ((entry - sl) / entry) * 100
            emoji = "📉"
        
        msg += f"{emoji} **{ticker} {direction}**\n"
        msg += f"  Entry: ${entry:.2f}\n"
        msg += f"  TP: ${tp:.2f} ({tp_pct:+.1f}%)\n"
        msg += f"  SL: ${sl:.2f} ({sl_pct:+.1f}%)\n"
        msg += f"  Prob: {prob:.1%}, ETTH: {etth:.2f}d\n"
        msg += f"  Qty: {row.get('qty', 0)} | Exposure: ${row.get('exposure', 0):.2f}\n\n"
    
    return msg


def main():
    args = parse_args()
    config = load_config(args.config)
    
    print(f"[plan_intraday] Fecha: {args.date}")
    
    # Cargar forecast
    df = load_forecast(args.date, args.forecast_dir)
    if df is None or df.empty:
        print("[plan_intraday] ERROR: No hay forecast")
        return
    
    # Cargar info de tickers
    tickers_info = load_tickers_master()
    if not tickers_info.empty and 'ticker' in df.columns:
        df = df.merge(tickers_info, on='ticker', how='left')
        df['sector'] = df['sector'].fillna('Unknown')
    
    # Calcular expected PnL
    tp_pct = args.tp_pct if args.tp_pct else config.get('risk', {}).get('tp_pct', 0.028)
    sl_pct = args.sl_pct if args.sl_pct else config.get('risk', {}).get('sl_pct', 0.005)
    df = calculate_expected_pnl(df, tp_pct, sl_pct)
    
    # Guardar forecast original para fallback (antes de filtros estrictos)
    df_pre_filters = df.copy()
    
    # Filtros
    df_filtered = apply_filters(df, config, args)
    if df_filtered.empty:
        print("[plan_intraday] WARN: No quedan señales después de filtros")
    
    # Rankear
    df_ranked = rank_candidates(df_filtered, config)
    
    # Guardrails (pasar df_pre_filters para fallback)
    df_plan = apply_guardrails(df_ranked, config, args, df_fallback=df_pre_filters)
    
    # Preparar plan ejecutable
    df_exec = prepare_execution_plan(df_plan, config, args, args.date)
    
    # Guardar
    out_dir = Path(args.forecast_dir) / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Candidatos (Top-15)
    top_n = config.get('plan', {}).get('top_n', 15)
    df_candidates = df_ranked.head(top_n)
    out_candidates = out_dir / "trade_candidates_intraday.csv"
    df_candidates.to_csv(out_candidates, index=False)
    print(f"\n[plan_intraday] Candidatos guardados: {out_candidates} ({len(df_candidates)} filas)")
    
    # Plan ejecutable
    out_plan = out_dir / "trade_plan_intraday.csv"
    df_exec.to_csv(out_plan, index=False)
    print(f"[plan_intraday] Plan guardado: {out_plan} ({len(df_exec)} trades)")
    
    # Mensaje Telegram
    telegram_msg = generate_telegram_message(df_exec, config)
    out_telegram = out_dir / "telegram_message.txt"
    with open(out_telegram, 'w', encoding='utf-8') as f:
        f.write(telegram_msg)
    print(f"[plan_intraday] Mensaje Telegram: {out_telegram}")
    
    # Stats JSON
    stats = {
        'date': args.date,
        'n_signals_initial': len(df),
        'n_signals_filtered': len(df_filtered),
        'n_candidates': len(df_candidates),
        'n_plan': len(df_exec),
        'total_exposure': float(df_exec['exposure'].sum()) if not df_exec.empty else 0,
        'avg_prob_win': float(df_exec['prob_win'].mean()) if not df_exec.empty else 0,
        'avg_etth': float(df_exec['ETTH'].mean()) if 'ETTH' in df_exec.columns and not df_exec.empty else 0
    }
    out_stats = out_dir / "plan_stats.json"
    with open(out_stats, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"[plan_intraday] Stats: {out_stats}")
    
    # Resumen
    print(f"\n[plan_intraday] ===== RESUMEN =====")
    print(f"  Señales iniciales: {stats['n_signals_initial']}")
    print(f"  Post-filtros: {stats['n_signals_filtered']}")
    print(f"  Plan final: {stats['n_plan']} trades")
    print(f"  Exposure total: ${stats['total_exposure']:,.0f}")
    if stats['n_plan'] > 0:
        print(f"  Prob win media: {stats['avg_prob_win']:.1%}")
        print(f"  ETTH media: {stats['avg_etth']:.2f} días")


if __name__ == "__main__":
    main()
