"""
Dashboard mejorado para monitorizar dos planes simultáneamente
- Plan STANDARD (prob_win >= 0.50)
- Plan PROBWIN_55 (prob_win >= 0.55)
"""
from flask import Flask, render_template_string, jsonify
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import yfinance as yf
import threading
import time

app = Flask(__name__)

# Configuración
WEEK_START = datetime.now().strftime("%Y-%m-%d")
PLANS_DIR = Path("evidence/weekly_plans")
CONFIG_FILE = Path(f"evidence/monitor_this_week/config_{WEEK_START}.json")

# Cache de precios actuales
prices_cache = {}
last_update = None

def load_plans():
    """Cargar ambos planes del día"""
    plans = {}
    
    std_file = PLANS_DIR / f"plan_standard_{WEEK_START}.csv"
    pw_file = PLANS_DIR / f"plan_probwin55_{WEEK_START}.csv"
    
    if std_file.exists():
        plans['STANDARD'] = pd.read_csv(std_file)
    if pw_file.exists():
        plans['PROBWIN_55'] = pd.read_csv(pw_file)
    
    return plans

def load_config():
    """Cargar configuración"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def update_prices():
    """Actualizar precios en background"""
    global prices_cache, last_update
    
    plans = load_plans()
    tickers = set()
    
    for plan_data in plans.values():
        if not plan_data.empty:
            tickers.update(plan_data['ticker'].unique())
    
    if tickers:
        try:
            data = yf.download(' '.join(tickers), period="1d", progress=False)
            if data is not None:
                for ticker in tickers:
                    try:
                        if len(tickers) == 1:
                            prices_cache[ticker] = float(data['Close'].iloc[-1])
                        else:
                            prices_cache[ticker] = float(data['Close'][ticker].iloc[-1])
                    except:
                        pass
                last_update = datetime.now().isoformat()
        except:
            pass

def background_price_updater():
    """Thread para actualizar precios cada minuto"""
    while True:
        update_prices()
        time.sleep(60)

# Iniciar thread de actualización
updater_thread = threading.Thread(target=background_price_updater, daemon=True)
updater_thread.start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Plan Comparison Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .date-info {
            color: #ddd;
            text-align: center;
            margin-bottom: 20px;
            font-size: 0.95em;
        }
        .plans-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .plan-card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
            border-left: 5px solid #2196F3;
        }
        .plan-card.probwin {
            border-left-color: #FF9800;
        }
        .plan-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 15px;
        }
        .plan-title {
            font-size: 1.5em;
            font-weight: bold;
            color: #2196F3;
        }
        .plan-card.probwin .plan-title {
            color: #FF9800;
        }
        .threshold-badge {
            display: inline-block;
            background: #f0f0f0;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            color: #666;
        }
        .stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat {
            background: #f9f9f9;
            padding: 12px;
            border-radius: 8px;
            border-left: 3px solid #2196F3;
        }
        .plan-card.probwin .stat {
            border-left-color: #FF9800;
        }
        .stat-label {
            font-size: 0.85em;
            color: #999;
            margin-bottom: 5px;
        }
        .stat-value {
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .trades-table th {
            background: #f5f5f5;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #666;
            border-bottom: 2px solid #ddd;
        }
        .trades-table td {
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }
        .trades-table tr:hover {
            background: #fafafa;
        }
        .ticker { font-weight: bold; color: #2196F3; }
        .buy { color: #4CAF50; font-weight: bold; }
        .sell { color: #f44336; font-weight: bold; }
        .comparison-section {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }
        .comparison-section h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.3em;
        }
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
        }
        .comparison-table th {
            background: #2196F3;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        .comparison-table td {
            padding: 12px;
            border-bottom: 1px solid #ddd;
        }
        .comparison-table tr:hover {
            background: #f9f9f9;
        }
        .last-update {
            text-align: center;
            margin-top: 20px;
            font-size: 0.9em;
            color: #999;
        }
        .position-summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        @media (max-width: 1024px) {
            .plans-grid {
                grid-template-columns: 1fr;
            }
            .stats {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trade Plans Comparison</h1>
        <div class="date-info">
            <strong>Week:</strong> {{ config.week_start }} | 
            <strong>Capital:</strong> ${{ "%.2f"|format(config.capital) }} |
            <strong>Max Deploy:</strong> ${{ "%.2f"|format(config.max_deploy) }}
        </div>

        <div class="plans-grid">
            <!-- PLAN STANDARD -->
            <div class="plan-card">
                <div class="plan-header">
                    <span class="plan-title">STANDARD</span>
                    <span class="threshold-badge">prob_win >= 0.50</span>
                </div>
                
                <div class="position-summary">
                    <div style="font-size: 1.2em; margin-bottom: 10px;">
                        <strong>{{ plans.STANDARD.shape[0] }}</strong> Posiciones
                    </div>
                    <div>Exposición: <strong>${{ "%.2f"|format(plans.STANDARD.exposure.sum() if plans.STANDARD is not none else 0) }}</strong></div>
                </div>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-label">Avg Prob Win</div>
                        <div class="stat-value">{{ "%.2f"|format(plans.STANDARD.prob_win.mean() if plans.STANDARD is not none else 0) }}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">Max Exposure</div>
                        <div class="stat-value">${{ "%.0f"|format(plans.STANDARD.exposure.max() if plans.STANDARD is not none else 0) }}</div>
                    </div>
                </div>

                {% if plans.STANDARD is not none and plans.STANDARD.shape[0] > 0 %}
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Side</th>
                            <th>Entry</th>
                            <th>TP</th>
                            <th>SL</th>
                            <th>Qty</th>
                            <th>Prob Win</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for _, row in plans.STANDARD.iterrows() %}
                        <tr>
                            <td class="ticker">{{ row.ticker }}</td>
                            <td class="{% if row.side == 'BUY' %}buy{% else %}sell{% endif %}">{{ row.side }}</td>
                            <td>${{ "%.2f"|format(row.entry) }}</td>
                            <td>${{ "%.2f"|format(row.tp_price) }}</td>
                            <td>${{ "%.2f"|format(row.sl_price) }}</td>
                            <td>{{ row.qty }}</td>
                            <td><strong>{{ "%.2f"|format(row.prob_win) }}</strong></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% endif %}
            </div>

            <!-- PLAN PROBWIN_55 -->
            <div class="plan-card probwin">
                <div class="plan-header">
                    <span class="plan-title">PROBWIN_55</span>
                    <span class="threshold-badge">prob_win >= 0.55</span>
                </div>
                
                <div class="position-summary" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                    <div style="font-size: 1.2em; margin-bottom: 10px;">
                        <strong>{{ plans.PROBWIN_55.shape[0] if plans.PROBWIN_55 is not none else 0 }}</strong> Posiciones
                    </div>
                    <div>Exposición: <strong>${{ "%.2f"|format(plans.PROBWIN_55.exposure.sum() if plans.PROBWIN_55 is not none else 0) }}</strong></div>
                </div>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-label">Avg Prob Win</div>
                        <div class="stat-value">{{ "%.2f"|format(plans.PROBWIN_55.prob_win.mean() if plans.PROBWIN_55 is not none else 0) }}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">Max Exposure</div>
                        <div class="stat-value">${{ "%.0f"|format(plans.PROBWIN_55.exposure.max() if plans.PROBWIN_55 is not none else 0) }}</div>
                    </div>
                </div>

                {% if plans.PROBWIN_55 is not none and plans.PROBWIN_55.shape[0] > 0 %}
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Side</th>
                            <th>Entry</th>
                            <th>TP</th>
                            <th>SL</th>
                            <th>Qty</th>
                            <th>Prob Win</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for _, row in plans.PROBWIN_55.iterrows() %}
                        <tr>
                            <td class="ticker">{{ row.ticker }}</td>
                            <td class="{% if row.side == 'BUY' %}buy{% else %}sell{% endif %}">{{ row.side }}</td>
                            <td>${{ "%.2f"|format(row.entry) }}</td>
                            <td>${{ "%.2f"|format(row.tp_price) }}</td>
                            <td>${{ "%.2f"|format(row.sl_price) }}</td>
                            <td>{{ row.qty }}</td>
                            <td><strong>{{ "%.2f"|format(row.prob_win) }}</strong></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% endif %}
            </div>
        </div>

        <!-- COMPARISON SECTION -->
        <div class="comparison-section">
            <h2>Comparative Analysis</h2>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>STANDARD (≥0.50)</th>
                        <th>PROBWIN_55 (≥0.55)</th>
                        <th>Difference</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Positions</strong></td>
                        <td>{{ plans.STANDARD.shape[0] if plans.STANDARD is not none else 0 }}</td>
                        <td>{{ plans.PROBWIN_55.shape[0] if plans.PROBWIN_55 is not none else 0 }}</td>
                        <td>{{ (plans.STANDARD.shape[0] if plans.STANDARD is not none else 0) - (plans.PROBWIN_55.shape[0] if plans.PROBWIN_55 is not none else 0) }}</td>
                    </tr>
                    <tr>
                        <td><strong>Total Exposure</strong></td>
                        <td>${{ "%.2f"|format(plans.STANDARD.exposure.sum() if plans.STANDARD is not none else 0) }}</td>
                        <td>${{ "%.2f"|format(plans.PROBWIN_55.exposure.sum() if plans.PROBWIN_55 is not none else 0) }}</td>
                        <td>${{ "%.2f"|format((plans.STANDARD.exposure.sum() if plans.STANDARD is not none else 0) - (plans.PROBWIN_55.exposure.sum() if plans.PROBWIN_55 is not none else 0)) }}</td>
                    </tr>
                    <tr>
                        <td><strong>Avg Prob Win</strong></td>
                        <td>{{ "%.3f"|format(plans.STANDARD.prob_win.mean() if plans.STANDARD is not none else 0) }}</td>
                        <td>{{ "%.3f"|format(plans.PROBWIN_55.prob_win.mean() if plans.PROBWIN_55 is not none else 0) }}</td>
                        <td>{{ "%.3f"|format((plans.PROBWIN_55.prob_win.mean() if plans.PROBWIN_55 is not none else 0) - (plans.STANDARD.prob_win.mean() if plans.STANDARD is not none else 0)) }}</td>
                    </tr>
                    <tr>
                        <td><strong>Min Prob Win</strong></td>
                        <td>{{ "%.3f"|format(plans.STANDARD.prob_win.min() if plans.STANDARD is not none else 0) }}</td>
                        <td>{{ "%.3f"|format(plans.PROBWIN_55.prob_win.min() if plans.PROBWIN_55 is not none else 0) }}</td>
                        <td>{{ "%.3f"|format((plans.PROBWIN_55.prob_win.min() if plans.PROBWIN_55 is not none else 0) - (plans.STANDARD.prob_win.min() if plans.STANDARD is not none else 0)) }}</td>
                    </tr>
                </tbody>
            </table>

            <div class="last-update">
                <p><strong>Dashboard Updated:</strong> {{ datetime.now().strftime('%Y-%m-%d %H:%M:%S') }}</p>
                <p><em>Prices update every minute from yfinance</em></p>
            </div>
        </div>
    </div>

    <script>
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    plans = load_plans()
    config = load_config()
    return render_template_string(HTML_TEMPLATE, plans=plans, config=config, datetime=datetime)

@app.route('/api/plans')
def api_plans():
    """API endpoint para planes en JSON"""
    plans = load_plans()
    result = {}
    for name, plan_df in plans.items():
        if plan_df is not None and not plan_df.empty:
            result[name] = plan_df.to_dict('records')
    return jsonify(result)

@app.route('/api/status')
def api_status():
    """API endpoint para status"""
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'last_price_update': last_update,
        'week_start': WEEK_START,
        'prices_cache_size': len(prices_cache)
    })

if __name__ == '__main__':
    print("="*80)
    print("DASHBOARD - COMPARACION DE PLANES SEMANALES")
    print("="*80)
    print(f"\nSemana: {WEEK_START}")
    print(f"\nEndpoints:")
    print(f"  Dashboard: http://localhost:7777/")
    print(f"  API Plans: http://localhost:7777/api/plans")
    print(f"  API Status: http://localhost:7777/api/status")
    print(f"\nMonitorizado:")
    print(f"  - Plan STANDARD (prob_win >= 0.50)")
    print(f"  - Plan PROBWIN_55 (prob_win >= 0.55)")
    print(f"\n✓ Iniciando servidor...\n")
    
    app.run(host='127.0.0.1', port=7777, debug=False)
