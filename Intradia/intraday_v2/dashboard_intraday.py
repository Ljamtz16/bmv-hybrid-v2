#!/usr/bin/env python3
"""
Intraday Trade Dashboard (Read-Only)
- Monitorea precios y movimientos en tiempo real
- Lee CSVs de artifacts/ (plan + trades)
- Snapshot cacheado para performance
"""

import json
import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template_string

try:
    import yfinance as yf
except Exception:
    yf = None

try:
    import pandas_market_calendars as mcal
except Exception:
    mcal = None

try:
    import pytz
except Exception:
    pytz = None


# =============================================================================
# CONFIG
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

PLAN_PATH = ARTIFACTS_DIR / "intraday_plan_clean.csv"
PLAN_RAW_PATH = ARTIFACTS_DIR / "intraday_plan.csv"
TRADES_PATH = ARTIFACTS_DIR / "intraday_trades.csv"
EQUITY_PATH = ARTIFACTS_DIR / "intraday_equity_curve.csv"
METRICS_PATH = ARTIFACTS_DIR / "intraday_metrics.json"
WEEKLY_PATH = ARTIFACTS_DIR / "intraday_weekly.csv"

PRICE_CACHE = {}
CACHE_TTL = 60

SNAPSHOT_CACHE = None
SNAPSHOT_LAST_BUILD = 0.0
SNAPSHOT_CACHE_TTL = 10
SNAPSHOT_STALE_TTL = 120
SNAPSHOT_REVALIDATING = False

CSV_LOCK = threading.RLock()

app = Flask(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _read_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        raw = raw.replace("Infinity", "null").replace("-Infinity", "null")
        return json.loads(raw)
    except Exception:
        return None


def _plan_summary(plan_df: pd.DataFrame, name: str):
    if plan_df is None or plan_df.empty:
        return {
            "name": name,
            "trades": 0,
            "exposure": 0.0,
            "prob_win_avg": 0.0,
        }
    entry_col = "entry_price" if "entry_price" in plan_df.columns else "entry"
    prob_col = "prob_win" if "prob_win" in plan_df.columns else None
    exposure = _safe_float(plan_df[entry_col].sum(), 0.0)
    prob_win_avg = 0.0
    if prob_col and prob_col in plan_df.columns and len(plan_df) > 0:
        prob_win_avg = _safe_float(plan_df[prob_col].mean(), 0.0)
    return {
        "name": name,
        "trades": int(len(plan_df)),
        "exposure": exposure,
        "prob_win_avg": prob_win_avg,
    }


def _get_market_status():
    if pytz and mcal:
        try:
            ny_tz = pytz.timezone("US/Eastern")
            now_ny = datetime.now(ny_tz)
            today = now_ny.date()
            current_time = now_ny.time()
            nyse = mcal.get_calendar("NYSE")
            schedule = nyse.schedule(start_date=today, end_date=today)
            if schedule.empty:
                return "CERRADO", now_ny.strftime("%Y-%m-%d %H:%M:%S")
            market_open = schedule.iloc[0]["market_open"].tz_convert(ny_tz).time()
            market_close = schedule.iloc[0]["market_close"].tz_convert(ny_tz).time()
            if market_open <= current_time < market_close:
                return "ABIERTO", now_ny.strftime("%Y-%m-%d %H:%M:%S")
            return "CERRADO", now_ny.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    # Fallback simple
    now = datetime.now()
    status = "ABIERTO" if 14 <= now.hour < 21 else "CERRADO"
    return status, now.strftime("%Y-%m-%d %H:%M:%S")


def _fetch_prices_batch(tickers):
    if not yf or not tickers:
        return {}
    try:
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            progress=False,
            group_by="ticker",
            auto_adjust=False,
            threads=True,
        )
        result = {}
        if isinstance(data.columns, pd.MultiIndex):
            for t in tickers:
                if t in data.columns.get_level_values(0):
                    series = data[t]["Close"].dropna()
                    if not series.empty:
                        result[t] = float(series.iloc[-1])
        else:
            series = data["Close"].dropna()
            if not series.empty and len(tickers) == 1:
                result[tickers[0]] = float(series.iloc[-1])
        return result
    except Exception:
        return {}


