#!/usr/bin/env python3
"""
Trade Plan Monitor Dashboard
Extrae precios en vivo (Google/yfinance) y visualiza avance vs plan
"""

import pandas as pd
import json
from datetime import datetime
import yfinance as yf
from pathlib import Path

# Leer trade plan ejecutable
TRADE_PLAN_PATH = Path("val/trade_plan_EXECUTE.csv")

def get_live_prices(tickers):
    """Extrae precios actuales de Google (via yfinance)"""
    try:
        data = yf.download(tickers, period="1d", progress=False)
        prices = {}
        
        # Handle both single and multiple tickers
        if isinstance(data, pd.DataFrame) and len(data.columns) > 1:
            # Multiple tickers - data["Close"] is a Series with ticker index
            close_prices = data["Close"].iloc[-1]
            prices = close_prices.to_dict()
        else:
            # Single ticker or single row
            if "Close" in data.columns:
                prices[tickers[0]] = data["Close"].iloc[-1]
            else:
                prices[tickers[0]] = data.iloc[-1]
        
        return prices
    except Exception as e:
        print(f"⚠️ Error descargando precios: {e}")
        return {}

def calculate_metrics(trade_row, current_price):
    """Calcula métricas de cada trade"""
    entry = trade_row["entry"]
    tp = trade_row["tp_price"]
    sl = trade_row["sl_price"]
    
    # PnL
    pnl = current_price - entry
    pnl_pct = (pnl / entry) * 100
    
    # Progress to TP/SL
    total_range = tp - sl
    current_distance = current_price - sl
    progress_pct = (current_distance / total_range) * 100 if total_range > 0 else 0
    progress_pct = max(0, min(100, progress_pct))  # Clamp 0-100
    
    # Status
    if current_price >= tp:
        status = "✅ TARGET HIT"
        color = "green"
    elif current_price <= sl:
        status = "❌ STOP HIT"
        color = "red"
    elif pnl > 0:
        status = "📈 GANANCIA"
        color = "lightgreen"
    elif pnl < 0:
        status = "📉 PÉRDIDA"
        color = "lightcoral"
    else:
        status = "⏸️ SIN CAMBIO"
        color = "lightgray"
    
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

