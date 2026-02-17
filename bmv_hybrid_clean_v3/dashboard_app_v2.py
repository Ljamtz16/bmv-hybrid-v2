#!/usr/bin/env python3
"""
dashboard_app_v2.py
Dashboard production-ready:
- Lee solo archivos procesados (sin recalcular)
- Cache de 15 segundos
- Endpoint /health con telemetría
- Logging estructurado
- Manejo de errores robusto
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

import psutil
import pandas as pd
from flask import Flask, jsonify, render_string, request
from flask_cors import CORS

# ============================================================================
# CONFIG & LOGGER
# ============================================================================

# Load runtime.env
load_dotenv(os.path.expanduser("~/bmv_runtime/config/runtime.env"))

BVM_RUNTIME = Path(os.getenv("BVM_RUNTIME", os.path.expanduser("~/bmv_runtime")))
BVM_LOGS = BVM_RUNTIME / "logs"
BVM_REPORTS = BVM_RUNTIME / "reports"
BVM_STATE = BVM_RUNTIME / "state"

BVM_LOGS.mkdir(parents=True, exist_ok=True)
BVM_REPORTS.mkdir(parents=True, exist_ok=True)
BVM_STATE.mkdir(parents=True, exist_ok=True)

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(BVM_LOGS / "dashboard.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("bmv_dashboard")

app = Flask(__name__)
CORS(app)

# ============================================================================
# CACHE DECORATOR (15 segundos)
# ============================================================================

_cache = {}
_cache_ttl = {}
CACHE_DURATION = 15  # segundos

def cache_result(key, ttl=CACHE_DURATION):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time.time()
            if key in _cache and key in _cache_ttl:
                if now - _cache_ttl[key] < ttl:
                    return _cache[key]
            
            result = f(*args, **kwargs)
            _cache[key] = result
            _cache_ttl[key] = now
            return result
        return wrapper
    return decorator

# ============================================================================
# UTILIDADES
# ============================================================================

def safe_read_csv(path, max_rows=None):
    """Lee CSV con manejo de errores."""
    try:
        if Path(path).exists():
            df = pd.read_csv(path)
            if max_rows:
                df = df.tail(max_rows)
            return df.to_dict('records')
    except Exception as e:
        logger.error(f"Error leyendo {path}: {e}")
    return []

def safe_read_json(path):
    """Lee JSON con manejo de errores."""
    try:
        if Path(path).exists():
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo {path}: {e}")
    return {}

def get_system_health():
    """Telemetría del sistema."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        
        # CPU temp (Linux)
        cpu_temp = None
        try:
            cpu_temp = psutil.sensors_temperatures().get('thermal_zone0', [None])[0]
            cpu_temp = cpu_temp.current if cpu_temp else None
        except:
            pass
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': mem.percent,
            'disk_free_gb': disk.free / (1024**3),
            'disk_total_gb': disk.total / (1024**3),
            'cpu_temp_c': cpu_temp,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error obteniendo health: {e}")
        return {}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
