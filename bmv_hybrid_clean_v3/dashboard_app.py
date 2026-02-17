#!/usr/bin/env python3
"""
dashboard_app.py
Servidor Flask ligero para monitorear posiciones en vivo desde cualquier dispositivo.
Uso: python dashboard_app.py
Acceso: http://localhost:5000
"""

from flask import Flask, jsonify, render_string, send_file
from pathlib import Path
import pandas as pd
import json
from datetime import datetime
import os

app = Flask(__name__)
BASE_DIR = Path(__file__).parent

# ============================================================================
# RUTAS DE DATOS
# ============================================================================

REPORTS_DIR = BASE_DIR / "reports"
BITACORA_FILE = BASE_DIR / "bitacora_intraday.csv"
EQUITY_FILE = REPORTS_DIR / "equity_curve.csv"
ACTIVE_POS_FILE = BASE_DIR / "active_positions.json"
CONFIG_FILE = BASE_DIR / "config" / "paper.yaml"

# ============================================================================
# UTILIDADES
# ============================================================================

def safe_read_csv(path, max_rows=100):
    """Lee CSV de forma segura."""
    try:
        if Path(path).exists():
            df = pd.read_csv(path)
            return df.tail(max_rows).to_dict('records')
    except Exception as e:
        print(f"Error leyendo {path}: {e}")
    return []

def safe_read_json(path):
    """Lee JSON de forma segura."""
    try:
        if Path(path).exists():
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error leyendo {path}: {e}")
    return {}

# ============================================================================
# ENDPOINTS API
# ============================================================================

