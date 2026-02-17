# dashboard_api.py
import subprocess
import os
import sys
import json
import time
import socket
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, List, Dict, Any

from flask import Flask, request, jsonify
import io
import csv
import threading
import traceback

try:
    # Allow requests from the local HTML file (file:// origin)
    from flask_cors import CORS  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CORS = None  # fallback if not installed

app = Flask(__name__)
if CORS is not None:
    CORS(app, resources={r"/api/*": {"origins": "*"}})

# Paths
REPO_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
OUTPUTS_DIR = REPO_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = OUTPUTS_DIR / "monitor_state.json"
PIPELINE_STATE_FILE = OUTPUTS_DIR / "pipeline_state.json"
PIPELINE_HISTORY_FILE = OUTPUTS_DIR / "pipeline_history.json"
FORWARD_HISTORY_FILE = OUTPUTS_DIR / "forward_pipeline_history.json"
CALENDAR_DIR = REPO_ROOT / "data" / "calendar"


def _python_exe() -> str:
    """Return current Python executable path."""
    return sys.executable


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    """Read CSV into list of dicts with robust encoding fallback.

    Tries encodings: utf-8, utf-8-sig, cp1252, latin-1.
    """
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
    data = path.read_bytes()
    last_err: Optional[Exception] = None
    for enc in encodings:
        try:
            text = data.decode(enc)
            reader = csv.DictReader(io.StringIO(text))
            return list(reader)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    # If all fail, raise last error
    raise RuntimeError(str(last_err) if last_err else "Unknown decode error")


def _run_powershell(args: List[str]) -> subprocess.CompletedProcess:
    """Run PowerShell script with -File and provided args list.

    The first element in args must be the .ps1 path, followed by script arguments.
    """
    ps_cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    env = os.environ.copy()
    # Force UTF-8 for any Python children launched by PowerShell
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Prefer UTF-8 codepage for PowerShell session (best-effort)
    env.setdefault("WSLENV", "")  # no-op, placeholder if needed
    return subprocess.run(
        ps_cmd + args,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )


def _run_python_script(script_path: Path, extra_args: Optional[List[str]] = None) -> subprocess.CompletedProcess:
    """Ejecuta un script Python usando el mismo intérprete.

    Parameters
    ----------
    script_path: Path al archivo .py
    extra_args: argumentos adicionales (lista de strings) opcional
    """
    if not script_path.exists():
        return subprocess.CompletedProcess(args=[str(script_path)], returncode=2, stdout="", stderr="Script no encontrado")
    cmd = [_python_exe(), str(script_path)] + (extra_args or [])
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )


# -----------------------
# Calendar helpers
# -----------------------

def _ny_today() -> date:
    """Return today's date in America/New_York (approx by EST/EDT offset via UTC-5/UTC-4 heuristics).
    We rely on local time; for precision consider zoneinfo throughout the stack.
    """
    try:
        from zoneinfo import ZoneInfo  # py>=3.9
        return datetime.now(tz=ZoneInfo("America/New_York")).date()
    except Exception:
        # Fallback: local date
        return datetime.now().date()


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


def _load_holidays(year: int) -> Dict[str, str]:
    """Load NYSE holidays map {YYYY-MM-DD: name}. Supports either list of dates or list of {date,name}."""
    path = CALENDAR_DIR / f"nyse_holidays_{year}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        holidays = data.get("holidays", [])
        out: Dict[str, str] = {}
        for item in holidays:
            if isinstance(item, str):
                out[item] = "Holiday"
            elif isinstance(item, dict):
                dt = item.get("date")
                nm = item.get("name") or "Holiday"
                if dt:
                    out[str(dt)] = str(nm)
        return out
    except Exception:
        return {}


def _load_events_for_year(year: int) -> List[Dict[str, Any]]:
    """Load events CSV for given year. Returns list of dict rows."""
    path = CALENDAR_DIR / f"events_{year}.csv"
    if not path.exists():
        return []
    try:
        rows = _read_csv_rows(path)
        # Normalize keys and values
        norm = []
        for r in rows:
            norm.append({
                "date": (r.get("date") or r.get("Date") or "").strip(),
                "time_et": (r.get("time_et") or r.get("Time_ET") or "").strip(),
                "ticker": (r.get("ticker") or r.get("Ticker") or "").strip(),
                "type": (r.get("type") or r.get("Type") or "").strip().lower(),
                "importance": (r.get("importance") or r.get("Importance") or "").strip().lower(),
                "description": (r.get("description") or r.get("Description") or "").strip(),
            })
        return norm
    except Exception:
        return []


