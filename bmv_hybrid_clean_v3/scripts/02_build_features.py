# scripts/02_build_features.py
from __future__ import annotations

# --- bootstrap de ruta del proyecto para que 'src' se pueda importar ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------------------

import os
import pandas as pd
from src.config import load_cfg
from src.io.loader import load_daily_map
from src.features.indicators import ensure_atr_14

def pick_raw_1d_dir(data_dir: str | Path) -> Path:
    """
    Devuelve la carpeta donde están los CSV 1D.
    Preferimos <data_dir>/raw/1d; si no existe, probamos <data_dir>/raw.
    """
    data_dir = Path(data_dir)
    cand1 = data_dir / "raw" / "1d"
    cand2 = data_dir / "raw"
    if cand1.exists():
        return cand1
    if cand2.exists():
        return cand2
    raise SystemExit(f"❌ No encuentro datos diarios en {cand1} ni {cand2}. Corre primero 01_download_data.py")

def ensure_atr_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza alias: crea ATR_14 y ATR14 si falta alguno.
    """
    df2 = ensure_atr_14(df)
    if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
        df2["ATR_14"] = df2["ATR14"]
    if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
        df2["ATR14"] = df2["ATR_14"]
    return df2

if __name__ == "__main__":
    # Permite forzar config por variable de entorno CFG (fallback a config/base.yaml)
    cfg_path = os.environ.get("CFG", "config/base.yaml")
    cfg = load_cfg(cfg_path)

    # Directorios
    raw_1d_dir = pick_raw_1d_dir(cfg.data_dir)
    interim_dir = Path(cfg.data_dir) / "interim"
    interim_dir.mkdir(parents=True, exist_ok=True)

    # Aliases opcional (compatibilidad)
    aliases = getattr(cfg, "aliases", None)

    # Cargar diarios
    d1_map = load_daily_map(raw_1d_dir, cfg.tickers, aliases=aliases, debug=False)

    # Generar y guardar features
    saved = 0
    for t, df in d1_map.items():
        if df is None or df.empty:
            print(f"⚠️ {t}: sin datos diarios; se omite.")
            continue
        try:
            # Asegura columnas ATR y alias consistentes
            df_feat = ensure_atr_aliases(df)

            # Guardar: preserva índice como fecha si ya viene indexado
            out = interim_dir / f"{t.replace('.','_')}_1d_features.csv"
            if isinstance(df_feat.index, pd.DatetimeIndex):
                df_feat.to_csv(out, index_label="Date")
            else:
                df_feat.to_csv(out, index=False)

            saved += 1
        except Exception as e:
            print(f"❌ Error procesando {t}: {e}")

    print(f"✅ Features diarias guardadas en {interim_dir}/ (archivos: {saved})")