def get_cached_prices(tickers):
    now = datetime.now()
    result = {}
    to_fetch = []

    for t in tickers:
        cached = PRICE_CACHE.get(t)
        if cached and (now - cached["ts"]).seconds < CACHE_TTL:
            result[t] = cached["price"]
        else:
            to_fetch.append(t)

    if to_fetch:
        fresh = _fetch_prices_batch(to_fetch)
        for t in to_fetch:
            if t in fresh:
                PRICE_CACHE[t] = {"price": fresh[t], "ts": now}
                result[t] = fresh[t]
            else:
                result[t] = None

    return result


def _build_active_trades(plan_df: pd.DataFrame, trades_df: pd.DataFrame):
    if plan_df.empty:
        return []

    closed = set()
    if not trades_df.empty:
        closed = set(
            trades_df[trades_df["exit_reason"].isin(["TP", "SL", "TIMEOUT", "NO_DATA", "DAILY_STOP_SL", "DAILY_STOP_R"])]
            .get("ticker", [])
            .astype(str)
            .str.upper()
            .tolist()
        )

    plan_df = plan_df.copy()
    plan_df["ticker"] = plan_df["ticker"].astype(str).str.upper()

    plan_df = plan_df[~plan_df["ticker"].isin(closed)]

    tickers = plan_df["ticker"].unique().tolist()
    prices = get_cached_prices(tickers)

    trades = []
    for _, row in plan_df.iterrows():
        ticker = row.get("ticker")
        side = str(row.get("side", "BUY")).upper()
        entry = _safe_float(row.get("entry_price", 0))
        tp = _safe_float(row.get("tp_price", 0))
        sl = _safe_float(row.get("sl_price", 0))
        prob_win = _safe_float(row.get("prob_win", 0))
        current = prices.get(ticker)
        if current is None:
            current = entry

        pnl = (current - entry) if side == "BUY" else (entry - current)
        pnl_pct = (pnl / entry * 100) if entry else 0

        trades.append({
            "ticker": ticker,
            "side": side,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "current": current,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "prob_win": prob_win,
        })

    return trades


def _build_history(trades_df: pd.DataFrame):
    if trades_df.empty:
        return []

    trades_df = trades_df.copy()
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"], errors="coerce")

    rows = []
    for _, row in trades_df.iterrows():
        rows.append({
            "ticker": str(row.get("ticker", "")),
            "side": str(row.get("side", "")),
            "entry": _safe_float(row.get("entry_price", 0)),
            "exit": _safe_float(row.get("exit_price", 0)),
            "exit_reason": str(row.get("exit_reason", "")),
            "pnl": _safe_float(row.get("pnl", 0)),
            "pnl_pct": _safe_float(row.get("pnl_pct", 0)),
            "entry_time": row.get("entry_time").isoformat() if pd.notna(row.get("entry_time")) else None,
        })

    return rows[::-1]


def _build_summary(active_trades, history_trades):
    pnl_total = sum([t["pnl"] for t in history_trades]) if history_trades else 0
    win_rate = 0
    if history_trades:
        wins = len([t for t in history_trades if t["pnl"] > 0])
        win_rate = (wins / len(history_trades)) * 100

    exposure = sum([t["entry"] for t in active_trades]) if active_trades else 0
    prob_win_avg = 0
    if active_trades:
        prob_win_avg = sum([t["prob_win"] for t in active_trades]) / len(active_trades)

    return {
        "pnl_total": pnl_total,
        "win_rate": win_rate,
        "exposure": exposure,
        "active_trades": len(active_trades),
        "history_trades": len(history_trades),
        "prob_win_avg": prob_win_avg,
    }


def build_trade_snapshot():
    with CSV_LOCK:
        plan_df = _read_csv(PLAN_PATH)
        trades_df = _read_csv(TRADES_PATH)

    active = _build_active_trades(plan_df, trades_df)
    history = _build_history(trades_df)
    summary = _build_summary(active, history)
    return {"active": active, "history": history, "summary": summary}


def _rebuild_snapshot_async():
    global SNAPSHOT_CACHE, SNAPSHOT_LAST_BUILD, SNAPSHOT_REVALIDATING
    try:
        SNAPSHOT_CACHE = build_trade_snapshot()
        SNAPSHOT_LAST_BUILD = time.time()
    finally:
        SNAPSHOT_REVALIDATING = False