def _events_for_date(d: date, all_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ds = d.isoformat()
    return [e for e in all_events if (e.get("date") or "").strip() == ds]


def _risk_level(events: List[Dict[str, Any]]) -> str:
    has_high = any((e.get("importance") == "high") for e in events)
    if has_high:
        return "high"
    has_med = any((e.get("importance") == "medium") for e in events)
    if has_med:
        return "medium"
    return "low"


# -----------------------
# Pipeline state helpers
# -----------------------

def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _load_pipeline_state() -> dict:
    if PIPELINE_STATE_FILE.exists():
        try:
            return json.loads(PIPELINE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {
        "running": False,
        "started_at": None,
        "finished_at": None,
        "last_status": None,
        "last_returncode": None,
        "last_message": None,
    }


def _save_pipeline_state(state: dict) -> None:
    try:
        PIPELINE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PIPELINE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] No se pudo guardar pipeline_state.json: {e}")


def _append_pipeline_history(entry: dict) -> None:
    """Append a pipeline execution entry to history file, trimming to last 200 entries."""
    try:
        PIPELINE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if PIPELINE_HISTORY_FILE.exists():
            try:
                data = json.loads(PIPELINE_HISTORY_FILE.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        else:
            data = []
        data.append(entry)
        # Trim to last 200
        if len(data) > 200:
            data = data[-200:]
        PIPELINE_HISTORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] No se pudo actualizar pipeline_history.json: {e}")


def _append_forward_history(entry: dict) -> None:
    """Append an execution entry for the forward-looking H3 pipeline (run_daily_h3_forward.ps1)."""
    try:
        FORWARD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if FORWARD_HISTORY_FILE.exists():
            try:
                data = json.loads(FORWARD_HISTORY_FILE.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        else:
            data = []
        data.append(entry)
        if len(data) > 200:
            data = data[-200:]
        FORWARD_HISTORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] No se pudo actualizar forward_pipeline_history.json: {e}")


def _read_forecast_tth() -> Optional[dict]:
    """Safely read the latest TTH forecast CSV and derive summary stats.

    Returns dict with 'date', 'n_signals', 'top', 'stats' or None if file missing.
    """
    # Find latest month directory (assumes reports/forecast/YYYY-MM)
    forecast_root = REPO_ROOT / "reports" / "forecast"
    if not forecast_root.exists():
        return None
    # Pick latest month folder lexicographically
    month_dirs = sorted([d for d in forecast_root.iterdir() if d.is_dir()])
    if not month_dirs:
        return None
    latest_dir = month_dirs[-1]
    tth_file = latest_dir / "forecast_with_patterns_tth.csv"
    if not tth_file.exists():
        return None
    try:
        import pandas as pd  # type: ignore
        df = pd.read_csv(tth_file)
        if "date" not in df.columns:
            return None
        latest_date = df["date"].max()
        slice_df = df[df["date"] == latest_date].copy()
        n = len(slice_df)
        # Use available columns (prob_win or prob_win_cal)
        prob_col = "prob_win_cal" if "prob_win_cal" in slice_df.columns else ("prob_win" if "prob_win" in slice_df.columns else None)
        etth_col = "etth_first_event" if "etth_first_event" in slice_df.columns else None
        ptp_col = "p_tp_before_sl" if "p_tp_before_sl" in slice_df.columns else None
        cols_for_top = [c for c in [prob_col, etth_col, ptp_col] if c]
        top = []
        if prob_col:
            slice_df = slice_df.sort_values(prob_col, ascending=False)
            for _, row in slice_df.head(10).iterrows():
                top.append({
                    "ticker": row.get("ticker"),
                    "prob_win": row.get(prob_col),
                    "etth": row.get(etth_col),
                    "p_tp_before_sl": row.get(ptp_col),
                })
        stats = {}
        if prob_col:
            stats["prob_win_mean"] = float(slice_df[prob_col].mean())
            stats["prob_win_max"] = float(slice_df[prob_col].max())
        if etth_col:
            stats["etth_mean"] = float(slice_df[etth_col].mean())
        if ptp_col:
            stats["p_tp_before_sl_mean"] = float(slice_df[ptp_col].mean())
        return {"date": str(latest_date), "n_signals": n, "top": top, "stats": stats, "month_dir": str(latest_dir)}
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] Error leyendo forecast_with_patterns_tth.csv: {e}")
        return None