@app.route('/')
def index():
    """Dashboard HTML principal."""
    return render_string(HTML_TEMPLATE, 
                        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/api/positions')
def api_positions():
    """Posiciones activas en vivo."""
    positions = safe_read_json(ACTIVE_POS_FILE)
    
    # Enriquecer con datos de bitácora si existe
    if BITACORA_FILE.exists():
        bitacora = safe_read_csv(BITACORA_FILE, max_rows=1)
        if bitacora:
            positions['last_bitacora'] = bitacora[0]
    
    return jsonify({
        'status': 'success',
        'data': positions,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/equity')
def api_equity():
    """Curva de capital diaria."""
    data = safe_read_csv(EQUITY_FILE, max_rows=252)  # 1 año aprox
    
    return jsonify({
        'status': 'success',
        'data': data,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/trades/latest')
def api_trades_latest():
    """Últimos 20 trades."""
    # Buscar archivos trades más recientes
    trades = []
    for day_dir in sorted(REPORTS_DIR.glob("paper_trading/*/"), reverse=True)[:10]:
        trades_file = day_dir / "trades.csv"
        if trades_file.exists():
            trades.extend(safe_read_csv(trades_file, max_rows=5))
    
    return jsonify({
        'status': 'success',
        'data': trades[:20],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/stats')
def api_stats():
    """Estadísticas resumidas."""
    stats = {
        'data_dir_size_mb': sum(f.stat().st_size for f in BASE_DIR.rglob('*')) / 1024 / 1024,
        'config_file': CONFIG_FILE.exists(),
        'models_count': len(list((BASE_DIR / "models").glob("*.joblib"))),
        'reports_days': len(list((REPORTS_DIR / "paper_trading").glob("*/"))),
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(stats)

# ============================================================================
# TEMPLATE HTML
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BMV Hybrid Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
               background: #0f172a; color: #e2e8f0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }
        h1 { font-size: 2.5em; margin-bottom: 5px; }
        .info { font-size: 0.9em; color: #94a3b8; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; }
        .card h2 { font-size: 1.1em; margin-bottom: 15px; color: #38bdf8; }
        .card-value { font-size: 2em; font-weight: bold; margin: 10px 0; }
        .card-subtext { font-size: 0.85em; color: #64748b; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th { background: #0f172a; padding: 10px; text-align: left; border-bottom: 2px solid #38bdf8; }
        td { padding: 10px; border-bottom: 1px solid #334155; }
        tr:hover { background: #293548; }
        
        .chart-container { position: relative; height: 300px; margin-top: 20px; }
        .loading { text-align: center; color: #94a3b8; padding: 40px; }
        .error { background: #7f1d1d; border: 1px solid #dc2626; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .success { background: #1e3a1f; border: 1px solid #16a34a; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .warning { background: #78350f; border: 1px solid #f59e0b; padding: 15px; border-radius: 5px; margin: 10px 0; }
        
        .pnl-positive { color: #16a34a; font-weight: bold; }
        .pnl-negative { color: #dc2626; font-weight: bold; }
        
        footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #334155; color: #64748b; font-size: 0.85em; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 BMV Hybrid - Dashboard</h1>
            <div class="info">Trading en Vivo - Última actualización: {{ last_update }}</div>
        </header>
        
        <!-- Tarjetas de resumen -->
        <div class="grid">
            <div class="card">
                <h2>💰 Posiciones Activas</h2>
                <div id="active-positions" class="loading">Cargando...</div>
            </div>
            
            <div class="card">
                <h2>📈 Capital Hoy</h2>
                <div id="today-equity" class="loading">Cargando...</div>
            </div>
            
            <div class="card">
                <h2>🎯 PnL Total</h2>
                <div id="total-pnl" class="loading">Cargando...</div>
            </div>
        </div>
        
        <!-- Últimos trades -->
        <div class="card">
            <h2>📝 Últimos Trades (20)</h2>
            <div id="trades-table" class="loading">Cargando...</div>
        </div>
        
        <!-- Gráfico de equity -->
        <div class="card">
            <h2>📊 Curva de Capital</h2>
            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>
        </div>
    </div>
    
    <footer>
        <p>Servidor corriendo en RPi - Dashboard ligero para monitoreo remoto</p>
        <p><small>Actualizar página cada 5 minutos recomendado</small></p>
    </footer>
    
    <script>
        // Cargar posiciones activas
        async function loadPositions() {
            try {
                const resp = await fetch('/api/positions');
                const json = await resp.json();
                const container = document.getElementById('active-positions');
                
                if (json.data && Object.keys(json.data).length > 0) {
                    container.innerHTML = `<div class="success"><strong>${Object.keys(json.data).length}</strong> posiciones abiertas</div>`;
                    container.innerHTML += `<pre style="background:#0f172a; padding:10px; border-radius:5px; font-size:0.8em; overflow-x:auto;">${JSON.stringify(json.data, null, 2)}</pre>`;
                } else {
                    container.innerHTML = '<div class="card-value">0</div><div class="card-subtext">Sin posiciones activas</div>';
                }
            } catch (e) {
                document.getElementById('active-positions').innerHTML = `<div class="error">Error: ${e.message}</div>`;
            }
        }
        
        // Cargar equity
        async function loadEquity() {
            try {
                const resp = await fetch('/api/equity');
                const json = await resp.json();
                if (json.data && json.data.length > 0) {
                    const lastRow = json.data[json.data.length - 1];
                    const equity = lastRow.equity || lastRow.capital || 0;
                    const pnl = lastRow.pnl || 0;
                    const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
                    document.getElementById('today-equity').innerHTML = 
                        `<div class="card-value">$${equity.toFixed(2)}</div><div class="card-subtext ${pnlClass}">PnL: ${pnl.toFixed(2)}</div>`;
                }
            } catch (e) {
                document.getElementById('today-equity').innerHTML = `<div class="error">Error cargando equity</div>`;
            }
        }
        
        // Cargar trades
        async function loadTrades() {
            try {
                const resp = await fetch('/api/trades/latest');
                const json = await resp.json();
                if (json.data && json.data.length > 0) {
                    let html = '<table><tr><th>Ticker</th><th>Entrada</th><th>Salida</th><th>PnL</th><th>Status</th></tr>';
                    json.data.forEach(trade => {
                        const pnlClass = (trade.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
                        html += `<tr>
                            <td>${trade.ticker || '-'}</td>
                            <td>${trade.entry_price || '-'}</td>
                            <td>${trade.exit_price || '-'}</td>
                            <td class="${pnlClass}">${(trade.pnl || 0).toFixed(2)}</td>
                            <td>${trade.status || '-'}</td>
                        </tr>`;
                    });
                    html += '</table>';
                    document.getElementById('trades-table').innerHTML = html;
                }
            } catch (e) {
                document.getElementById('trades-table').innerHTML = `<div class="error">Error cargando trades</div>`;
            }
        }
        
        // Cargar gráfico de equity
        async function loadChart() {
            try {
                const resp = await fetch('/api/equity');
                const json = await resp.json();
                if (json.data && json.data.length > 0) {
                    const ctx = document.getElementById('equityChart').getContext('2d');
                    const dates = json.data.map(row => row.date || row.datetime || '');
                    const equities = json.data.map(row => row.equity || row.capital || 0);
                    
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: dates,
                            datasets: [{
                                label: 'Capital',
                                data: equities,
                                borderColor: '#38bdf8',
                                backgroundColor: 'rgba(56, 189, 248, 0.1)',
                                fill: true,
                                tension: 0.4,
                                pointRadius: 2,
                                pointHoverRadius: 5
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
            } catch (e) {
                console.error('Error gráfico:', e);
            }
        }
        
        // Cargar todo
        function refresh() {
            loadPositions();
            loadEquity();
            loadTrades();
            loadChart();
        }
        
        refresh();
        setInterval(refresh, 300000); // Actualizar cada 5 minutos
    </script>
</body>
</html>
"""

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("""
    ╔════════════════════════════════════════╗
    ║  BMV Hybrid Dashboard - Flask Server   ║
    ╚════════════════════════════════════════╝
    
    🌐 Servidor corriendo en: http://0.0.0.0:5000
    
    Acceso remoto:
      - Desde RPi: http://localhost:5000
      - Desde otros dispositivos: http://<rpi-ip>:5000
    
    Presiona CTRL+C para detener.
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
