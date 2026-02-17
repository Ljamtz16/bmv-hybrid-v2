"""
Genera y guarda el manifiesto de features esperado por los modelos.
Ejecutar después de entrenar modelos para capturar el orden y nombres correctos.
"""
import json
from pathlib import Path
import pandas as pd

def generate_feature_manifest():
    """
    Lee features_enhanced_binary_targets y genera manifiesto con columnas de training.
    """
    train_path = Path('data/daily/features_enhanced_binary_targets.parquet')
    manifest_path = Path('models/direction/feature_manifest.json')
    
    if not train_path.exists():
        print(f"[ERROR] No existe {train_path}")
        return False
    
    df = pd.read_parquet(train_path)
    
    # Columnas a excluir (igual que en 11_infer_and_gate.py)
    exclude_cols = ['timestamp', 'date', 'ticker', 'target', 'target_binary', 'target_ordinal',
                    'open', 'high', 'low', 'close', 'volume', 'close_fwd', 'ret_fwd', 'thr_up', 'thr_dn',
                    'atr_pct_w', 'k', 'regime', 'prev_close', 'hh_20', 'll_20', 'hh_60', 'll_60',
                    'vol_avg_20', 'is_up', 'dow', 'day_of_month', 'atr_pct_p33', 'atr_pct_p66']
    
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    feature_cols = [c for c in feature_cols if df[c].notna().sum() > len(df) * 0.8]
    feature_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
    
    manifest = {
        "version": "1.0",
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "exclude_cols": list(exclude_cols),
        "generated_at": pd.Timestamp.now().isoformat(),
        "source": str(train_path)
    }
    
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Manifiesto generado: {manifest_path}")
    print(f"     n_features={len(feature_cols)}")
    return True

if __name__ == "__main__":
    generate_feature_manifest()