def generate_html_dashboard(df_trades, metrics):
    """Genera dashboard HTML interactivo"""
    
    # Calcular agregados
    total_pnl = sum(m["pnl"] for m in metrics.values())
    total_pnl_pct = (total_pnl / df_trades["entry"].sum()) * 100
    
    html = f"""
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
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }}
        .header h1 {{
            color: #1e3c72;
            margin-bottom: 10px;
        }}
        .timestamp {{
            color: #666;
            font-size: 14px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card h3 {{
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
            text-transform: uppercase;
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #1e3c72;
        }}
        .summary-card.positive .value {{
            color: #27ae60;
        }}
        .summary-card.negative .value {{
            color: #e74c3c;
        }}
        .trades-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
        }}
        .trade-card {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .trade-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }}
        .trade-header {{
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 2px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .ticker {{
            font-size: 24px;
            font-weight: bold;
            color: #1e3c72;
        }}
        .status-badge {{
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .trade-body {{
            padding: 20px;
        }}
        .price-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }}
        .price-row:last-child {{
            border-bottom: none;
            margin-bottom: 10px;
            padding-bottom: 0;
        }}
        .price-label {{
            color: #666;
            font-size: 13px;
            font-weight: 600;
        }}
        .price-value {{
            font-weight: bold;
            color: #333;
        }}
        .entry-price {{
            color: #3498db;
        }}
        .current-price {{
            color: #1e3c72;
            font-size: 18px;
        }}
        .tp-price {{
            color: #27ae60;
        }}
        .sl-price {{
            color: #e74c3c;
        }}
        .pnl {{
            font-size: 18px;
            font-weight: bold;
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }}
        .pnl.positive {{
            background: #d4edda;
            color: #155724;
        }}
        .pnl.negative {{
            background: #f8d7da;
            color: #721c24;
        }}
        .pnl.neutral {{
            background: #e2e3e5;
            color: #383d41;
        }}
        .progress-container {{
            margin-top: 15px;
        }}
        .progress-label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
        }}
        .progress-bar {{
            width: 100%;
            height: 20px;
            background: #eee;
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3498db 0%, #27ae60 100%);
            transition: width 0.3s ease;
        }}
        .stats-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 10px;
            font-size: 12px;
        }}
        .stat {{
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }}
        .stat-label {{
            color: #999;
            font-size: 11px;
            margin-bottom: 3px;
        }}
        .stat-value {{
            font-weight: bold;
            color: #333;
        }}
        .refresh-btn {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #3498db;
            color: white;
            border: none;
            padding: 15px 25px;
            border-radius: 50px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            transition: all 0.3s;
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .refresh-btn:hover {{
            background: #2980b9;
            transform: scale(1.05);
        }}
        .refresh-btn:active {{
            transform: scale(0.95);
        }}
        .refresh-btn.loading {{
            background: #95a5a6;
            cursor: wait;
        }}
        .refresh-btn .spinner {{
            display: none;
            width: 16px;
            height: 16px;
            border: 2px solid white;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
        }}
        .refresh-btn.loading .spinner {{
            display: block;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        @media (max-width: 768px) {{
            .summary {{
                grid-template-columns: 1fr;
            }}
            .trades-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Trade Monitor Dashboard</h1>
            <p class="timestamp">Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="font-size: 13px; color: #999; margin-top: 5px;">Precios en vivo desde Google Finance (yfinance)</p>
        </div>
        
        <div class="summary">
            <div class="summary-card {('positive' if total_pnl >= 0 else 'negative')}">
                <h3>P&L Total</h3>
                <div class="value">${total_pnl:.2f}</div>
                <p style="font-size: 13px; color: #999; margin-top: 5px;">({total_pnl_pct:+.2f}%)</p>
            </div>
            <div class="summary-card">
                <h3>Exposición</h3>
                <div class="value">${df_trades['exposure'].sum():.2f}</div>
                <p style="font-size: 13px; color: #999; margin-top: 5px;">de $800 cap</p>
            </div>
            <div class="summary-card">
                <h3>Trades Activos</h3>
                <div class="value">{len(df_trades)}</div>
                <p style="font-size: 13px; color: #999; margin-top: 5px;">de 4 en plan</p>
            </div>
            <div class="summary-card">
                <h3>Prob. Win Promedio</h3>
                <div class="value">{df_trades['prob_win'].mean()*100:.1f}%</div>
                <p style="font-size: 13px; color: #999; margin-top: 5px;">del modelo</p>
            </div>
        </div>
        
        <div class="trades-grid">
"""
    
    for ticker, trade in df_trades.iterrows():
        m = metrics[ticker]
        pnl_class = "positive" if m["pnl"] >= 0 else ("negative" if m["pnl"] < 0 else "neutral")
        
        html += f"""
            <div class="trade-card">
                <div class="trade-header">
                    <div class="ticker">{ticker}</div>
                    <div class="status-badge" style="background: {m['color']};">
                        {m['status']}
                    </div>
                </div>
                <div class="trade-body">
                    <div class="pnl {pnl_class}">
                        ${m['pnl']:+.2f} ({m['pnl_pct']:+.2f}%)
                    </div>
                    
                    <div class="price-row">
                        <span class="price-label">Entry</span>
                        <span class="price-value entry-price">${trade['entry']:.2f}</span>
                    </div>
                    
                    <div class="price-row">
                        <span class="price-label">Current Price</span>
                        <span class="price-value current-price">${m['current_price']:.2f}</span>
                    </div>
                    
                    <div class="price-row">
                        <span class="price-label">Target (TP)</span>
                        <span class="price-value tp-price">${trade['tp_price']:.2f}</span>
                    </div>
                    
                    <div class="price-row">
                        <span class="price-label">Stop (SL)</span>
                        <span class="price-value sl-price">${trade['sl_price']:.2f}</span>
                    </div>
                    
                    <div class="progress-container">
                        <div class="progress-label">
                            <span>Progreso SL → TP</span>
                            <span>{m['progress_pct']:.1f}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {m['progress_pct']}%"></div>
                        </div>
                    </div>
                    
                    <div class="stats-row">
                        <div class="stat">
                            <div class="stat-label">Dist a TP</div>
                            <div class="stat-value">${m['distance_to_tp']:.2f}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Dist a SL</div>
                            <div class="stat-value">${m['distance_to_sl']:.2f}</div>
                        </div>
                    </div>
                </div>
            </div>
"""
    
    html += """
        </div>
    </div>
    
    <button class="refresh-btn" onclick="refreshPrices()">
        <span class="spinner"></span>
        <span class="btn-text">🔄 Actualizar Precios</span>
    </button>
    
    <script>
        function refreshPrices() {
            const btn = document.querySelector('.refresh-btn');
            const btnText = document.querySelector('.btn-text');
            
            // Show loading state
            btn.classList.add('loading');
            btn.disabled = true;
            btnText.textContent = 'Actualizando...';
            
            // Reload page after a short delay for visual feedback
            setTimeout(() => {
                location.reload();
            }, 500);
        }
        
        // Auto-refresh cada 60 segundos
        setTimeout(() => {
            location.reload();
        }, 60000);
    </script>
</body>
</html>
"""
    
    return html

def main():
    # Leer trade plan
    if not TRADE_PLAN_PATH.exists():
        print(f"❌ No encontrado: {TRADE_PLAN_PATH}")
        return
    
    df_trades = pd.read_csv(TRADE_PLAN_PATH)
    print(f"📋 Leyendo {len(df_trades)} trades...")
    print(f"   Tickers: {', '.join(df_trades['ticker'].values)}")
    
    # Descargar precios
    print(f"📡 Descargando precios desde Google Finance...")
    prices = get_live_prices(df_trades['ticker'].tolist())
    
    if not prices or len(prices) == 0:
        print("❌ No se pudieron descargar precios")
        return
    
    print(f"✅ Precios obtenidos:")
    for ticker, price in prices.items():
        print(f"   {ticker}: ${price:.2f}")
    
    # Calcular métricas
    metrics = {}
    for ticker, trade in df_trades.set_index('ticker').iterrows():
        if ticker in prices:
            metrics[ticker] = calculate_metrics(trade, prices[ticker])
    
    # Generar HTML
    html = generate_html_dashboard(df_trades.set_index('ticker'), metrics)
    
    # Guardar
    output_path = Path("val/trade_monitor_dashboard.html")
    output_path.write_text(html, encoding='utf-8')
    print(f"\n✅ Dashboard generado: {output_path}")
    print(f"   Abre en navegador: file:///{output_path.absolute()}")
    
    # Guardar también data JSON para debugging
    json_data = {
        "timestamp": datetime.now().isoformat(),
        "trades": df_trades.to_dict('records'),
        "prices": {str(k): float(v) for k, v in prices.items()},
        "metrics": {
            str(k): {
                "pnl": float(v["pnl"]),
                "pnl_pct": float(v["pnl_pct"]),
                "progress_pct": float(v["progress_pct"]),
                "status": v["status"],
            }
            for k, v in metrics.items()
        }
    }
    json_path = Path("val/trade_monitor_data.json")
    json_path.write_text(json.dumps(json_data, indent=2), encoding='utf-8')
    print(f"✅ Data JSON: {json_path}")

if __name__ == "__main__":
    main()
