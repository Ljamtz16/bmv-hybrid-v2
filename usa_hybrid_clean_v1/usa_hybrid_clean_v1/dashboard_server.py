#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, Response

TRADE_PLAN_PATH = Path("val/trade_plan_EXECUTE.csv")
AUDIT_PATH = Path("val/trade_plan_run_audit.json")

app = Flask(__name__)


def load_trades():
    if not TRADE_PLAN_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRADE_PLAN_PATH)
    df = df[df.get("qty", 0) > 0].copy()
    return df


def load_cap_from_audit():
    try:
        if AUDIT_PATH.exists():
            data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
            cap = data.get("exposure_cap", {}).get("cap")
            if cap:
                return float(cap)
    except Exception:
        pass
    return None


def get_live_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            p = None
            try:
                fi = getattr(tk, "fast_info", None)
                if fi is not None:
                    p = float(fi.last_price)
            except Exception:
                p = None
            if p is None or p == 0:
                hist = tk.history(period="1d", interval="1m")
                if not hist.empty:
                    p = float(hist["Close"].iloc[-1])
            if p is None or p == 0:
                dl = yf.download(t, period="1d", progress=False)
                if not dl.empty:
                    p = float(dl["Close"].iloc[-1])
            if p is not None and p > 0:
                prices[t] = p
        except Exception:
            continue
    return prices


def calc_metrics(trade_row, current_price):
    entry = float(trade_row["entry"]) if pd.notna(trade_row["entry"]) else current_price
    tp = float(trade_row["tp_price"]) if pd.notna(trade_row["tp_price"]) else current_price
    sl = float(trade_row["sl_price"]) if pd.notna(trade_row["sl_price"]) else current_price
    pnl = current_price - entry
    pnl_pct = (pnl / entry) * 100 if entry else 0.0
    total_range = tp - sl
    current_distance = current_price - sl
    progress_pct = (current_distance / total_range) * 100 if total_range > 0 else 0.0
    progress_pct = max(0.0, min(100.0, progress_pct))
    status = "⏸️ SIN CAMBIO"
    color = "#e2e3e5"
    if current_price >= tp:
        status = "✅ TARGET HIT"
        color = "#27ae60"
    elif current_price <= sl:
        status = "❌ STOP HIT"
        color = "#e74c3c"
    elif pnl > 0:
        status = "📈 GANANCIA"
        color = "#d4edda"
    elif pnl < 0:
        status = "📉 PÉRDIDA"
        color = "#f8d7da"
    return {
        "current_price": current_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "progress_pct": progress_pct,
        "status": status,
        "color": color,
        "distance_to_tp": tp - current_price,
        "distance_to_sl": current_price - sl,
    }


@app.get("/api/metrics")
def api_metrics():
    df = load_trades()
    tickers = df["ticker"].tolist() if not df.empty else []
    prices = get_live_prices(tickers)
    metrics = {}
    for t, row in df.set_index("ticker").iterrows():
        if t in prices:
            metrics[t] = calc_metrics(row, prices[t])
    total_pnl = sum(m["pnl"] for m in metrics.values())
    exposure_total = float(df["exposure"].sum()) if not df.empty else 0.0
    cap = load_cap_from_audit()
    resp = {
        "timestamp": datetime.now().isoformat(),
        "tickers": tickers,
        "prices": prices,
        "metrics": metrics,
        "summary": {
            "total_pnl": total_pnl,
            "total_pnl_pct": (total_pnl / (df["entry"].sum() or 1)) * 100 if not df.empty else 0.0,
            "exposure_total": exposure_total,
            "count": len(tickers),
            "prob_win_avg": float(df["prob_win"].mean()) * 100 if not df.empty else 0.0,
            "cap": cap,
        },
    }
    return jsonify(resp)