def get_cached_snapshot():
    global SNAPSHOT_CACHE, SNAPSHOT_LAST_BUILD, SNAPSHOT_REVALIDATING
    now = time.time()

    if SNAPSHOT_CACHE is not None:
        age = now - SNAPSHOT_LAST_BUILD
        if age < SNAPSHOT_CACHE_TTL:
            return SNAPSHOT_CACHE
        if age < SNAPSHOT_STALE_TTL and not SNAPSHOT_REVALIDATING:
            SNAPSHOT_REVALIDATING = True
            threading.Thread(target=_rebuild_snapshot_async, daemon=True).start()
            return SNAPSHOT_CACHE

    SNAPSHOT_CACHE = build_trade_snapshot()
    SNAPSHOT_LAST_BUILD = now
    return SNAPSHOT_CACHE


def _build_chart(ticker: str):
    if not yf:
        return []
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="15m")
        if hist.empty:
            return []
        points = []
        for idx, row in hist.iterrows():
            points.append({"t": idx.isoformat(), "close": float(row["Close"])})
        return points
    except Exception:
        return []


def _load_weekly_report():
    df = _read_csv(WEEKLY_PATH)
    if df.empty:
        return []
    cols = [c for c in ["week", "trades", "pnl_total", "wr", "avg_pnl"] if c in df.columns]
    return df[cols].to_dict(orient="records")


# =============================================================================
# WEB
# =============================================================================