def _write_forward_report(summary: dict, reason_empty_plan: Optional[str]) -> Optional[Path]:
    """Persist a markdown summary for the forward-looking run (next day planning)."""
    try:
        month_dir = Path(summary.get("month_dir", "")) if summary else None
        if not month_dir or not month_dir.exists():
            return None
        # Target date is the next trading day (approx: next calendar day, may be weekend)
        today = _ny_today()
        target = today + timedelta(days=1)
        md_path = month_dir / f"forward_summary_{target.isoformat()}.md"
        lines = [
            f"# Resumen Forward-Looking H3 - {target.isoformat()}",
            "", f"Generado: {datetime.utcnow().isoformat(timespec='seconds')}Z", "",
        ]
        if summary:
            lines.append(f"Fecha datos base (último close): {summary['date']}")
            lines.append(f"Señales T-1: {summary['n_signals']}")
            stats = summary.get("stats", {})
            if stats:
                lines.append("## Estadísticas agregadas")
                for k, v in stats.items():
                    lines.append(f"- {k}: {v:.4f}")
            top = summary.get("top", [])
            if top:
                lines.append("\n## Top señales (hasta 10)")
                for i, t in enumerate(top, 1):
                    lines.append(
                        f"{i}. {t['ticker']} | prob_win={t.get('prob_win'):.3f} | p_tp_before_sl={t.get('p_tp_before_sl'):.3f} | etth={t.get('etth'):.2f}"
                    )
        if reason_empty_plan:
            lines.append("\n## Plan vacío")
            lines.append(f"Motivo: {reason_empty_plan}")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return md_path
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] No se pudo escribir forward summary markdown: {e}")
        return None


# -----------------------
# Status
# -----------------------

def _read_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_state(data: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _pid_is_alive(pid: int) -> bool:
    try:
        import psutil  # type: ignore
    except Exception:
        # Fallback simple: try Windows tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _pid_looks_like_monitor(pid: int) -> bool:
    try:
        import psutil  # type: ignore
        p = psutil.Process(pid)
        cmdline = " ".join(p.cmdline()).lower()
        return "monitor_intraday.py" in cmdline
    except Exception:
        # If psutil not available or fails, assume alive pid is enough
        return True


@app.get("/api/status")
def api_status():
    """Return health info and real monitor state using PID bookkeeping."""
    health_file = OUTPUTS_DIR / "monitor_health.json"
    health = None
    if health_file.exists():
        try:
            health = json.loads(health_file.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            health = {"error": f"Error leyendo monitor_health.json: {e}"}

    state = _read_state()
    pid = state.get("pid")
    interval = state.get("interval_seconds")
    running = False
    if isinstance(pid, int) and _pid_is_alive(pid) and _pid_looks_like_monitor(pid):
        running = True
    else:
        # If dead but state file exists, clear it softly
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
            except Exception:
                pass
        state = {}
        pid = None
        interval = None

    monitor_info = {
        "running": running,
        "interval_seconds": interval,
        "pid": pid,
        "started_at": state.get("started_at"),
    }

    return jsonify({"monitor": monitor_info, "health": health})


# -----------------------
# Meta routes (diagnóstico)
# -----------------------

@app.get("/api/meta/routes")
def api_meta_routes():
    """Devuelve listado de rutas registradas para diagnóstico."""
    routes = []
    for r in app.url_map.iter_rules():
        routes.append({
            "endpoint": r.endpoint,
            "rule": str(r),
            "methods": sorted(m for m in r.methods if m not in {"HEAD", "OPTIONS"})
        })
    return jsonify({"ok": True, "routes": routes})


@app.get("/api/meta/port")
def api_meta_port():
    """Devuelve el puerto activo leído desde outputs/api_port.json (si existe)."""
    port_file = OUTPUTS_DIR / "api_port.json"
    if not port_file.exists():
        return jsonify({"ok": False, "error": "api_port.json no existe"}), 404
    try:
        data = json.loads(port_file.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "port": data.get("port"), "generated_at": data.get("generated_at")})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"error leyendo api_port.json: {e}"}), 500


