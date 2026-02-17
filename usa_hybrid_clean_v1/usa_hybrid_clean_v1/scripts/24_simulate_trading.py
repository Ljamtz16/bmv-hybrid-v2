# =============================================
# 24_simulate_trading.py
# =============================================
import pandas as pd, argparse, os
from datetime import datetime, timezone
import math

def simulate(df,tp=0.07,sl=0.01,capital_initial=1100,cash_per_trade=200.0):
    pnl=[]
    n_all=len(df)
    n_gated=0
    for _,r in df.iterrows():
        gate_col = 'gate_pattern_ok' if 'gate_pattern_ok' in df.columns else 'gate_ok'
        if int(r.get(gate_col, 0)) != 1:
            continue
        n_gated += 1
        ret = r.get('y_hat', 0.0)
        if ret >= tp:
            pnl.append(tp)
        elif ret <= -sl:
            pnl.append(-sl)
        else:
            pnl.append(ret)
    # Cada trade usa un capital fijo por operación
    net = sum(pnl) * cash_per_trade
    win_rate = (pd.Series(pnl) > 0).mean() if pnl else 0.0
    return {
        'rows_total': n_all,
        'rows_gated': n_gated,
        'trades': len(pnl),
        'win_rate': win_rate,
        'net_pnl_sum': net,
        'capital_final': capital_initial + net
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--month",required=True)
    ap.add_argument("--capital-initial",type=float,default=1100)
    ap.add_argument("--tp-pct",type=float,default=0.07)
    ap.add_argument("--sl-pct",type=float,default=0.01)
    ap.add_argument("--per-trade-cash", type=float, default=200.0, help="Capital fijo por operación (USD).")
    ap.add_argument("--allow-fractional", action="store_true", help="Permite fracciones de acción si el broker lo soporta.")
    ap.add_argument("--horizon-days",type=int,default=3)
    ap.add_argument("--forecast_dir",default="reports/forecast")
    ap.add_argument("--source-file", default="", help="Nombre de archivo dentro del mes: p.ej. forecast_with_patterns.csv; si vacío usa forecast_signals.csv")
    ap.add_argument("--tickers", default="", help="Archivo CSV con tickers sectoriales")
    ap.add_argument("--min-prob", type=float, default=0.0, help="Filtra prob_win >= este umbral (0 desactiva)")
    ap.add_argument("--min-abs-yhat", type=float, default=0.0, help="Filtra |y_hat| >= este umbral (0 desactiva)")
    ap.add_argument("--simulate-results-out", default="simulate_results.csv", help="Nombre del CSV de trades simulados a escribir")
    # Position-active options
    ap.add_argument("--position-active", action="store_true", help="Simula con capital, posiciones abiertas y cooldown")
    ap.add_argument("--max-open", type=int, default=0, help="Máximo de posiciones abiertas simultáneas (0 = sin límite -> modo legacy)")
    ap.add_argument("--cooldown-days", type=int, default=0, help="Días de espera tras cerrar un ticker antes de reabrir")
    ap.add_argument("--lock-same-ticker", action="store_true", help="Evita múltiples posiciones simultáneas en el mismo ticker")
    ap.add_argument("--sort-signals-by", choices=["prob_win","abs_yhat"], default="prob_win", help="Orden diario de señales al asignar capital")
    ap.add_argument("--horizon-dynamic-atr", action="store_true", help="Usa H=4 si atr_pct del día supera p75 mensual; si no, usa --horizon-days")
    ap.add_argument("--horizon-days-high-atr", type=int, default=4, help="Horizonte a usar cuando atr está alta")
    # Re-entrada tras TP
    ap.add_argument("--allow-reentry-after-tp", action="store_true", help="Permite re-entrada si la última salida fue TP y el ticker sigue válido")
    ap.add_argument("--reentry-yhat-min", type=float, default=0.04, help="Umbral mínimo de |y_hat| para permitir re-entrada tras TP")
    ap.add_argument("--reentry-atr-min", type=float, default=0.02, help="Umbral mínimo de ATR para permitir re-entrada tras TP")
    # Mini-rebalance para liberar slots
    ap.add_argument("--rebalance-every-days", type=int, default=0, help="Cada N días cierra posiciones de menor calidad para liberar slots (0 = desactivado)")
    ap.add_argument("--rebalance-close-k", type=int, default=1, help="Número de posiciones a cerrar en cada rebalance si no hay slots libres")
    args=ap.parse_args()

    source = args.source_file.strip() or "forecast_signals.csv"
    f=os.path.join(args.forecast_dir,args.month, source)
    df=pd.read_csv(f)
    # Asegurar tipo datetime y filtrar solo el mes indicado
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        month_mask = df['date'].dt.strftime('%Y-%m') == args.month
        df = df[month_mask].copy()
    # Filtrar por tickers si se especifica archivo
    sector_name = "all"
    if args.tickers and os.path.exists(args.tickers):
        tickers_list = pd.read_csv(args.tickers)['ticker'].tolist()
        df = df[df['ticker'].isin(tickers_list)]
        sector_name = os.path.splitext(os.path.basename(args.tickers))[0].replace("tickers_","")
    # Filtros adicionales por probabilidad y magnitud de y_hat
    if args.min_prob and 'prob_win' in df.columns:
        df = df[df['prob_win'] >= float(args.min_prob)]
    if args.min_abs_yhat and 'y_hat' in df.columns:
        df = df[df['y_hat'].abs() >= float(args.min_abs_yhat)]
    # Helper para position sizing
    def _calc_shares(entry_price: float, per_trade_cash: float, allow_fractional: bool) -> float:
        if entry_price is None:
            return float('nan')
        try:
            ep = float(entry_price)
        except Exception:
            return float('nan')
        if not (ep > 0):
            return float('nan')
        if allow_fractional:
            return per_trade_cash / ep
        return math.floor(per_trade_cash / ep)

    # Construir trades detallados (para simulate_results.csv)
    trades = []
    gate_col = 'gate_pattern_ok' if 'gate_pattern_ok' in df.columns else 'gate_ok'

    # Helper to materialize a trade row
    def _make_trade_row(r, rr, reason):
        entry_dt = r.get('date')
        entry_price = r.get('entry_price', r.get('close', None))
        exit_price = None
        try:
            if entry_price is not None:
                exit_price = float(entry_price) * (1.0 + rr)
        except Exception:
            exit_price = None
        shares = _calc_shares(entry_price, args.per_trade_cash, args.allow_fractional)
        cash_used = None
        try:
            if shares == shares and entry_price is not None:
                cash_used = float(shares) * float(entry_price)
        except Exception:
            cash_used = None
        pnl_reconstructed = None
        try:
            if exit_price is not None and shares == shares and entry_price is not None:
                pnl_reconstructed = (float(exit_price) - float(entry_price)) * float(shares)
        except Exception:
            pnl_reconstructed = None
        return {
            'ticker': r.get('ticker'),
            'sector': r.get('sector', sector_name),
            'source_run': sector_name,
            'entry_date': entry_dt,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'horizon_days': args.horizon_days,
            'prob_win': r.get('prob_win'),
            'y_hat': float(r.get('y_hat', 0.0)),
            'tp_pct_suggested': args.tp_pct,
            'sl_pct_suggested': args.sl_pct,
            'shares': shares,
            'cash_used': cash_used,
            'pnl_reconstructed': pnl_reconstructed,
            'pnl': rr * args.per_trade_cash,
            'rr': rr,
            'reason': reason,
        }

    # Active mode: enforce capital and open positions
    use_active = args.position_active or (args.max_open and args.max_open > 0)
    realized_pnls = []
    capital = float(args.capital_initial)
    available_cash = capital
    open_positions = []  # list of dicts: {ticker, rr, yhat_open, exit_dt}
    last_exit_dt_by_ticker = {}
    last_exit_reason_by_ticker = {}

    if use_active and 'date' in df.columns:
        df = df.sort_values('date').copy()
        # group by day, sort within day
        if args.sort_signals_by == 'prob_win' and 'prob_win' in df.columns:
            df['_sortkey'] = -df['prob_win'].fillna(0)
        else:
            df['_sortkey'] = -df['y_hat'].abs().fillna(0)
        for day, g in df.groupby(df['date'].dt.floor('D')):
            # 1) Close positions whose exit_dt <= current day
            still_open = []
            for pos in open_positions:
                if pos['exit_dt'] <= day:
                    realized_pnls.append(pos['rr'] * args.per_trade_cash)
                    available_cash += args.per_trade_cash
                    last_exit_dt_by_ticker[pos['ticker']] = pos['exit_dt']
                else:
                    still_open.append(pos)
            open_positions = still_open

            # 2) Mini-rebalance: si no hay slots y hay señales gate-ok, libera K posiciones cada N días
            if args.rebalance_every_days and args.max_open and len(open_positions) >= args.max_open:
                try:
                    day0 = df['date'].min().floor('D') if 'date' in df.columns else day
                    delta_days = int((day - day0).days)
                except Exception:
                    delta_days = 0
                pending_signals = g[(g.get(gate_col, 0) == 1)] if gate_col in g.columns else g
                if (delta_days > 0 and args.rebalance_every_days > 0 and (delta_days % args.rebalance_every_days) == 0 and len(pending_signals) > 0):
                    # Cerrar las posiciones de menor calidad (por yhat_open ascendente)
                    k = min(args.rebalance_close_k, len(open_positions))
                    to_close = sorted(open_positions, key=lambda p: (p.get('yhat_open', 0.0)))[:k]
                    still = []
                    for pos in open_positions:
                        if pos in to_close:
                            realized_pnls.append(pos['rr'] * args.per_trade_cash)
                            available_cash += args.per_trade_cash
                            last_exit_dt_by_ticker[pos['ticker']] = day
                            last_exit_reason_by_ticker[pos['ticker']] = 'REBALANCE_EXIT'
                        else:
                            still.append(pos)
                    open_positions = still

            # 3) Allocate capital to today's signals
            g2 = g.sort_values('_sortkey')
            for _, r in g2.iterrows():
                if int(r.get(gate_col, 0)) != 1:
                    continue
                # cooldown and same-ticker lock
                tk = r.get('ticker')
                if args.lock_same_ticker and any(p['ticker']==tk for p in open_positions):
                    continue
                # Permitir re-entrada inmediata tras TP si condiciones se cumplen; si no, aplicar cooldown normal
                allow_reentry = False
                if args.allow_reentry_after_tp and tk in last_exit_reason_by_ticker and last_exit_reason_by_ticker[tk] == 'TP_HIT':
                    try:
                        yhat_val = float(r.get('y_hat', 0.0))
                    except Exception:
                        yhat_val = 0.0
                    atr_val = float(r.get('atr_pct', 0.0)) if 'atr_pct' in r else 0.0
                    if abs(yhat_val) >= args.reentry_yhat_min and atr_val >= args.reentry_atr_min:
                        allow_reentry = True
                if not allow_reentry and args.cooldown_days and tk in last_exit_dt_by_ticker:
                    if (day - last_exit_dt_by_ticker[tk]).days < args.cooldown_days:
                        continue
                # capacity checks
                if args.max_open and len(open_positions) >= args.max_open:
                    break
                if available_cash + 1e-9 < args.per_trade_cash:
                    break

                # Determine rr and reason
                ret = float(r.get('y_hat', 0.0))
                if ret >= args.tp_pct:
                    rr = args.tp_pct
                    reason = 'TP_HIT'
                elif ret <= -args.sl_pct:
                    rr = -args.sl_pct
                    reason = 'SL_HIT'
                else:
                    rr = ret
                    reason = 'HORIZON_END'

                # Open position
                trade_row = _make_trade_row(r, rr, reason)
                trades.append(trade_row)
                # Dynamic horizon based on ATR percentile
                H = args.horizon_days
                if args.horizon_dynamic_atr and 'atr_pct' in df.columns:
                    try:
                        # Compute monthly p75 once
                        if '_atr_p75' not in df.columns:
                            atr_p75 = df['atr_pct'].quantile(0.75)
                            df['_atr_p75'] = atr_p75
                        if float(r.get('atr_pct', 0.0)) >= float(df['_atr_p75'].iloc[0]):
                            H = args.horizon_days_high_atr
                    except Exception:
                        H = args.horizon_days
                exit_dt = day + pd.Timedelta(days=H)
                open_positions.append({'ticker': tk, 'exit_dt': exit_dt, 'rr': rr, 'yhat_open': float(r.get('y_hat', 0.0))})
                available_cash -= args.per_trade_cash

        # After last day, close any remaining positions
        for pos in open_positions:
            realized_pnls.append(pos['rr'] * args.per_trade_cash)
            available_cash += args.per_trade_cash
            last_exit_dt_by_ticker[pos['ticker']] = pos['exit_dt']
            last_exit_reason_by_ticker[pos['ticker']] = 'HORIZON_END'

        net = sum(realized_pnls)
        win_rate = (pd.Series(realized_pnls) > 0).mean() if realized_pnls else 0.0
        res = {
            'rows_total': int(len(df)),
            'rows_gated': int((df[gate_col]==1).sum()) if gate_col in df.columns else int(len(df)),
            'trades': int(len(trades)),
            'win_rate': win_rate,
            'net_pnl_sum': net,
            'capital_final': capital + net
        }
    else:
        # Legacy stateless path
        # Build trades list just like before
        for _, r in df.iterrows():
            if int(r.get(gate_col, 0)) != 1:
                continue
            ret = float(r.get('y_hat', 0.0))
            if ret >= args.tp_pct:
                rr = args.tp_pct
                reason = 'TP_HIT'
            elif ret <= -args.sl_pct:
                rr = -args.sl_pct
                reason = 'SL_HIT'
            else:
                rr = ret
                reason = 'HORIZON_END'
            trades.append(_make_trade_row(r, rr, reason))
        res = simulate(df,args.tp_pct,args.sl_pct,args.capital_initial,args.per_trade_cash)

    out=os.path.join(args.forecast_dir,args.month,f"kpi_{sector_name}.json")
    res_row = {**res, 'source_file': source, 'sector': sector_name, 'timestamp': datetime.now(timezone.utc).isoformat()}
    import json
    with open(out,"w") as fjson:
        json.dump(res_row, fjson, indent=2)
    print(f"[simulate] {args.month} ({source}) -> {out}")

    # Guardar trades detallados
    # Guardar siempre simulate_results.csv para evitar archivos obsoletos
    expected_cols = [
        'ticker','sector','entry_date','entry_price','exit_price','horizon_days','prob_win','y_hat',
        'tp_pct_suggested','sl_pct_suggested','shares','cash_used','pnl_reconstructed','pnl','rr','reason'
    ]
    trades_df = pd.DataFrame(trades, columns=expected_cols + ['source_run'])
    trades_df.to_csv(os.path.join(args.forecast_dir, args.month, args.simulate_results_out), index=False)

if __name__=="__main__":
    main()