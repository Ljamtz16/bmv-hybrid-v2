# scripts/debug_check_merge_keys.py
import argparse, pandas as pd
from pathlib import Path

KEYS = ["ticker","side","entry_date","tp","sl"]

def norm(df):
    df = df.copy()
    # Normaliza tipos/formatos
    if "entry_date" in df.columns:
        df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
        # quita tz si la hay
        try:
            df["entry_date"] = df["entry_date"].dt.tz_localize(None)
        except Exception:
            pass
    for c in ["ticker","side"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.upper().str.strip()
    for c in ["tp","sl"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(4)  # redondeo para evitar diferencias de flotantes
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    args = ap.parse_args()

    base = Path("reports/forecast") / args.month / "validation"
    trades_path = base / "validation_trades_auto.csv"
    join_path   = base / "validation_join_auto.csv"
    fvr_path    = base / "forecast_vs_real.csv"

    if trades_path.exists():
        L = pd.read_csv(trades_path)
    elif join_path.exists():
        L = pd.read_csv(join_path)
    else:
        print(f"❌ No encontré validation_trades_auto.csv ni validation_join_auto.csv en {base}")
        return
    if not fvr_path.exists():
        print(f"❌ No encontré forecast_vs_real.csv en {base}")
        return

    R = pd.read_csv(fvr_path)

    L = norm(L)
    R = norm(R)

    # Columnas presentes
    print("Cols L (trades):", list(L.columns))
    print("Cols R (fvr):   ", list(R.columns))

    # Faltantes respecto a KEYS
    miss_L = [k for k in KEYS if k not in L.columns]
    miss_R = [k for k in KEYS if k not in R.columns]
    if miss_L or miss_R:
        print("❌ Faltan llaves:", {"L_missing": miss_L, "R_missing": miss_R})
        return

    # Muestra valores únicos raros
    for c in ["ticker","side"]:
        print(f"\nValores únicos {c} - L:", sorted(L[c].dropna().unique())[:10])
        print(f"Valores únicos {c} - R:", sorted(R[c].dropna().unique())[:10])

    # Revisa intersección por columnas clave
    # 1) ticker-side
    ts_L = set(L[["ticker","side"]].drop_duplicates().apply(tuple, axis=1))
    ts_R = set(R[["ticker","side"]].drop_duplicates().apply(tuple, axis=1))
    print("\nIntersección ticker/side:", len(ts_L & ts_R), "de", len(ts_L), "y", len(ts_R))

    # 2) entry_date (por día sin hora, para ver si hay desfase horario)
    if "entry_date" in L.columns and "entry_date" in R.columns:
        L["entry_day"] = L["entry_date"].dt.date
        R["entry_day"] = R["entry_date"].dt.date
        days_L = set(L["entry_day"].dropna().unique())
        days_R = set(R["entry_day"].dropna().unique())
        print("Intersección días:", len(days_L & days_R), "de", len(days_L), "y", len(days_R))

        # 3) delta de horas (muestra algunas diferencias)
        sample = L.merge(R, on=["ticker","side","entry_day"], suffixes=("_L","_R"))
        if not sample.empty:
            sample["delta_hours"] = (sample["entry_date_L"] - sample["entry_date_R"]).dt.total_seconds() / 3600.0
            print("\nEjemplos delta_hours (head):")
            print(sample[["ticker","side","entry_date_L","entry_date_R","delta_hours"]].head(10).to_string(index=False))

    # 4) TP/SL diferencias
    #    Redondeamos a 4 decimales; muestra filas que no coinciden
    merge_ts = L.merge(R, on=["ticker","side","entry_date"], suffixes=("_L","_R"))
    if merge_ts.empty:
        print("\nMerge por ticker/side/entry_date es vacío (probable desfase horario).")
    else:
        eq_tp = (merge_ts["tp_L"].round(4) == merge_ts["tp_R"].round(4))
        eq_sl = (merge_ts["sl_L"].round(4) == merge_ts["sl_R"].round(4))
        print(f"\nCoincidencia TP exacta (redondeada): {eq_tp.mean():.1%} | SL: {eq_sl.mean():.1%}")
        if (~eq_tp).any() or (~eq_sl).any():
            print("Ejemplos no coincidentes (head):")
            bad = merge_ts.loc[(~eq_tp) | (~eq_sl), ["ticker","side","entry_date","tp_L","tp_R","sl_L","sl_R"]].head(10)
            print(bad.to_string(index=False))

if __name__ == "__main__":
    main()