# -----------------------
# Monitor start/stop (phase 1: simple)
# -----------------------

@app.post("/api/monitor/start")
def api_monitor_start():
    data = request.get_json(silent=True) or {}
    interval = int(data.get("interval_seconds", 300))

    script = SCRIPTS_DIR / "monitor_intraday.py"
    if not script.exists():
        return jsonify({"ok": False, "error": "monitor_intraday.py no encontrado"}), 500

    cmd = [
        _python_exe(),
        str(script),
        "--loop",
        "--interval-seconds",
        str(interval),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        state = {
            "pid": proc.pid,
            "interval_seconds": interval,
            "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        _write_state(state)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "message": f"Monitor iniciado (intervalo={interval} s)"})


@app.post("/api/monitor/stop")
def api_monitor_stop():
    # Prefer stopping by saved PID
    state = _read_state()
    pid = state.get("pid")
    stopped_by_pid = False
    stdout_text = ""
    stderr_text = ""
    if isinstance(pid, int) and _pid_is_alive(pid):
        try:
            import psutil  # type: ignore
            try:
                p = psutil.Process(pid)
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p = psutil.Process(pid)
                p.kill()
            stopped_by_pid = True
        except Exception:
            # Fallback to Stop-Process
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Stop-Process -Id {pid} -Force",
            ]
            result = subprocess.run(
                ps_cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )
            stopped_by_pid = result.returncode == 0
            stdout_text = result.stdout
            stderr_text = result.stderr

    if not stopped_by_pid:
        # Broad fallback: kill by pattern
        ps_script = r"""
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*monitor_intraday.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        ok = result.returncode == 0
        stdout_text += result.stdout
        stderr_text += result.stderr
    else:
        ok = True

    # Clear state
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except Exception:
        pass

    return jsonify(
        {
            "ok": ok,
            "message": "Monitor detenido",
            "stdout": stdout_text,
            "stderr": stderr_text,
        }
    )


# -----------------------
# Workspace soft clean
# -----------------------

@app.post("/api/clean/soft")
def api_clean_soft():
    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", False))

    ps_script = SCRIPTS_DIR / "clean_workspace.ps1"
    if not ps_script.exists():
        return jsonify({"ok": False, "error": "clean_workspace.ps1 no encontrado"}), 500

    args = [str(ps_script), "-Mode", "Soft", "-Yes"]
    if dry_run:
        args.append("-DryRun")

    result = _run_powershell(args)

    return jsonify(
        {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "dry_run": dry_run,
        }
    )


# -----------------------
# Pipeline endpoints
# -----------------------

@app.route("/api/pipeline/status", methods=["GET"])
def api_pipeline_status():
    state = _load_pipeline_state()
    return jsonify({"ok": True, "pipeline": state})


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    state = _load_pipeline_state()
    if state.get("running"):
        msg = "Ya hay un pipeline en ejecución; espera a que termine."
        return jsonify({"ok": False, "error": msg, "pipeline": state}), 409

    ps_script = SCRIPTS_DIR / "run_daily_pipeline.ps1"
    if not ps_script.exists():
        msg = "run_daily_pipeline.ps1 no encontrado"
        return jsonify({"ok": False, "error": msg}), 500

    state.update(
        {
            "running": True,
            "started_at": _utc_now_iso(),
            "finished_at": None,
            "last_status": None,
            "last_returncode": None,
            "last_message": "Pipeline en ejecución",
        }
    )
    _save_pipeline_state(state)

    result = _run_powershell([str(ps_script)])

    ok = result.returncode == 0
    last_status = "OK" if ok else "ERROR"
    last_message = "Pipeline finalizado correctamente" if ok else "Pipeline terminó con errores"

    state.update(
        {
            "running": False,
            "finished_at": _utc_now_iso(),
            "last_status": last_status,
            "last_returncode": result.returncode,
            "last_message": last_message,
        }
    )
    _save_pipeline_state(state)

    # Historial
    started_at = state.get("started_at")
    finished_at = state.get("finished_at")
    duration_seconds = None
    try:
        if started_at and finished_at:
            t0 = datetime.fromisoformat(started_at.replace("Z", ""))
            t1 = datetime.fromisoformat(finished_at.replace("Z", ""))
            duration_seconds = (t1 - t0).total_seconds()
    except Exception:
        duration_seconds = None
    history_entry = {
        "started_at": started_at,
        "finished_at": finished_at,
        "status": last_status,
        "returncode": result.returncode,
        "message": last_message,
        "duration_seconds": duration_seconds,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
    }
    _append_pipeline_history(history_entry)

    return jsonify(
        {
            "ok": ok,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "pipeline": state,
        }
    )


@app.route("/api/pipeline/intraday", methods=["POST"])
def api_pipeline_intraday():
    """Lanza la sesión intradía en background (no altera pipeline_state)."""
    ps_script = SCRIPTS_DIR / "run_intraday_session.ps1"
    if not ps_script.exists():
        return jsonify({"ok": False, "error": "run_intraday_session.ps1 no encontrado"}), 500
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"No se pudo lanzar sesión intradía: {e}"}), 500
    return jsonify({"ok": True, "message": "Sesión intradía lanzada en background"})


@app.route("/api/pipeline/history", methods=["GET"])
def api_pipeline_history():
    """Return the pipeline execution history list (chronological oldest->newest)."""
    if PIPELINE_HISTORY_FILE.exists():
        try:
            data = json.loads(PIPELINE_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception as e:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"Error leyendo historial: {e}"}), 500
    else:
        data = []
    # Return also reversed (newest first) for convenience
    return jsonify({"ok": True, "history": data, "history_desc": list(reversed(data))})


@app.route("/api/pipeline/forward/history", methods=["GET"])
def api_forward_history():
    if FORWARD_HISTORY_FILE.exists():
        try:
            data = json.loads(FORWARD_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception as e:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"Error leyendo historial forward: {e}"}), 500
    else:
        data = []
    return jsonify({"ok": True, "history": data, "history_desc": list(reversed(data))})


@app.route("/api/pipeline/run_forward", methods=["POST"])
def api_pipeline_run_forward():
    """Ejecuta el pipeline forward-looking (run_daily_h3_forward.ps1) y genera reporte de señales T-1.

    Body JSON opcional:
    {
      "send_telegram": true,
      "recent_days": 3,
      "max_open": 3,
      "capital": 1000,
      "relaxed": false
    }
    """
    data = request.get_json(silent=True) or {}
    send_telegram = bool(data.get("send_telegram", False))
    recent_days = int(data.get("recent_days", 3))
    max_open = int(data.get("max_open", 3))
    capital = float(data.get("capital", 1000.0))
    relaxed = bool(data.get("relaxed", False))
    run_daily_first = bool(data.get("run_daily_first", False))
    allow_stale = bool(data.get("allow_stale", True))  # Default True for weekend runs

    ps_script = REPO_ROOT / "run_daily_h3_forward.ps1"
    if not ps_script.exists():
        return jsonify({"ok": False, "error": "run_daily_h3_forward.ps1 no encontrado"}), 500

    args = [str(ps_script), "-RecentDays", str(recent_days), "-MaxOpen", str(max_open), "-Capital", str(int(capital))]
    if send_telegram:
        args.append("-SendTelegram")
    if relaxed:
        # Pass a flag if script supports; otherwise ignored
        args.append("-RelaxedMode")

    daily_step = None
    if run_daily_first:
        daily_script = SCRIPTS_DIR / "run_daily_pipeline.ps1"
        if daily_script.exists():
            daily_started = _utc_now_iso()
            daily_args = [str(daily_script)]
            if allow_stale:
                daily_args.append("-AllowStale")
            daily_result = _run_powershell(daily_args)
            daily_finished = _utc_now_iso()
            daily_ok = daily_result.returncode == 0
            # Duración
            daily_duration = None
            try:
                t0 = datetime.fromisoformat(daily_started.replace("Z", ""))
                t1 = datetime.fromisoformat(daily_finished.replace("Z", ""))
                daily_duration = (t1 - t0).total_seconds()
            except Exception:
                pass
            daily_step = {
                "name": "daily_pipeline",
                "started_at": daily_started,
                "finished_at": daily_finished,
                "ok": daily_ok,
                "returncode": daily_result.returncode,
                "duration_seconds": daily_duration,
                "stdout_tail": (daily_result.stdout or "")[-2000:],
                "stderr_tail": (daily_result.stderr or "")[-2000:],
            }
            # Registrar en historial general si se desea (reutilizamos estructura)
            hist_entry = {
                "started_at": daily_started,
                "finished_at": daily_finished,
                "status": "OK" if daily_ok else "ERROR",
                "returncode": daily_result.returncode,
                "message": "Pipeline diario (parte de forward_all)",
                "duration_seconds": daily_duration,
                "stdout_tail": (daily_result.stdout or "")[-1200:],
                "stderr_tail": (daily_result.stderr or "")[-1200:],
            }
            _append_pipeline_history(hist_entry)
            # Si falla el daily, decidimos si continuar o abortar forward
            if not daily_ok:
                # Abortar forward y devolver razón
                return jsonify({
                    "ok": False,
                    "error": "Falló la etapa daily, no se ejecuta forward.",
                    "daily": daily_step,
                    "forward_skipped": True,
                }), 500
        else:
            daily_step = {
                "name": "daily_pipeline",
                "ok": False,
                "error": "run_daily_pipeline.ps1 no encontrado",
            }

    started_at = _utc_now_iso()
    result = _run_powershell(args)
    finished_at = _utc_now_iso()
    ok = result.returncode == 0

    # Parse outcome (did we get a trade plan?)
    forecast_summary = _read_forecast_tth()
    plan_path = None
    reason_empty_plan = None
    if forecast_summary:
        # Month dir known, trade_plan_tth.csv expected
        month_dir = Path(forecast_summary["month_dir"])
        plan_candidate = month_dir / "trade_plan_tth.csv"
        if plan_candidate.exists():
            plan_path = str(plan_candidate)
        else:
            reason_empty_plan = "No se generó trade_plan_tth.csv (posibles filtros estrictos o 0 señales válidas)."
    else:
        reason_empty_plan = "No se encontró forecast_with_patterns_tth.csv para resumir señales."

    md_path = None
    if forecast_summary:
        md = _write_forward_report(forecast_summary, reason_empty_plan)
        if md:
            md_path = str(md)

    entry = {
        "started_at": started_at,
        "finished_at": finished_at,
        "returncode": result.returncode,
        "ok": ok,
        "recent_days": recent_days,
        "max_open": max_open,
        "capital": capital,
        "send_telegram": send_telegram,
        "relaxed": relaxed,
        "plan_path": plan_path,
        "summary": forecast_summary,
        "report_md": md_path,
        "reason_empty_plan": reason_empty_plan,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
        "daily_step": daily_step,
        "run_daily_first": run_daily_first,
    }
    _append_forward_history(entry)

    return jsonify({
        "ok": ok,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "plan_path": plan_path,
        "reason_empty_plan": reason_empty_plan,
        "summary": forecast_summary,
        "report_md": md_path,
        "history_entry": entry,
    })


@app.route("/api/pipeline/forward/report", methods=["GET"])
def api_pipeline_forward_report():
    summary = _read_forecast_tth()
    if not summary:
        return jsonify({"ok": False, "error": "No se encontró forecast TTH para generar resumen"}), 404
    # Try to locate trade plan
    month_dir = Path(summary.get("month_dir", ""))
    plan_exists = (month_dir / "trade_plan_tth.csv").exists() if month_dir.exists() else False
    return jsonify({"ok": True, "summary": summary, "plan_exists": plan_exists})


# -----------------------
# Intraday plan buffer refresh
# -----------------------

@app.post("/api/plan/download_intraday")
def api_plan_download_intraday():
    """Ejecuta scripts/download_intraday_for_plan.py para refrescar buffers intradía.

    JSON body opcional:
    {
      "interval": "5m",
      "days": 1,
      "max_workers": 1,
      "skip_recent": false,
      "save_history": false,
      "dry_run": false,
      "plan": "val/trade_plan.csv"
    }
    """
    data = request.get_json(silent=True) or {}
    interval = data.get("interval", "5m")
    days = int(data.get("days", 1))
    max_workers = int(data.get("max_workers", 1))
    skip_recent = bool(data.get("skip_recent", False))
    save_history = bool(data.get("save_history", False))
    dry_run = bool(data.get("dry_run", False))
    plan = data.get("plan", "val/trade_plan.csv")

    script = SCRIPTS_DIR / "download_intraday_for_plan.py"
    if not script.exists():
        return jsonify({"ok": False, "error": "download_intraday_for_plan.py no encontrado"}), 500

    args = ["--plan", plan, "--interval", interval, "--days", str(days), "--max-workers", str(max_workers)]
    if skip_recent:
        args.append("--skip-recent")
    if save_history:
        args.append("--save-history")
    if dry_run:
        args.append("--dry-run")

    started_at = _utc_now_iso()
    result = _run_python_script(script, args)
    finished_at = _utc_now_iso()
    ok = result.returncode == 0

    # Extra: intentar leer métricas generadas
    metrics_path = REPO_ROOT / "outputs" / "intraday_metrics.csv"
    metrics_head = None
    if metrics_path.exists():
        try:
            text = metrics_path.read_text(encoding="utf-8").splitlines()
            metrics_head = text[:25]
        except Exception:
            metrics_head = None

    return jsonify({
        "ok": ok,
        "returncode": result.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_tail": (result.stdout or "")[-3000:],
        "stderr_tail": (result.stderr or "")[-3000:],
        "metrics_head": metrics_head,
        "params": {
            "interval": interval,
            "days": days,
            "max_workers": max_workers,
            "skip_recent": skip_recent,
            "save_history": save_history,
            "dry_run": dry_run,
            "plan": plan,
        },
    })


@app.route("/api/bitacora", methods=["GET"])
def api_bitacora():
    """Return bitacora_intraday.csv data as JSON, or read directly from Excel if CSV is empty."""
    csv_file = OUTPUTS_DIR / "bitacora_intraday.csv"
    
    # Try CSV first (fast path)
    if csv_file.exists():
        try:
            data = _read_csv_rows(csv_file)
            if data:  # If CSV has data, return it
                return jsonify({"ok": True, "data": data, "source": "csv"})
        except Exception:
            pass
    
    # Fallback: try reading directly from Excel (Google Drive or local)
    excel_path_gdrive = Path("G:/Mi unidad/Trading proyecto/H3_BITACORA_PREDICCIONES.xlsx")
    excel_path_local = REPO_ROOT / "reports" / "H3_BITACORA_PREDICCIONES.xlsx"
    
    excel_path = excel_path_gdrive if excel_path_gdrive.exists() else excel_path_local
    
    if excel_path.exists():
        try:
            import pandas as pd
            df = pd.read_excel(excel_path, sheet_name="Predicciones")
            # Filter only active positions (Estado == "ACTIVO")
            if "Estado" in df.columns:
                df = df[df["Estado"] == "ACTIVO"]
            data = df.to_dict(orient="records")
            return jsonify({"ok": True, "data": data, "source": "excel", "path": str(excel_path)})
        except Exception as e:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"Error reading Excel: {str(e)}"}), 500
    
    # No data available
    return jsonify({"ok": True, "data": [], "message": "No hay operaciones registradas. Ejecuta el pipeline H3 para generar señales."})


@app.route("/api/equity", methods=["GET"])
def api_equity():
    """Return equity_curve.csv data as JSON."""
    csv_file = OUTPUTS_DIR / "equity_curve.csv"
    if not csv_file.exists():
        return jsonify({"ok": True, "data": []})
    try:
        data = _read_csv_rows(csv_file)
        return jsonify({"ok": True, "data": data})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/progress/<ticker>", methods=["GET"])
def api_progress(ticker: str):
    """Return progress_series_TICKER.csv data as JSON."""
    csv_file = OUTPUTS_DIR / f"progress_series_{ticker}.csv"
    if not csv_file.exists():
        return jsonify({"ok": True, "data": []})
    try:
        data = _read_csv_rows(csv_file)
        return jsonify({"ok": True, "data": data})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


# -----------------------
# Calendar endpoints
# -----------------------

@app.get("/api/calendar/today")
def api_calendar_today():
    today = _ny_today()
    year = today.year
    holidays = _load_holidays(year)
    all_events = _load_events_for_year(year)

    is_weekend = _is_weekend(today)
    is_holiday = today.isoformat() in holidays
    is_trading_day = not (is_weekend or is_holiday)
    reason = None
    if is_weekend:
        reason = "Weekend"
    elif is_holiday:
        reason = f"Holiday: {holidays.get(today.isoformat())}"

    events = _events_for_date(today, all_events)
    risk = {
        "level": _risk_level(events),
        "reasons": [
            (f"{e.get('time_et')} ET - {e.get('description')}" + (f" [{e.get('ticker')}]" if e.get('ticker') else "")).strip()
            for e in events if e.get("importance") in {"high", "medium"}
        ],
    }

    return jsonify({
        "ok": True,
        "date": today.isoformat(),
        "market": {"is_trading_day": is_trading_day, "reason": reason},
        "risk": risk,
        "events": events,
    })


@app.get("/api/calendar/upcoming")
def api_calendar_upcoming():
    # Next N days (including weekends)
    N = int(request.args.get("days", "5"))
    start = _ny_today() + timedelta(days=1)
    year_set = {start.year, (start + timedelta(days=N)).year}
    # Load events for involved years (in case we cross year boundary)
    all_events = []
    for y in sorted(year_set):
        all_events.extend(_load_events_for_year(y))
    holidays = {}
    for y in sorted(year_set):
        holidays.update(_load_holidays(y))

    days = []
    for i in range(N):
        d = start + timedelta(days=i)
        is_weekend = _is_weekend(d)
        is_holiday = d.isoformat() in holidays
        is_trading_day = not (is_weekend or is_holiday)
        events = _events_for_date(d, all_events)
        reason = None
        if is_weekend:
            reason = "Weekend"
        elif is_holiday:
            reason = f"Holiday: {holidays.get(d.isoformat())}"
        days.append({
            "date": d.isoformat(),
            "is_trading_day": is_trading_day,
            "risk_level": _risk_level(events),
            "events": events,
            "reason": reason,
        })

    return jsonify({"ok": True, "days": days})


if __name__ == "__main__":
    # Modo estricto (usar solo el puerto preferido y abortar si está ocupado)
    preferred = int(os.environ.get("API_PORT", "5001"))
    strict = os.environ.get("STRICT_PORT", "0").lower() in {"1", "true", "yes"}

    def _can_bind(port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
        finally:
            try:
                s.close()
            except Exception:
                pass

    if strict:
        if not _can_bind(preferred):
            print(f"[ERROR] STRICT_PORT activo: puerto {preferred} ocupado. Libéralo o ajusta API_PORT antes de iniciar.")
            print("[HINT] PowerShell para identificar proceso:\n  netstat -ano | findstr :{preferred}\nLuego matar: taskkill /PID <PID> /F")
            sys.exit(1)
        chosen_port = preferred
        print(f"[INFO] STRICT_PORT: iniciando en puerto fijo {chosen_port}.")
    else:
        candidate_ports = [preferred] + [p for p in range(preferred + 1, preferred + 11)]
        chosen_port = None
        for p in candidate_ports:
            if _can_bind(p):
                chosen_port = p
                break
        if chosen_port is None:
            print(f"[ERROR] No se encontró puerto libre desde {preferred} hasta {preferred+10}. Abortando.")
            sys.exit(1)
        if chosen_port != preferred:
            print(f"[WARN] Puerto preferido {preferred} ocupado. Usando puerto alterno {chosen_port}. (Establece STRICT_PORT=1 para exigir el preferido)")
        else:
            print(f"[INFO] Iniciando servidor en puerto {chosen_port}.")

    # Persistir puerto elegido
    try:
        port_file = OUTPUTS_DIR / "api_port.json"
        port_file.write_text(
            json.dumps({"port": chosen_port, "generated_at": datetime.utcnow().isoformat(timespec='seconds') + 'Z'}),
            encoding="utf-8"
        )
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] No se pudo escribir api_port.json: {e}")

    try:
        app.run(host="127.0.0.1", port=chosen_port, debug=False)
    except Exception as e:
        print(f"[ERROR] Fallo al iniciar Flask: {e}")
        sys.exit(1)