@cache_result('health', ttl=5)
def health():
    """Health check con telemetría."""
    try:
        state = safe_read_json(BVM_STATE / "last_run.json")
        health_data = get_system_health()
        
        # Verificar locks
        has_lock = (BVM_STATE / "lock_daily").exists()
        
        return jsonify({
            'status': 'ok' if not has_lock else 'busy',
            'service': 'bmv-dashboard',
            'last_run': state,
            'system': health_data,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error en health: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/positions')
@cache_result('positions')
def api_positions():
    """Posiciones activas actuales."""
    try:
        active_pos_file = Path(os.path.expanduser("~")) / "bmv_hybrid_clean_v3" / "active_positions.json"
        positions = safe_read_json(active_pos_file)
        
        return jsonify({
            'status': 'success',
            'data': positions,
            'count': len(positions),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error en /api/positions: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/equity')
@cache_result('equity')
def api_equity():
    """Curva de capital (últimos 252 días = 1 año aprox)."""
    try:
        equity_file = BVM_REPORTS / "paper_trading" / "equity_curve.csv"
        data = safe_read_csv(equity_file, max_rows=252)
        
        # Calcular estadísticas
        stats = {}
        if data:
            df = pd.DataFrame(data)
            if 'pnl_cumulative' in df.columns:
                stats = {
                    'total_pnl': float(df['pnl_cumulative'].iloc[-1]) if len(df) > 0 else 0,
                    'today_pnl': float(df['pnl_day'].iloc[-1]) if 'pnl_day' in df.columns and len(df) > 0 else 0,
                    'max_pnl': float(df['pnl_cumulative'].max()),
                    'min_pnl': float(df['pnl_cumulative'].min()),
                }
        
        return jsonify({
            'status': 'success',
            'data': data,
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error en /api/equity: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/trades/latest')
@cache_result('trades')
def api_trades_latest():
    """Últimos 20 trades."""
    try:
        trades = []
        paper_trading_dir = BVM_REPORTS / "paper_trading"
        
        # Buscar últimas 10 carpetas de días
        if paper_trading_dir.exists():
            for day_dir in sorted(paper_trading_dir.glob("*/"), reverse=True)[:10]:
                trades_file = day_dir / "trades.csv"
                if trades_file.exists():
                    trades.extend(safe_read_csv(trades_file, max_rows=5))
        
        return jsonify({
            'status': 'success',
            'data': trades[:20],
            'count': len(trades),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error en /api/trades/latest: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/status')
@cache_result('status', ttl=5)
def api_status():
    """Status general del sistema."""
    try:
        last_run = safe_read_json(BVM_STATE / "last_run.json")
        health = get_system_health()
        
        # Contar artifacts
        reports_count = len(list(BVM_REPORTS.glob("**/*.csv")))
        logs_count = len(list(BVM_LOGS.glob("*.log")))
        
        return jsonify({
            'status': 'ok',
            'last_run': last_run,
            'system_health': health,
            'artifacts': {
                'reports': reports_count,
                'logs': logs_count
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error en /api/status: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    """Dashboard HTML."""
    return render_string(HTML_TEMPLATE, 
                        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        bvm_runtime=str(BVM_RUNTIME))

# ============================================================================
# LOGGING ROUTES
# ============================================================================

@app.before_request
def log_request():
    logger.debug(f"{request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response(response):
    logger.debug(f"Response: {response.status_code}")
    return response

# ============================================================================
# HTML TEMPLATE
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>BMV Hybrid Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
            background: #0f172a; color: #e2e8f0; padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header { 
            text-align: center; margin-bottom: 30px; 
            border-bottom: 2px solid #334155; padding-bottom: 20px;
        }
        h1 { font-size: 2.5em; margin-bottom: 5px; color: #38bdf8; }
        .info { font-size: 0.85em; color: #94a3b8; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .card { 
            background: #1e293b; border: 1px solid #334155; 
            border-radius: 6px; padding: 15px;
        }
        .card h2 { font-size: 0.95em; margin-bottom: 10px; color: #38bdf8; text-transform: uppercase; }
        .card-value { font-size: 1.8em; font-weight: bold; margin: 8px 0; }
        .card-subtext { font-size: 0.8em; color: #64748b; }
        .card-status { padding: 5px 10px; border-radius: 3px; font-size: 0.8em; font-weight: bold; }
        .status-ok { background: #1e3a1f; color: #16a34a; }
        .status-busy { background: #78350f; color: #f59e0b; }
        .status-error { background: #7f1d1d; color: #dc2626; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85em; }
        th { background: #0f172a; padding: 8px; text-align: left; border-bottom: 2px solid #38bdf8; }
        td { padding: 8px; border-bottom: 1px solid #334155; }
        
        .pnl-positive { color: #16a34a; font-weight: bold; }
        .pnl-negative { color: #dc2626; font-weight: bold; }
        
        .chart-container { position: relative; height: 250px; margin-top: 15px; }
        .loading { text-align: center; color: #94a3b8; padding: 20px; }
        
        footer { 
            text-align: center; margin-top: 40px; padding-top: 20px; 
            border-top: 1px solid #334155; color: #64748b; font-size: 0.8em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 BMV Hybrid Dashboard</h1>
            <div class="info">Runtime: {{ bvm_runtime }} | Actualización: {{ last_update }}</div>
        </header>
        
        <div class="grid">
            <div class="card">
                <h2>🔴 Sistema</h2>
                <div id="health-status" class="loading">Cargando...</div>
            </div>
            
            <div class="card">
                <h2>💰 Posiciones</h2>
                <div id="positions-count" class="loading">Cargando...</div>
            </div>
            
            <div class="card">
                <h2>📈 PnL Hoy</h2>
                <div id="today-pnl" class="loading">Cargando...</div>
            </div>
            
            <div class="card">
                <h2>✅ Total PnL</h2>
                <div id="total-pnl" class="loading">Cargando...</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📋 Últimos 10 Trades</h2>
            <div id="trades-table" class="loading">Cargando...</div>
        </div>
        
        <div class="card">
            <h2>📊 Curva de Capital (últimos 60 días)</h2>
            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>
        </div>
    </div>
    
    <footer>
        Dashboard ligero | RPi 4B+ | Actualiza cada 5 min | API en /health
    </footer>
    
    <script>
        const API_CACHE = 15000; // 15 segundos
        
        async function apiCall(endpoint) {
            try {
                const resp = await fetch(endpoint);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                return await resp.json();
            } catch (e) {
                console.error(`API error: ${endpoint}`, e);
                return null;
            }
        }
        
        async function loadHealth() {
            const data = await apiCall('/health');
            if (!data) return;
            
            const container = document.getElementById('health-status');
            const status = data.status === 'ok' ? 'status-ok' : (data.status === 'busy' ? 'status-busy' : 'status-error');
            container.innerHTML = `
                <div class="card-status ${status}">${data.status.toUpperCase()}</div>
                <div class="card-subtext" style="margin-top:8px;">
                    CPU: ${data.system.cpu_percent}% | RAM: ${data.system.memory_percent.toFixed(1)}%<br/>
                    Disk: ${data.system.disk_free_gb.toFixed(1)} GB libre
                </div>
            `;
        }
        
        async function loadPositions() {
            const data = await apiCall('/api/positions');
            if (!data) return;
            
            const container = document.getElementById('positions-count');
            const count = data.count || 0;
            container.innerHTML = `<div class="card-value">${count}</div><div class="card-subtext">Posiciones abiertas</div>`;
        }
        
        async function loadEquity() {
            const data = await apiCall('/api/equity');
            if (!data || !data.stats) return;
            
            const pnl = data.stats.total_pnl || 0;
            const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            
            document.getElementById('today-pnl').innerHTML = 
                `<div class="card-subtext">Hoy</div><div class="card-value ${pnlClass}">$${(data.stats.today_pnl || 0).toFixed(2)}</div>`;
            
            document.getElementById('total-pnl').innerHTML = 
                `<div class="card-value ${pnlClass}">$${pnl.toFixed(2)}</div><div class="card-subtext">Desde inicio</div>`;
        }
        
        async function loadTrades() {
            const data = await apiCall('/api/trades/latest');
            if (!data || !data.data) return;
            
            const container = document.getElementById('trades-table');
            if (data.data.length === 0) {
                container.innerHTML = '<div class="card-subtext">Sin trades aún</div>';
                return;
            }
            
            let html = '<table><tr><th>Ticker</th><th>Entrada</th><th>Salida</th><th>PnL</th><th>Status</th></tr>';
            data.data.slice(0, 10).forEach(trade => {
                const pnlClass = (trade.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
                html += `<tr>
                    <td>${trade.ticker || '-'}</td>
                    <td>${(trade.entry_price || '-').toFixed(2)}</td>
                    <td>${(trade.exit_price || '-').toFixed(2)}</td>
                    <td class="${pnlClass}">${(trade.pnl || 0).toFixed(2)}</td>
                    <td>${trade.status || '-'}</td>
                </tr>`;
            });
            html += '</table>';
            container.innerHTML = html;
        }
        
        async function loadChart() {
            const data = await apiCall('/api/equity');
            if (!data || !data.data) return;
            
            const ctx = document.getElementById('equityChart');
            if (!ctx) return;
            
            const dates = data.data.map(row => row.date || row.datetime || '').slice(-60);
            const equities = data.data.map(row => row.capital || row.equity || 0).slice(-60);
            
            new Chart(ctx.getContext('2d'), {
                type: 'line',
                data: {
                    labels: dates,
                    datasets: [{
                        label: 'Capital',
                        data: equities,
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 1,
                        pointHoverRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: true, labels: { color: '#e2e8f0' } } },
                    scales: {
                        y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                        x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
                    }
                }
            });
        }
        
        async function refresh() {
            await Promise.all([
                loadHealth(),
                loadPositions(),
                loadEquity(),
                loadTrades(),
                loadChart()
            ]);
        }
        
        refresh();
        setInterval(refresh, 300000); // 5 minutos
    </script>
</body>
</html>
"""

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  BMV Dashboard v2 (production-ready)")
    logger.info(f"  BVM_RUNTIME: {BVM_RUNTIME}")
    logger.info(f"  Listen: 0.0.0.0:{os.getenv('DASH_PORT', 5000)}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('DASH_PORT', 5000)),
        debug=False,
        use_reloader=False
    )
