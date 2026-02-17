#!/usr/bin/env python3
"""
Live trading dashboard Flask server with auto-refresh prices from yfinance.
Runs on http://localhost:7777/
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, Response

TRADE_PLAN_PATH = Path("val/trade_plan_EXECUTE.csv")
OUTPUT_HTML = Path("val/trade_monitor_dashboard.html")
EXPOSURE_CAP = 800.0

app = Flask(__name__)


def fetch_prices(tickers: List[str]) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            price = None
            # Try fast_info
            fi = getattr(tk, "fast_info", None)
            if fi is not None:
                price = fi.last_price if getattr(fi, "last_price", None) not in (None, 0) else None
            # Fallback to 1m history
            if price is None:
                hist = tk.history(period="1d", interval="1m")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            # Fallback to daily close
            if price is None:
                dl = yf.download(t, period="1d", progress=False)
                if not dl.empty:
                    price = float(dl["Close"].iloc[-1])
            if price is not None:
                prices[t] = float(price)
        except Exception:
            continue
    return prices


def compute(df: pd.DataFrame, prices: Dict[str, float]):
    rows = []
    for _, r in df.iterrows():
        t = r["ticker"]
        if t not in prices:
            continue
        entry = float(r["entry"])
        current = float(prices[t])
        tp = float(r["tp_price"])
        sl = float(r["sl_price"])
        qty = float(r.get("qty", 0) or 0)
        pnl_unit = current - entry
        pnl = pnl_unit * qty
        pnl_pct = (pnl_unit / entry) * 100 if entry else 0.0
        total_range = tp - sl if tp != sl else 0.0
        progress_pct = ((current - sl) / total_range * 100) if total_range > 0 else 0.0
        progress_pct = max(0.0, min(100.0, progress_pct))
        dist_tp = tp - current
        dist_sl = current - sl
        rows.append({
            "ticker": t,
            "entry": entry,
            "current": current,
            "tp": tp,
            "sl": sl,
            "qty": qty,
            "exposure": float(r.get("exposure", entry * qty)),
            "prob_win": float(r.get("prob_win", 0)),
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "progress_pct": progress_pct,
            "dist_tp": dist_tp,
            "dist_sl": dist_sl,
            "status": "GANANCIA" if pnl >= 0 else "PÉRDIDA",
        })
    return rows


def aggregate(rows: List[Dict]):
    total_pnl = sum(r["pnl"] for r in rows)
    exposure_total = sum(r["exposure"] for r in rows)
    active = len([r for r in rows if r.get("qty", 0) > 0])
    avg_prob = sum(r["prob_win"] for r in rows) / len(rows) if rows else 0.0
    return {
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / exposure_total * 100) if exposure_total else 0.0,
        "exposure_total": exposure_total,
        "active": active,
        "avg_prob": avg_prob * 100,
    }


def render_html(rows: List[Dict], summary: Dict, timestamp: str) -> str:

    kpi_html = f"""
    <div class="summary">
        <div class="summary-card {'positive' if summary['total_pnl']>=0 else 'negative'}">
            <h3>P&L TOTAL</h3>
            <div class="value">{fmt_money(summary['total_pnl'])}</div>
            <p class="subtext">({fmt_pct(summary['total_pnl_pct'])})</p>
        </div>
        <div class="summary-card">
            <h3>EXPOSICIÓN</h3>
            <div class="value">{fmt_money(summary['exposure_total'])}</div>
            <p class="subtext">de {fmt_money(EXPOSURE_CAP)} cap</p>
        </div>
        <div class="summary-card">
            <h3>TRADES ACTIVOS</h3>
            <div class="value">{summary['active']}</div>
            <p class="subtext">de {summary['active']} en plan</p>
        </div>
        <div class="summary-card">
            <h3>PROB. WIN PROMEDIO</h3>
            <div class="value">{summary['avg_prob']:.1f}%</div>
            <p class="subtext">del modelo</p>
        </div>
    </div>
    """

    cards_html_parts = []
    for r in rows:
        pnl_class = "positive" if r["pnl"] >= 0 else "negative"
        badge_class = "badge-pos" if r["pnl"] >= 0 else "badge-neg"
        cards_html_parts.append(f"""
        <div class="trade-card">
            <div class="trade-header">
                <div class="ticker">{r['ticker']}</div>
                <div class="status-badge {badge_class}">{r['status']}</div>
            </div>
            <div class="trade-body">
                <div class="pnl-banner {pnl_class}">{fmt_money(r['pnl'])} ({fmt_pct(r['pnl_pct'])})</div>
                <div class="price-row"><span class="price-label">Entry</span><span class="price-value entry-price">{fmt_money(r['entry'])}</span></div>
                <div class="price-row"><span class="price-label">Current Price</span><span class="price-value current-price">{fmt_money(r['current'])}</span></div>
                <div class="price-row"><span class="price-label">Target (TP)</span><span class="price-value tp-price">{fmt_money(r['tp'])}</span></div>
                <div class="price-row"><span class="price-label">Stop (SL)</span><span class="price-value sl-price">{fmt_money(r['sl'])}</span></div>
                <div class="progress-container">
                    <div class="progress-label"><span>Progreso SL → TP</span><span>{r['progress_pct']:.1f}%</span></div>
                    <div class="progress-bar"><div class="progress-fill" style="width:{r['progress_pct']:.1f}%"></div></div>
                </div>
                <div class="mini-grid">
                    <div class="mini"><div class="mini-label">Dist a TP</div><div class="mini-value">{fmt_money(r['dist_tp'])}</div></div>
                    <div class="mini"><div class="mini-label">Dist a SL</div><div class="mini-value">{fmt_money(r['dist_sl'])}</div></div>
                    <div class="mini"><div class="mini-label">Qty</div><div class="mini-value">{r['qty']:.0f}</div></div>
                </div>
            </div>
        </div>
        """)

    trades_html = "\n".join(cards_html_parts)

    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Monitor Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 30px; text-align: center; }}
        .header h1 {{ color: #1e3c72; margin-bottom: 8px; }}
        .timestamp {{ color: #666; font-size: 14px; }}
        .sub {{ font-size: 12px; color: #999; margin-top: 5px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }}
        .summary-card h3 {{ color: #666; font-size: 14px; margin-bottom: 10px; text-transform: uppercase; }}
        .summary-card .value {{ font-size: 32px; font-weight: bold; color: #1e3c72; }}
        .summary-card.positive .value {{ color: #27ae60; }}
        .summary-card.negative .value {{ color: #e74c3c; }}
        .subtext {{ font-size: 13px; color: #999; margin-top: 5px; }}
        .trades-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
        .trade-card {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.2s, box-shadow 0.2s; display: flex; flex-direction: column; }}
        .trade-card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 12px rgba(0,0,0,0.15); }}
        .trade-header {{ padding: 16px 20px; background: #f8f9fa; border-bottom: 2px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; }}
        .ticker {{ font-size: 22px; font-weight: bold; color: #1e3c72; }}
        .status-badge {{ padding: 6px 12px; border-radius: 18px; font-size: 12px; font-weight: 700; }}
        .badge-pos {{ background: #eafaf1; color: #1f7a3e; }}
        .badge-neg {{ background: #fdecea; color: #a12622; }}
        .trade-body {{ padding: 20px; display: flex; flex-direction: column; gap: 10px; }}
        .pnl-banner {{ padding: 12px; border-radius: 8px; font-size: 16px; font-weight: 700; text-align: center; }}
        .pnl-banner.positive {{ background: #eafaf1; color: #1f7a3e; }}
        .pnl-banner.negative {{ background: #fdecea; color: #a12622; }}
        .price-row {{ display: flex; justify-content: space-between; margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px solid #eee; }}
        .price-row:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
        .price-label {{ color: #666; font-size: 13px; font-weight: 600; }}
        .price-value {{ font-weight: bold; color: #333; }}
        .entry-price {{ color: #3498db; }}
        .current-price {{ color: #1e3c72; font-size: 16px; }}
        .tp-price {{ color: #27ae60; }}
        .sl-price {{ color: #e74c3c; }}
        .progress-container {{ margin-top: 4px; }}
        .progress-label {{ font-size: 12px; color: #666; margin-bottom: 4px; display: flex; justify-content: space-between; }}
        .progress-bar {{ width: 100%; height: 14px; background: #e9eef5; border-radius: 10px; overflow: hidden; position: relative; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #66b3ff 0%, #27ae60 100%); transition: width 0.3s ease; }}
        .mini-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 6px; }}
        .mini {{ background: #eef3f9; padding: 10px; border-radius: 8px; text-align: center; }}
        .mini .mini-label {{ color: #99a3ad; font-size: 11px; margin-bottom: 3px; }}
        .mini .mini-value {{ font-weight: 700; color: #333; }}
        .refresh-btn {{ position: fixed; bottom: 24px; right: 24px; background: #3498db; color: white; border: none; padding: 14px 20px; border-radius: 40px; font-size: 14px; font-weight: 700; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.2); display: flex; align-items: center; gap: 8px; transition: all 0.2s; }}
        .refresh-btn:hover {{ background: #2980b9; transform: translateY(-1px); }}
        .refresh-btn:active {{ transform: translateY(0); }}
        .refresh-btn.loading {{ background: #95a5a6; cursor: wait; }}
        .spinner {{ display: none; width: 14px; height: 14px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; }}
        .refresh-btn.loading .spinner {{ display: inline-block; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        @media (max-width: 768px) {{ .summary {{ grid-template-columns: 1fr; }} .trades-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trade Monitor Dashboard</h1>
            <p class="timestamp">Actualizado: {timestamp}</p>
            <p class="sub">Precios en vivo desde Yahoo Finance (yfinance)</p>
        </div>
        {kpi_html}
        <div class="trades-grid">
            {trades_html}
        </div>
    </div>
    <button class="refresh-btn" onclick="refreshNow()">
        <span class="spinner"></span>
        <span class="btn-text">Actualizar Precios</span>
    </button>
    <script>
        function refreshNow() {{
            const btn = document.querySelector('.refresh-btn');
            const txt = document.querySelector('.btn-text');
            if(btn) btn.classList.add('loading');
            if(txt) txt.textContent = 'Actualizando...';
            setTimeout(()=>{{ location.reload(); }}, 300);
        }}
        setTimeout(()=>{{ location.reload(); }}, 60000);
    </script>
</body>
</html>
"""


def main():
    if not TRADE_PLAN_PATH.exists():
        raise SystemExit(f"No existe {TRADE_PLAN_PATH}")
    df = pd.read_csv(TRADE_PLAN_PATH)
    df = df[df.get("qty", 0) > 0].copy()
    prices = fetch_prices(df["ticker"].tolist())
    rows = compute(df, prices)
    summary = aggregate(rows)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_html(rows, summary, timestamp)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Dashboard generado: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
