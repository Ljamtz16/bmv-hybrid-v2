#!/usr/bin/env python3
"""
dashboards/dashboard_trade_monitor.py
Generate a self-contained HTML dashboard reading paper broker state.
"""

import argparse
import pandas as pd
import json
from pathlib import Path
from datetime import datetime


def read_state(state_dir):
    """Read broker state files."""
    state_dir = Path(state_dir)
    
    state = {}
    state_file = state_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
    
    positions = []
    pos_file = state_dir / "positions.csv"
    if pos_file.exists():
        pos_df = pd.read_csv(pos_file)
        if not pos_df.empty:
            positions = pos_df.iloc[-1:].to_dict(orient="records")
    
    fills = []
    fills_file = state_dir / "fills.csv"
    if fills_file.exists():
        fills_df = pd.read_csv(fills_file)
        fills = fills_df.tail(20).to_dict(orient="records")
    
    ledger = {}
    ledger_file = state_dir / "pnl_ledger.csv"
    if ledger_file.exists():
        ledger_df = pd.read_csv(ledger_file)
        if not ledger_df.empty:
            ledger = ledger_df.iloc[-1].to_dict()
    
    return state, positions, fills, ledger


def generate_html(state, positions, fills, ledger):
    """Generate HTML dashboard."""
    
    cash = state.get("cash", 0.0)
    equity = state.get("equity", 0.0)
    unrealized = ledger.get("unrealized_pnl", 0.0)
    realized = ledger.get("realized_pnl", 0.0)
    open_count = len(positions)
    
    # Build position rows
    pos_rows = ""
    for pos in positions:
        ticker = pos.get("ticker", "N/A")
        qty = pos.get("qty", 0)
        avg_price = pos.get("avg_price", 0)
        last_price = pos.get("last_price", 0)
        unrealized_pos = pos.get("unrealized_pnl", 0)
        unrealized_pct = (unrealized_pos / (avg_price * qty) * 100) if avg_price * qty > 0 else 0
        
        color = "green" if unrealized_pos > 0 else "red"
        
        pos_rows += f"""
        <tr>
            <td><strong>{ticker}</strong></td>
            <td>{qty:.0f}</td>
            <td>${avg_price:.2f}</td>
            <td>${last_price:.2f}</td>
            <td style="color: {color};">${unrealized_pos:.2f}</td>
            <td style="color: {color};">{unrealized_pct:.2f}%</td>
        </tr>
        """
    
    if not pos_rows:
        pos_rows = "<tr><td colspan='6' style='text-align: center;'>No open positions</td></tr>"
    
    # Build fill rows
    fill_rows = ""
    for fill in fills:
        ticker = fill.get("ticker", "N/A")
        side = fill.get("side", "N/A")
        qty = fill.get("qty", 0)
        price = fill.get("fill_price", 0)
        ts = fill.get("ts", "N/A")
        
        fill_rows += f"""
        <tr>
            <td>{ts}</td>
            <td><strong>{ticker}</strong></td>
            <td>{side}</td>
            <td>{qty:.0f}</td>
            <td>${price:.2f}</td>
        </tr>
        """
    
    if not fill_rows:
        fill_rows = "<tr><td colspan='5' style='text-align: center;'>No fills</td></tr>"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Paper Broker Monitor</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            h1 {{
                color: white;
                margin-bottom: 30px;
                font-size: 32px;
            }}
            .kpi-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .kpi-card {{
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .kpi-label {{
                font-size: 14px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }}
            .kpi-value {{
                font-size: 28px;
                font-weight: bold;
                color: #333;
            }}
            .kpi-value.positive {{
                color: #10b981;
            }}
            .kpi-value.negative {{
                color: #ef4444;
            }}
            .section {{
                background: white;
                padding: 25px;
                border-radius: 12px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .section h2 {{
                font-size: 20px;
                margin-bottom: 15px;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th {{
                background: #f3f4f6;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                color: #374151;
                border-bottom: 1px solid #e5e7eb;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #e5e7eb;
            }}
            tr:hover {{
                background: #f9fafb;
            }}
            .refresh-btn {{
                position: fixed;
                bottom: 30px;
                right: 30px;
                width: 60px;
                height: 60px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 50%;
                font-size: 24px;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                transition: all 0.3s ease;
            }}
            .refresh-btn:hover {{
                background: #5568d3;
                transform: scale(1.1);
            }}
            .refresh-btn.loading {{
                animation: spin 1s linear infinite;
            }}
            @keyframes spin {{
                from {{ transform: rotate(0deg); }}
                to {{ transform: rotate(360deg); }}
            }}
            .timestamp {{
                color: #999;
                font-size: 12px;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Paper Broker Monitor</h1>
            
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Equity</div>
                    <div class="kpi-value">${equity:.2f}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cash</div>
                    <div class="kpi-value">${cash:.2f}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Unrealized P&L</div>
                    <div class="kpi-value {'positive' if unrealized >= 0 else 'negative'}">${unrealized:.2f}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Realized P&L</div>
                    <div class="kpi-value {'positive' if realized >= 0 else 'negative'}">${realized:.2f}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Open Positions</div>
                    <div class="kpi-value">{open_count}</div>
                </div>
            </div>
            
            <div class="section">
                <h2>Open Positions</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Qty</th>
                            <th>Avg Price</th>
                            <th>Last Price</th>
                            <th>Unrealized P&L</th>
                            <th>Return %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {pos_rows}
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2>Recent Fills</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Ticker</th>
                            <th>Side</th>
                            <th>Qty</th>
                            <th>Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {fill_rows}
                    </tbody>
                </table>
            </div>
            
            <div class="timestamp">
                Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
        
        <button class="refresh-btn" onclick="refresh()">🔄</button>
        
        <script>
            function refresh() {{
                const btn = document.querySelector('.refresh-btn');
                btn.classList.add('loading');
                setTimeout(() => {{
                    location.reload();
                }}, 1000);
            }}
            
            // Auto-refresh every 60 seconds
            setInterval(() => {{
                fetch(window.location.href)
                    .then(r => r.text())
                    .then(html => {{
                        const parser = new DOMParser();
                        const newDoc = parser.parseFromString(html, 'text/html');
                        document.body.innerHTML = newDoc.body.innerHTML;
                    }})
                    .catch(e => console.log('Auto-refresh failed:', e));
            }}, 60000);
        </script>
    </body>
    </html>
    """
    
    return html


def main():
    ap = argparse.ArgumentParser(description="Generate paper broker dashboard")
    ap.add_argument("--state-dir", required=True, help="State directory")
    ap.add_argument("--out", required=True, help="Output HTML file")
    
    args = ap.parse_args()
    
    # Read state
    state, positions, fills, ledger = read_state(args.state_dir)
    
    # Generate HTML
    html = generate_html(state, positions, fills, ledger)
    
    # Write
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(html)
    
    print(f"[OK] Dashboard generated: {args.out}")


if __name__ == "__main__":
    main()