@app.get("/")
def index():
    html = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Monitor Dashboard (Live)</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1f3c73;
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; overflow-x: auto; }
        .header {
            background: white; padding: 30px; border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 30px; text-align: center;
        }
        .header h1 { color: #1e3c72; margin-bottom: 8px; }
        .timestamp { color: #666; font-size: 14px; }
        .sub { font-size: 12px; color: #999; margin-top: 5px; }
        .summary {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px; margin-bottom: 30px;
        }
        .summary-card {
            background: white; padding: 20px; border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;
        }
        .summary-card h3 { color: #666; font-size: 14px; margin-bottom: 10px; text-transform: uppercase; }
        .summary-card .value { font-size: 32px; font-weight: bold; color: #1e3c72; }
        .summary-card.positive .value { color: #27ae60; }
        .summary-card.negative .value { color: #e74c3c; }
        .trades-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; min-width: 1280px; }
        .trade-card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.2s, box-shadow 0.2s; display: flex; flex-direction: column; height: 100%; }
        .trade-card:hover { transform: translateY(-5px); box-shadow: 0 8px 12px rgba(0,0,0,0.15); }
        .trade-header { padding: 20px; background: #f8f9fa; border-bottom: 2px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; }
        .ticker { font-size: 24px; font-weight: bold; color: #1e3c72; }
        .status-badge { padding: 6px 12px; border-radius: 18px; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; gap: 6px; }
        .trade-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
        .pnl-banner { padding: 12px; border-radius: 8px; font-size: 16px; font-weight: 700; text-align: center; margin-bottom: 14px; }
        .pnl-banner.positive { background: #eafaf1; color: #1f7a3e; }
        .pnl-banner.negative { background: #fdecea; color: #a12622; }
        .price-row { display: flex; justify-content: space-between; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .price-row:last-child { border-bottom: none; margin-bottom: 10px; padding-bottom: 0; }
        .price-label { color: #666; font-size: 13px; font-weight: 600; }
        .price-value { font-weight: bold; color: #333; }
        .entry-price { color: #3498db; }
        .current-price { color: #1e3c72; font-size: 18px; }
        .tp-price { color: #27ae60; }
        .sl-price { color: #e74c3c; }
        .pnl { font-size: 18px; font-weight: bold; text-align: center; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
        .pnl.positive { background: #d4edda; color: #155724; }
        .pnl.negative { background: #f8d7da; color: #721c24; }
        .pnl.neutral { background: #e2e3e5; color: #383d41; }
        .progress-container { margin-top: 10px; }
        .progress-label { font-size: 12px; color: #666; margin-bottom: 5px; display: flex; justify-content: space-between; }
        .progress-bar { width: 100%; height: 16px; background: #e9eef5; border-radius: 10px; overflow: hidden; position: relative; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #66b3ff 0%, #27ae60 100%); transition: width 0.3s ease; }
        .mini-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
        .mini { background: #eef3f9; padding: 12px; border-radius: 10px; text-align: center; }
        .mini .mini-label { color: #99a3ad; font-size: 11px; margin-bottom: 4px; }
        .mini .mini-value { font-weight: 700; color: #333; }
        .stat-label { color: #999; font-size: 11px; margin-bottom: 3px; }
        .stat-value { font-weight: bold; color: #333; }
        .refresh-btn { position: fixed; bottom: 30px; right: 30px; background: #3498db; color: white; border: none; padding: 15px 25px; border-radius: 50px; font-size: 16px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.2); transition: all 0.3s; z-index: 100; display: flex; align-items: center; gap: 8px; }
        .refresh-btn:hover { background: #2980b9; transform: scale(1.05); }
        .refresh-btn:active { transform: scale(0.95); }
        .refresh-btn.loading { background: #95a5a6; cursor: wait; }
        .refresh-btn .spinner { display: none; width: 16px; height: 16px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; }
        .refresh-btn.loading .spinner { display: block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (max-width: 768px) { .summary { grid-template-columns: 1fr; } /* keep 4 columns with horizontal scroll */ }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Trade Monitor Dashboard</h1>
            <p class="timestamp" id="lastUpdated">Actualizado: —</p>
            <p class="sub">Precios en vivo desde Yahoo Finance (yfinance) • Auto-actualiza cada 30s</p>
        </div>

        <div id="summary" class="summary"></div>
        <div id="grid" class="trades-grid"></div>
    </div>

    <button class="refresh-btn" onclick="refreshNow()">
        <span class="spinner"></span>
        <span class="btn-text">🔄 Actualizar Precios</span>
    </button>

    <script>
        function fmt(v){ return (Math.round(v*100)/100).toFixed(2); }
        function fmtTime(iso){ try { const d = new Date(iso); return d.toLocaleString(); } catch(e){ return iso; } }

        async function fetchData(){
            const res = await fetch('/api/metrics?nocache='+Date.now());
            return await res.json();
        }

        function renderSummary(s){
            const pnlCardClass = s.total_pnl >= 0 ? 'summary-card positive' : 'summary-card negative';
            document.getElementById('summary').innerHTML = `
                <div class="${pnlCardClass}">
                    <h3>P&L Total</h3>
                    <div class="value">$${fmt(s.total_pnl)}</div>
                    <p style="font-size:13px;color:#999;margin-top:5px;">(${fmt(s.total_pnl_pct)}%)</p>
                </div>
                <div class="summary-card">
                    <h3>Exposición</h3>
                    <div class="value">$${fmt(s.exposure_total)}</div>
                    <p style="font-size:13px;color:#999;margin-top:5px;">${s.cap ? 'de $'+fmt(s.cap)+' cap' : ''}</p>
                </div>
                <div class="summary-card">
                    <h3>Trades Activos</h3>
                    <div class="value">${s.count}</div>
                    <p style="font-size:13px;color:#999;margin-top:5px;">de ${s.count} en plan</p>
                </div>
                <div class="summary-card">
                    <h3>Prob. Win Promedio</h3>
                    <div class="value">${fmt(s.prob_win_avg)}%</div>
                    <p style="font-size:13px;color:#999;margin-top:5px;">del modelo</p>
                </div>`;
        }

        function renderGrid(data){
            const g = document.getElementById('grid');
            g.innerHTML = '';
            data.tickers.forEach(t => {
                const m = data.metrics[t];
                if(!m) return;
                const current = m.current_price;
                const entry = current - m.pnl;
                const tp = m.distance_to_tp + current;
                const sl = current - m.distance_to_sl;
                const pnlClass = m.pnl > 0 ? 'positive' : (m.pnl < 0 ? 'negative' : 'neutral');
                const statusColor = m.pnl > 0 ? '#eafaf1' : (m.pnl < 0 ? '#fdecea' : '#e2e3e5');
                const statusTextColor = m.pnl > 0 ? '#1f7a3e' : (m.pnl < 0 ? '#a12622' : '#333');
                const card = document.createElement('div');
                card.className = 'trade-card';
                card.innerHTML = `
                    <div class="trade-header">
                        <div class="ticker">${t}</div>
                        <div class="status-badge" style="background:${statusColor};color:${statusTextColor};">✅ ${m.status.replace('GANANCIA','GANANCIA').replace('PÉRDIDA','PÉRDIDA')}</div>
                    </div>
                    <div class="trade-body">
                        <div class="pnl-banner ${pnlClass}">$${fmt(m.pnl)} (${fmt(m.pnl_pct)}%)</div>
                        <div class="price-row"><span class="price-label">Entry</span><span class="price-value entry-price">$${fmt(entry)}</span></div>
                        <div class="price-row"><span class="price-label">Current Price</span><span class="price-value current-price">$${fmt(current)}</span></div>
                        <div class="price-row"><span class="price-label">Target (TP)</span><span class="price-value tp-price">$${fmt(tp)}</span></div>
                        <div class="price-row"><span class="price-label">Stop (SL)</span><span class="price-value sl-price">$${fmt(sl)}</span></div>
                        <div class="progress-container">
                            <div class="progress-label"><span>Progreso SL → TP</span><span>${fmt(m.progress_pct)}%</span></div>
                            <div class="progress-bar"><div class="progress-fill" style="width:${fmt(m.progress_pct)}%"></div></div>
                        </div>
                        <div class="mini-grid">
                            <div class="mini"><div class="mini-label">Dist a TP</div><div class="mini-value">$${fmt(m.distance_to_tp)}</div></div>
                            <div class="mini"><div class="mini-label">Dist a SL</div><div class="mini-value">$${fmt(m.distance_to_sl)}</div></div>
                            <div class="mini"><div class="mini-label">ETTH (días)</div><div class="mini-value">${fmt(data.metrics[t].progress_pct/10)}</div></div>
                        </div>
                    </div>`;
                g.appendChild(card);
            });
        }

        async function load(){
            const btn = document.querySelector('.refresh-btn');
            const btnText = document.querySelector('.btn-text');
            try{
                const data = await fetchData();
                document.getElementById('lastUpdated').textContent = 'Actualizado: ' + fmtTime(data.timestamp);
                renderSummary(data.summary);
                renderGrid(data);
            }catch(e){ console.error(e); }
            finally{
                if(btn){ btn.classList.remove('loading'); btn.disabled = false; }
                if(btnText){ btnText.textContent = '🔄 Actualizar Precios'; }
            }
        }

        function refreshNow(){
            const btn = document.querySelector('.refresh-btn');
            const btnText = document.querySelector('.btn-text');
            if(btn){ btn.classList.add('loading'); btn.disabled = true; }
            if(btnText){ btnText.textContent = 'Actualizando...'; }
            load();
        }

        load();
        setInterval(load, 30000);
    </script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
