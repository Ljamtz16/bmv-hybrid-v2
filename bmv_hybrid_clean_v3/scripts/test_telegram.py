# test_telegram.py
import os, requests, re
from dotenv import load_dotenv, find_dotenv

env_path = find_dotenv(usecwd=True)
loaded = load_dotenv(env_path, override=True)
print("ENV loaded:", loaded, "| path:", env_path or "<none>")

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

print("TOKEN bruto (repr):", repr(TOKEN[:12] + ("…" if len(TOKEN) > 12 else "")))
print("CHAT_ID:", CHAT_ID)

if not TOKEN:
    raise SystemExit("❌ Falta TELEGRAM_BOT_TOKEN")
pat = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
if not pat.match(TOKEN):
    raise SystemExit("❌ Formato de token inválido.")

r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=15)
print("GET getMe ->", r.status_code, r.text[:160])
r.raise_for_status()

msg = "✅ Prueba OK: bot conectado desde Python."
r2 = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                   data={"chat_id": CHAT_ID, "text": msg}, timeout=15)
print("POST sendMessage ->", r2.status_code, r2.text[:200])
r2.raise_for_status()
print("✅ Todo OK.")
