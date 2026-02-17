import os
import json
import time
import shutil
import logging
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    from dotenv import dotenv_values
except ImportError:  # dotenv is optional
    dotenv_values = None  # type: ignore

logger = logging.getLogger(__name__)


def load_runtime_env(env_path: Path) -> Dict[str, str]:
    """Load key=value pairs from runtime.env. Uses python-dotenv if available."""
    env_path = env_path.expanduser().resolve()
    data: Dict[str, str] = {}
    if dotenv_values is not None and env_path.exists():
        data = {k: v for k, v in dotenv_values(str(env_path)).items() if v is not None}
    else:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def ensure_runtime_dirs(base_dir: Path) -> Dict[str, Path]:
    reports = base_dir / "reports"
    state = base_dir / "state"
    logs = base_dir.parent / "logs" if base_dir.parent != base_dir else base_dir / "logs"
    for p in [reports, state, logs]:
        p.mkdir(parents=True, exist_ok=True)
    return {"reports": reports, "state": state, "logs": logs}


def atomic_write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=path.stem)[1])
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def atomic_write_csv(path: Path, headers: List[str], rows: Iterable[Iterable]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=path.stem)
    try:
        with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Optional[Dict]:
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception as exc:
        logger.warning("Failed to read json %s: %s", path, exc)
        return None


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def safe_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.warning("Failed to remove %s: %s", path, exc)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
