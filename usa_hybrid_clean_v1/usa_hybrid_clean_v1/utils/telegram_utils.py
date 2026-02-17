import os, json, time, requests
from datetime import datetime


def load_env_file(path: str = ".env") -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ[k.strip()] = v.strip()
        return True
    except Exception:
        return False


def env(name: str, default=None):
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def send_telegram(text: str, chat_id: str | None = None):
    # Best-effort: load .env if not already loaded (silent failure is fine)
    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        load_env_file(".env")

    token = env("TELEGRAM_BOT_TOKEN")
    chat = chat_id or env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat, "text": text, "parse_mode": "HTML"})
    r.raise_for_status()
    return r.json()


def format_money(v) -> str:
    try:
        x = float(v)
        return f"${x:,.2f}"
    except Exception:
        return "$0.00"


def throttle_keeper(cache_path: str = ".tg_throttle.json"):
    """
    Returns a guard(key, cool_sec=30) -> bool function.
    On True: it's allowed and recorded; On False: within cooldown (skip).
    """
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f) or {}
        except Exception:
            cache = {}

    def save():
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception:
            pass

    def guard(key: str, cool_sec: int = 30) -> bool:
        now = time.time()
        last = float(cache.get(key, 0))
        if now - last < max(0, int(cool_sec)):
            return False
        cache[key] = now
        save()
        return True

    return guard
