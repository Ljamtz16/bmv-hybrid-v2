# scripts/06_dynamic_buy_gate_eval.py
import pandas as pd
import json
from pathlib import Path

# --- parámetros ---
REPORTS = Path("reports")
MODELS = Path("models")
REPORTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)

# === Lógica previa que ya tenías (simulación + resultados) ===
# Supongamos que al final produces un DataFrame "df" con columnas:
# ticker | trades | win_rate | expect | buy_enabled

# (ejemplo simulado para ilustrar)
df = pd.DataFrame([
    {"ticker": "ALSEA.MX", "trades": 20, "win_rate": 0.60, "expect": 0.9, "buy_enabled": True},
    {"ticker": "GFNORTEO.MX", "trades": 12, "win_rate": 0.30, "expect": -0.5, "buy_enabled": False},
    {"ticker": "OMAB.MX", "trades": 8, "win_rate": 0.75, "expect": 1.2, "buy_enabled": True},
])

# === Guardar CSV completo ===
csv_path = REPORTS / "buy_gate_prev_window.csv"
df.to_csv(csv_path, index=False, encoding="utf-8")
print(f"✅ Reporte detallado guardado en {csv_path}")

# === Guardar JSON compacto ===
json_path = MODELS / "buy_gate.json"
buy_dict = {row["ticker"]: bool(row["buy_enabled"]) for _, row in df.iterrows()}

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(buy_dict, f, ensure_ascii=False, indent=2)

print(f"✅ JSON compacto guardado en {json_path}")
