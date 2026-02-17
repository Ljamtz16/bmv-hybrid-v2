"""
sync_plan_to_bitacora.py
Sincroniza posiciones del trade_plan.csv a la bitácora Excel H3_BITACORA_PREDICCIONES.xlsx
"""
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

BITACORA_PATH = Path("reports/H3_BITACORA_PREDICCIONES.xlsx")
TRADE_PLAN_PATH = Path("val/trade_plan.csv")

def main():
    if not TRADE_PLAN_PATH.exists():
        print(f"[ERROR] No existe {TRADE_PLAN_PATH}")
        sys.exit(1)
    
    if not BITACORA_PATH.exists():
        print(f"[ERROR] No existe {BITACORA_PATH}")
        sys.exit(1)
    
    # Leer trade plan
    plan = pd.read_csv(TRADE_PLAN_PATH)
    print(f"[INFO] Trade plan: {len(plan)} posiciones")
    
    # Leer bitácora
    bitacora = pd.read_excel(BITACORA_PATH, sheet_name="Predicciones")
    print(f"[INFO] Bitácora actual: {len(bitacora)} filas")
    
    # Preparar nuevas filas para bitácora
    nuevas = []
    for _, row in plan.iterrows():
        nueva_fila = {
            "Ticker": row["ticker"],
            "Side": row.get("side", "BUY").upper(),
            "Entry Price": row["entry"],
            "TP Price": row["tp_price"],
            "SL Price": row["sl_price"],
            "Cantidad": int(row["qty"]),
            "Prob Win": row["prob_win"],
            "Status": "ACTIVO",
            "Fecha Señal": datetime.now().strftime("%Y-%m-%d"),
            "Precio Actual": row["entry"],  # Inicialmente igual al entry
            "TP Hit": 0,
            "SL Hit": 0,
            "Progreso a TP %": 0.0,
            "Días Transcurridos": 0,
            "Last Update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Retorno Esperado": row["y_hat"],
            "Horizon Days": row.get("horizon_days", 3),
            "Policy": row.get("policy", "N/A"),
        }
        nuevas.append(nueva_fila)
    
    # Verificar si ya existen (deduplicar por ticker activo)
    tickers_activos = set(bitacora[bitacora["Status"] == "ACTIVO"]["Ticker"]) if "Status" in bitacora.columns else set()
    nuevas_filtradas = [n for n in nuevas if n["Ticker"] not in tickers_activos]
    
    if not nuevas_filtradas:
        print("[INFO] Todas las posiciones ya están en bitácora como ACTIVO")
        return
    
    print(f"[INFO] Agregando {len(nuevas_filtradas)} posiciones nuevas")
    
    # Agregar al DataFrame
    df_nuevas = pd.DataFrame(nuevas_filtradas)
    bitacora_actualizada = pd.concat([bitacora, df_nuevas], ignore_index=True)
    
    # Guardar (backup primero)
    backup_path = BITACORA_PATH.parent / f"{BITACORA_PATH.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    bitacora.to_excel(backup_path, sheet_name="Predicciones", index=False)
    print(f"[BACKUP] {backup_path}")
    
    # Guardar actualizada
    bitacora_actualizada.to_excel(BITACORA_PATH, sheet_name="Predicciones", index=False)
    print(f"[OK] Bitácora actualizada: {len(bitacora_actualizada)} filas totales")
    
    # Mostrar resumen
    print("\n=== POSICIONES AGREGADAS ===")
    for n in nuevas_filtradas:
        print(f"{n['Ticker']}: Entry ${n['Entry Price']:.2f} → TP ${n['TP Price']:.2f} (prob {n['Prob Win']:.1%})")

if __name__ == "__main__":
    main()