HTML = """<!DOCTYPE html>
<html lang=\"es\">
<head>
<meta charset=\"UTF-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Intraday Dashboard</title>
<style>
:root {
  --bg: #0f172a;
  --card: #ffffff;
  --text: #0f172a;
  --muted: #6b7280;
  --green: #16a34a;
  --red: #dc2626;
  --blue: #2563eb;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: linear-gradient(135deg, #0f172a, #1e293b); padding: 20px; color: #fff; }
.container { max-width: 1200px; margin: 0 auto; }
.header { background: var(--card); color: var(--text); padding: 20px; border-radius: 16px; box-shadow: 0 8px 20px rgba(0,0,0,0.2); margin-bottom: 20px; }
.header h1 { margin: 0 0 6px; }
.header p { margin: 0; color: var(--muted); font-size: 12px; }
.stats { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 20px; }
.card { background: var(--card); color: var(--text); padding: 16px; border-radius: 12px; box-shadow: 0 6px 16px rgba(0,0,0,0.12); }
.card h3 { margin: 0 0 6px; font-size: 12px; color: var(--muted); text-transform: uppercase; }
.card .value { font-size: 26px; font-weight: 700; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.trade { background: var(--card); color: var(--text); padding: 16px; border-radius: 12px; border-left: 4px solid var(--blue); box-shadow: 0 6px 16px rgba(0,0,0,0.12); }
.trade.profit { border-left-color: var(--green); }
.trade.loss { border-left-color: var(--red); }
.trade h4 { margin: 0 0 8px; display: flex; justify-content: space-between; }
.badge { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; color: #fff; }
.badge.buy { background: #16a34a; }
.badge.sell { background: #dc2626; }
.row { display: flex; justify-content: space-between; font-size: 13px; margin: 6px 0; }
.btn { border: none; background: var(--blue); color: #fff; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: 700; }
.tabs { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.tab { background: #e2e8f0; color: #0f172a; border: none; padding: 8px 12px; border-radius: 10px; cursor: pointer; font-weight: 700; }
.tab.active { background: var(--blue); color: #fff; }
.table { width: 100%; border-collapse: collapse; font-size: 12px; }
.table th, .table td { padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; align-items: center; justify-content: center; }
.modal.active { display: flex; }
.modal-content { background: #fff; color: #0f172a; padding: 16px; border-radius: 12px; width: min(900px, 90vw); }
#chartCanvas { width: 100%; height: 360px; }
</style>
</head>
<body>
<div class=\"container\">
  <div class=\"header\">
    <h1>Intraday Dashboard</h1>
    <p>Actualizado: <span id=\"updateTime\"></span> • Mercado: <span id=\"marketStatus\"></span></p>
  </div>

  <div class=\"stats\" id=\"stats\"></div>

  <div class=\"tabs\">
        <button class=\"tab active\" onclick=\"switchTab('active')\">Activos</button>
        <button class=\"tab\" onclick=\"switchTab('plans')\">Planes</button>
        <button class=\"tab\" onclick=\"switchTab('report')\">Reporte</button>
        <button class=\"tab\" onclick=\"switchTab('gating')\">Gating</button>
        <button class=\"tab\" onclick=\"switchTab('health')\">Salud</button>
        <button class=\"tab\" onclick=\"switchTab('history')\">Historial</button>
  </div>

  <div id=\"activeTab\">
    <div class=\"grid\" id=\"activeGrid\"></div>
  </div>

  <div id=\"historyTab\" style=\"display:none;\">
    <div class=\"card\">
      <table class=\"table\" id=\"historyTable\"></table>
    </div>
  </div>

    <div id=\"plansTab\" style=\"display:none;\">
        <div class=\"card\">
            <div id=\"plansSummary\"></div>
        </div>
    </div>

    <div id=\"reportTab\" style=\"display:none;\">
        <div class=\"card\" style=\"margin-bottom:12px;\">
            <div id=\"metricsSummary\"></div>
        </div>
        <div class=\"card\">
            <table class=\"table\" id=\"weeklyTable\"></table>
        </div>
    </div>

    <div id=\"gatingTab\" style=\"display:none;\">
        <div class=\"card\" id=\"gatingRules\"></div>
    </div>

    <div id=\"healthTab\" style=\"display:none;\">
        <div class=\"card\" id=\"healthStatus\"></div>
    </div>
</div>

<div class=\"modal\" id=\"chartModal\">
  <div class=\"modal-content\">
    <div style=\"display:flex; justify-content: space-between; align-items:center; margin-bottom:10px;\">
      <strong id=\"chartTitle\">Chart</strong>
      <button class=\"btn\" onclick=\"closeChart()\">Cerrar</button>
    </div>
    <canvas id=\"chartCanvas\" height=\"360\"></canvas>
  </div>
</div>

<script>
const API = window.location.origin + '/api';

function fmtCurrency(x){ return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(x || 0); }
function fmtPct(x){ return (x || 0).toFixed(2) + '%'; }

function switchTab(which){
    const tabs = ['active','plans','report','gating','health','history'];
    tabs.forEach(t => {
        const el = document.getElementById(t + 'Tab');
        if (el) el.style.display = (t === which) ? 'block' : 'none';
    });
    document.querySelectorAll('.tab').forEach((t, i) => {
        t.classList.toggle('active', tabs[i] === which);
    });
    if (which === 'plans') loadPlans();
    if (which === 'report') loadReport();
    if (which === 'gating') loadGatingRules();
    if (which === 'health') loadHealth();
}

function loadPlans(){
    fetch(API + '/plans')
        .then(r=>r.json())
        .then(data=>{
            const target = document.getElementById('plansSummary');
            if (!data || data.length === 0) {
                target.innerHTML = '<div>Sin datos de planes.</div>';
                return;
            }
            target.innerHTML = data.map(p=>`
                <div style="margin-bottom:10px; padding:10px; border:1px solid #e5e7eb; border-radius:8px;">
                    <strong>${p.name}</strong> — Trades: ${p.trades} | Exposición: ${fmtCurrency(p.exposure)} | Prob win avg: ${p.prob_win_avg.toFixed(2)}%
                </div>
            `).join('');
        })
        .catch(()=>{
            document.getElementById('plansSummary').innerHTML = '<div>Error cargando planes.</div>';
        });
}

function loadReport(){
    fetch(API + '/report')
        .then(r=>r.json())
        .then(data=>{
            const m = data.metrics || {};
            document.getElementById('metricsSummary').innerHTML = `
                <div><strong>Total trades:</strong> ${m.total_trades ?? 0} | <strong>Valid:</strong> ${m.valid_trades ?? 0}</div>
                <div><strong>PF:</strong> ${m.pf ? m.pf.toFixed(2) : 'n/a'} | <strong>WR:</strong> ${m.wr ? m.wr.toFixed(1) : 'n/a'}%</div>
                <div><strong>PnL:</strong> ${fmtCurrency(m.pnl_total ?? 0)} | <strong>Max DD:</strong> ${fmtCurrency(m.max_dd ?? 0)}</div>
            `;

            const weekly = data.weekly || [];
            if (weekly.length === 0) {
                document.getElementById('weeklyTable').innerHTML = '<tr><td>Sin reporte semanal</td></tr>';
                return;
            }
            document.getElementById('weeklyTable').innerHTML = `
                <thead><tr><th>Semana</th><th>Trades</th><th>PnL</th><th>WR</th><th>Avg PnL</th></tr></thead>
                <tbody>
                    ${weekly.map(w=>`
                        <tr>
                            <td>${w.week}</td>
                            <td>${w.trades}</td>
                            <td style="color:${w.pnl_total >= 0 ? '#16a34a' : '#dc2626'}; font-weight:700;">${fmtCurrency(w.pnl_total)}</td>
                            <td>${(w.wr ?? 0).toFixed(1)}%</td>
                            <td>${fmtCurrency(w.avg_pnl)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
        })
        .catch(()=>{
            document.getElementById('metricsSummary').innerHTML = '<div>Error cargando métricas.</div>';
            document.getElementById('weeklyTable').innerHTML = '<tr><td>Error cargando reporte semanal</td></tr>';
        });
}

function loadGatingRules(){
    fetch(API + '/gating')
        .then(r=>r.json())
        .then(data=>{
            const target = document.getElementById('gatingRules');
            target.innerHTML = `
                <div><strong>Threshold:</strong> ${data.threshold}</div>
                <div><strong>Max por ticker/día:</strong> ${data.max_per_ticker_day}</div>
                <div><strong>Max por día:</strong> ${data.max_per_day}</div>
                <div><strong>Regime flags:</strong> ${data.regime_flags.join(', ')}</div>
                <div><strong>Split exclusion:</strong> ${data.exclude_splits ? 'Sí' : 'No'}</div>
                <div><strong>Daily stop:</strong> ${data.daily_stop_enabled ? 'Sí' : 'No'} | SL max: ${data.daily_stop_max_sl} | R limit: ${data.daily_stop_r_limit}</div>
            `;
        })
        .catch(()=>{
            document.getElementById('gatingRules').innerHTML = '<div>Error cargando reglas de gating.</div>';
        });
}

function loadHealth(){
    fetch(API + '/health')
        .then(r=>r.json())
        .then(h=>{
            document.getElementById('healthStatus').innerHTML = `
                <div>Plan: ${h.plan_exists ? 'OK' : 'Falta'} | Trades: ${h.trades_exists ? 'OK' : 'Falta'} | Equity: ${h.equity_exists ? 'OK' : 'Falta'}</div>
                <div>Snapshot age: ${h.snapshot_age_sec ? h.snapshot_age_sec.toFixed(1) + 's' : 'n/a'} | Price cache: ${h.price_cache}</div>
            `;
        })
        .catch(()=>{
            document.getElementById('healthStatus').innerHTML = '<div>Error cargando salud del sistema.</div>';
        });
}

function drawChart(points){
  const canvas = document.getElementById('chartCanvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.clientWidth;
  const h = canvas.height = 360;
  ctx.clearRect(0,0,w,h);
  if(!points || points.length === 0){
    ctx.fillText('Sin datos', 12, 24); return;
  }
  const closes = points.map(p=>p.close);
  const min = Math.min(...closes), max = Math.max(...closes);
  const range = (max-min) || 1;
  ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p,i)=>{
    const x = (i/(points.length-1))*(w-40)+20;
    const y = 20 + (1-((p.close-min)/range))*(h-40);
    if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
}

function openChart(ticker){
  document.getElementById('chartTitle').textContent = 'Chart ' + ticker;
  document.getElementById('chartModal').classList.add('active');
  fetch(API + '/chart/' + encodeURIComponent(ticker))
    .then(r=>r.json())
    .then(data=>drawChart(data.points || []))
    .catch(()=>drawChart([]));
}
function closeChart(){ document.getElementById('chartModal').classList.remove('active'); }

function refresh(){
  fetch(API + '/snapshot')
    .then(r=>r.json())
    .then(data=>{
      document.getElementById('updateTime').textContent = new Date().toLocaleString();
      document.getElementById('marketStatus').textContent = data.market_status || 'n/a';
      const s = data.summary;
      document.getElementById('stats').innerHTML = `
        <div class="card"><h3>P&L total</h3><div class="value">${fmtCurrency(s.pnl_total)}</div></div>
        <div class="card"><h3>Win rate</h3><div class="value">${fmtPct(s.win_rate)}</div></div>
        <div class="card"><h3>Exposición</h3><div class="value">${fmtCurrency(s.exposure)}</div></div>
        <div class="card"><h3>Trades activos</h3><div class="value">${s.active_trades}</div></div>
      `;

      const active = data.active || [];
      if(active.length === 0){
        document.getElementById('activeGrid').innerHTML = '<div class="card">Sin trades activos</div>';
      }else{
        document.getElementById('activeGrid').innerHTML = active.map(t=>`
          <div class="trade ${t.pnl >= 0 ? 'profit':'loss'}">
            <h4>${t.ticker} <span class="badge ${t.side.toLowerCase()}">${t.side}</span></h4>
            <div class="row"><span>Actual</span><strong>${fmtCurrency(t.current)}</strong></div>
            <div class="row"><span>Entry</span><strong>${fmtCurrency(t.entry)}</strong></div>
            <div class="row"><span>TP / SL</span><strong>${fmtCurrency(t.tp)} / ${fmtCurrency(t.sl)}</strong></div>
            <div class="row"><span>PnL</span><strong>${fmtCurrency(t.pnl)} (${fmtPct(t.pnl_pct)})</strong></div>
            <div class="row"><span>Prob win</span><strong>${t.prob_win.toFixed(1)}%</strong></div>
            <button class="btn" onclick="openChart('${t.ticker}')">Ver chart</button>
          </div>
        `).join('');
      }

      const history = data.history || [];
      if(history.length === 0){
        document.getElementById('historyTable').innerHTML = '<tr><td>Sin historial</td></tr>';
      }else{
        document.getElementById('historyTable').innerHTML = `
          <thead><tr><th>Ticker</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Reason</th><th>Entry Time</th></tr></thead>
          <tbody>
            ${history.slice(0, 200).map(h=>`
              <tr>
                <td>${h.ticker}</td>
                <td>${h.side}</td>
                <td>${fmtCurrency(h.entry)}</td>
                <td>${fmtCurrency(h.exit)}</td>
                <td style="color:${h.pnl>=0?'#16a34a':'#dc2626'}; font-weight:700;">${fmtCurrency(h.pnl)}</td>
                <td>${h.exit_reason}</td>
                <td>${h.entry_time || ''}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
      }
    })
    .catch(()=>{});
}

setInterval(refresh, 30000);
refresh();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/snapshot")
def api_snapshot():
    snap = get_cached_snapshot()
    status, _ = _get_market_status()
    snap["market_status"] = status
    return jsonify(snap)


@app.route("/api/plans")
def api_plans():
    with CSV_LOCK:
        plan_clean = _read_csv(PLAN_PATH)
        plan_raw = _read_csv(PLAN_RAW_PATH)
    summary = [
        _plan_summary(plan_raw, "PLAN_RAW"),
        _plan_summary(plan_clean, "PLAN_CLEAN"),
    ]
    return jsonify(summary)


@app.route("/api/report")
def api_report():
    metrics = _read_json(METRICS_PATH) or {}
    weekly = _load_weekly_report()
    return jsonify({"metrics": metrics, "weekly": weekly})


@app.route("/api/gating")
def api_gating():
    return jsonify({
        "threshold": 0.70,
        "max_per_ticker_day": 1,
        "max_per_day": 6,
        "regime_flags": ["is_high_vol_prev", "is_wide_range_prev", "is_directional_prev"],
        "exclude_splits": True,
        "daily_stop_enabled": True,
        "daily_stop_max_sl": 2,
        "daily_stop_r_limit": -1.0,
    })


@app.route("/api/chart/<ticker>")
def api_chart(ticker):
    return jsonify({"ticker": ticker, "points": _build_chart(ticker)})


@app.route("/api/health")
def api_health():
    return jsonify({
        "plan_exists": PLAN_PATH.exists(),
        "trades_exists": TRADES_PATH.exists(),
        "equity_exists": EQUITY_PATH.exists(),
        "price_cache": len(PRICE_CACHE),
        "snapshot_age_sec": time.time() - SNAPSHOT_LAST_BUILD if SNAPSHOT_LAST_BUILD else None,
    })


def main():
    port = int(os.environ.get("DASHBOARD_PORT", "8050"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
