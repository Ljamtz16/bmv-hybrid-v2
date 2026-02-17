#!/usr/bin/env python3
"""
Dashboard exclusivo para simulaciones históricas (PROBWIN_55).
Lee outputs de run_phase2_probwin_sim.py.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
import pandas as pd

app = Flask(__name__)

DEFAULT_OUTPUT_DIR = Path("evidence") / "phase2_simulations"


def _resolve_output_dir(custom: str | None) -> Path:
    if custom:
        return Path(custom)
    env_dir = request.args.get("output") if request else None
    if env_dir:
        return Path(env_dir)
    return DEFAULT_OUTPUT_DIR


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_trades(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if "exit_date" in df.columns:
        df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
        df = df.sort_values("exit_date", ascending=False)
    if limit:
        df = df.head(limit)
    return df.to_dict("records")


def _latest_run_dir(base_dir: Path) -> Path | None:
    if not base_dir.exists():
        return None
    run_dirs = [p for p in base_dir.iterdir() if p.is_dir()]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda p: p.stat().st_mtime)


def _resolve_run_dir(base_dir: Path) -> Path | None:
    run_arg = request.args.get("run") if request else None
    if run_arg:
        run_path = base_dir / run_arg
        if run_path.exists():
            return run_path
    return _latest_run_dir(base_dir)


@app.route("/")
def index():
    base_dir = _resolve_output_dir(None)
    run_dir = _resolve_run_dir(base_dir)
    metadata = _read_json(run_dir / "metadata.json") if run_dir else {}
    metrics_swing = _read_json(run_dir / "metrics_swing.json") if run_dir else {}
    metrics_intraday = _read_json(run_dir / "metrics_intraday.json") if run_dir else {}
    metrics_total = _read_json(run_dir / "metrics_total.json") if run_dir else {}
    weekly_total = _read_json(run_dir / "weekly_summary_total.json") if run_dir else {}
    best_week = weekly_total.get("best_week", {}) if weekly_total else {}
    worst_week = weekly_total.get("worst_week", {}) if weekly_total else {}

    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Phase 2 Simulation Dashboard</title>
        <style>
            :root {
                --bg: #0f172a;
                --surface: #111827;
                --card: #1f2937;
                --card-2: #0b1220;
                --text: #e5e7eb;
                --muted: #94a3b8;
                --accent: #38bdf8;
                --good: #10b981;
                --warn: #f59e0b;
                --bad: #ef4444;
                --border: #334155;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: "Inter", "Segoe UI", Arial, sans-serif;
                background: var(--bg);
                color: var(--text);
            }
            .wrap { max-width: 1200px; margin: 0 auto; padding: 28px; }
            .header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
            .title h1 { margin: 0; font-size: 28px; }
            .subtitle { color: var(--muted); margin-top: 6px; }
            .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; background: var(--card); border: 1px solid var(--border); color: var(--muted); font-size: 12px; }
            .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
            .card { background: var(--card); border: 1px solid var(--border); padding: 16px; border-radius: 12px; box-shadow: 0 10px 30px rgba(2, 6, 23, 0.25); }
            .card h2 { margin: 0 0 12px 0; font-size: 16px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
            .metric { font-size: 24px; font-weight: 700; }
            .muted { color: var(--muted); }
            .metric-row { display: flex; flex-direction: column; gap: 4px; }
            .status { font-size: 12px; color: var(--muted); }
            .pill { display: inline-flex; align-items: center; padding: 4px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); background: var(--card-2); }
            .pill.good { color: var(--good); border-color: rgba(16, 185, 129, 0.4); }
            .pill.warn { color: var(--warn); border-color: rgba(245, 158, 11, 0.4); }
            .pill.bad { color: var(--bad); border-color: rgba(239, 68, 68, 0.4); }
            .section { margin-top: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
            th { color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 12px; letter-spacing: 0.04em; }
            .api-links a { color: var(--accent); text-decoration: none; }
            .api-links a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="header">
                <div class="title">
                    <h1>Phase 2 Simulation Dashboard</h1>
                    <div class="subtitle">Run: {{ run_name or 'N/A' }}</div>
                    <div class="subtitle">Generated: {{ generated_at or 'N/A' }}</div>
                </div>
                <div class="badge">{{ now }}</div>
            </div>

            <div class="card">
                <h2>Metadata</h2>
                <div class="grid">
                    <div class="metric-row"><div class="muted">Mode</div><div class="metric">{{ mode }}</div></div>
                    <div class="metric-row"><div class="muted">ProbWin Threshold</div><div class="metric">{{ pw_threshold }}</div></div>
                    <div class="metric-row"><div class="muted">Date Range</div><div class="metric">{{ start_date }} → {{ end_date }}</div></div>
                    <div class="metric-row"><div class="muted">Universe</div><div class="metric">{{ ticker_universe }}</div></div>
                </div>
            </div>

            <div class="grid section">
                <div class="card">
                    <h2>Swing</h2>
                    <div class="metric-row"><span class="muted">Trades</span><span class="metric">{{ metrics_swing.get('n_trades', 0) }}</span></div>
                    <div class="metric-row"><span class="muted">Total P&L</span><span class="metric">${{ '%.2f'|format(metrics_swing.get('total_pnl', 0)) }}</span></div>
                    <div class="metric-row"><span class="muted">Win Rate</span><span class="metric">{{ '%.1f'|format(metrics_swing.get('win_rate', 0) * 100) }}%</span></div>
                    <div class="metric-row"><span class="muted">Profit Factor</span><span class="metric">{{ '%.2f'|format(metrics_swing.get('profit_factor', 0)) }}</span></div>
                </div>

                <div class="card">
                    <h2>Intraday</h2>
                    <div class="metric-row"><span class="muted">Trades</span><span class="metric">{{ metrics_intraday.get('n_trades', 0) }}</span></div>
                    <div class="metric-row"><span class="muted">Total P&L</span><span class="metric">${{ '%.2f'|format(metrics_intraday.get('total_pnl', 0)) }}</span></div>
                    <div class="metric-row"><span class="muted">Win Rate</span><span class="metric">{{ '%.1f'|format(metrics_intraday.get('win_rate', 0) * 100) }}%</span></div>
                    <div class="metric-row"><span class="muted">Profit Factor</span><span class="metric">{{ '%.2f'|format(metrics_intraday.get('profit_factor', 0)) }}</span></div>
                </div>

                <div class="card">
                    <h2>Total</h2>
                    <div class="metric-row"><span class="muted">Trades</span><span class="metric">{{ metrics_total.get('n_trades', 0) }}</span></div>
                    <div class="metric-row"><span class="muted">Total P&L</span><span class="metric">${{ '%.2f'|format(metrics_total.get('total_pnl', 0)) }}</span></div>
                    <div class="metric-row"><span class="muted">Win Rate</span><span class="metric">{{ '%.1f'|format(metrics_total.get('win_rate', 0) * 100) }}%</span></div>
                    <div class="metric-row"><span class="muted">Profit Factor</span><span class="metric">{{ '%.2f'|format(metrics_total.get('profit_factor', 0)) }}</span></div>
                </div>
            </div>

            <div class="card section">
                <h2>Weekly Summary (Total)</h2>
                <div class="grid">
                    <div class="metric-row"><span class="muted">Total Weeks</span><span class="metric">{{ weekly_total.get('total_weeks', 0) }}</span></div>
                    <div class="metric-row"><span class="muted">Positive Weeks</span><span class="metric">{{ weekly_total.get('positive_weeks', 0) }}</span></div>
                    <div class="metric-row"><span class="muted">Avg Weekly P&L</span><span class="metric">${{ '%.2f'|format(weekly_total.get('avg_weekly_pnl', 0)) }}</span></div>
                    <div class="metric-row"><span class="muted">Std Weekly P&L</span><span class="metric">${{ '%.2f'|format(weekly_total.get('std_weekly_pnl', 0)) }}</span></div>
                </div>
            </div>

            <div class="card section">
                <h2>Best vs Worst Week (Total)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Week Start</th>
                            <th>Week End</th>
                            <th>Trades</th>
                            <th>P&L</th>
                            <th>Win Rate</th>
                            <th>PF</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><span class="pill good">Best</span></td>
                            <td>{{ best_week.get('week_start', 'N/A') }}</td>
                            <td>{{ best_week.get('week_end', 'N/A') }}</td>
                            <td>{{ best_week.get('trades', 0) }}</td>
                            <td>${{ '%.2f'|format(best_week.get('pnl', 0)) }}</td>
                            <td>{{ '%.1f'|format(best_week.get('win_rate', 0) * 100) }}%</td>
                            <td>{{ '%.2f'|format(best_week.get('pf', 0)) }}</td>
                        </tr>
                        <tr>
                            <td><span class="pill bad">Worst</span></td>
                            <td>{{ worst_week.get('week_start', 'N/A') }}</td>
                            <td>{{ worst_week.get('week_end', 'N/A') }}</td>
                            <td>{{ worst_week.get('trades', 0) }}</td>
                            <td>${{ '%.2f'|format(worst_week.get('pnl', 0)) }}</td>
                            <td>{{ '%.1f'|format(worst_week.get('win_rate', 0) * 100) }}%</td>
                            <td>{{ '%.2f'|format(worst_week.get('pf', 0)) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="card section api-links">
                <h2>API</h2>
                <ul>
                    <li><a href="/api/summary">/api/summary</a></li>
                    <li><a href="/api/weekly">/api/weekly</a></li>
                    <li><a href="/api/trades?limit=200">/api/trades?limit=200</a></li>
                    <li><a href="/api/trades?limit=200&book=swing">/api/trades?limit=200&book=swing</a></li>
                    <li><a href="/api/trades?limit=200&book=intraday">/api/trades?limit=200&book=intraday</a></li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

    return render_template_string(
        html,
        run_name=run_dir.name if run_dir else None,
        generated_at=metadata.get("generated_at"),
        mode=metadata.get("mode", "N/A"),
        pw_threshold=metadata.get("pw_threshold", "N/A"),
        start_date=metadata.get("start_date", "N/A"),
        end_date=metadata.get("end_date", "N/A"),
        ticker_universe=metadata.get("ticker_universe", "N/A"),
        metrics_swing=metrics_swing,
        metrics_intraday=metrics_intraday,
        metrics_total=metrics_total,
        weekly_total=weekly_total,
        best_week=best_week,
        worst_week=worst_week,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/api/summary")
def api_summary():
    base_dir = _resolve_output_dir(None)
    run_dir = _resolve_run_dir(base_dir)
    if not run_dir:
        return jsonify({"ok": False, "error": "No run directory found"}), 404

    return jsonify({
        "ok": True,
        "run": run_dir.name,
        "metadata": _read_json(run_dir / "metadata.json"),
        "metrics_swing": _read_json(run_dir / "metrics_swing.json"),
        "metrics_intraday": _read_json(run_dir / "metrics_intraday.json"),
        "metrics_total": _read_json(run_dir / "metrics_total.json"),
        "weekly_swing": _read_json(run_dir / "weekly_summary_swing.json"),
        "weekly_intraday": _read_json(run_dir / "weekly_summary_intraday.json"),
        "weekly_total": _read_json(run_dir / "weekly_summary_total.json"),
    })


@app.route("/api/weekly")
def api_weekly():
    base_dir = _resolve_output_dir(None)
    run_dir = _resolve_run_dir(base_dir)
    if not run_dir:
        return jsonify({"ok": False, "error": "No run directory found"}), 404
    return jsonify({
        "ok": True,
        "run": run_dir.name,
        "weekly_swing": _read_json(run_dir / "weekly_summary_swing.json"),
        "weekly_intraday": _read_json(run_dir / "weekly_summary_intraday.json"),
        "weekly_total": _read_json(run_dir / "weekly_summary_total.json"),
    })


@app.route("/api/trades")
def api_trades():
    base_dir = _resolve_output_dir(None)
    run_dir = _resolve_run_dir(base_dir)
    if not run_dir:
        return jsonify({"ok": False, "error": "No run directory found"}), 404
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError:
        limit = 200
    book = request.args.get("book", "total").lower()
    if book == "swing":
        trades_path = run_dir / "trades_swing.csv"
    elif book == "intraday":
        trades_path = run_dir / "trades_intraday.csv"
    else:
        trades_path = run_dir / "trades_total.csv"
    trades = _read_trades(trades_path, limit=limit)
    return jsonify({"ok": True, "run": run_dir.name, "book": book, "count": len(trades), "trades": trades})


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de simulaciones Phase 2")
    parser.add_argument("--output-dir", default=None, help="Base output dir (default: evidence/phase2_simulations)")
    parser.add_argument("--port", type=int, default=8060, help="Port")
    args = parser.parse_args()

    if args.output_dir:
        global DEFAULT_OUTPUT_DIR
        DEFAULT_OUTPUT_DIR = Path(args.output_dir)

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
