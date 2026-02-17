"""
Script: 08_make_targets_adaptive.py
Genera targets ADAPTATIVOS por volatilidad (ATR) y horizonte diario/intraday.
Corrige el cálculo del umbral: ATR% = atr_14d / close.shift(1), winsorizado (1-99%).
Incluye k por régimen y ret_fwd sin leak: close(t+H)/open(t+1)-1.
"""
import sys
import pandas as pd
import numpy as np
import os


def enable_utf8_output():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            import io as _io
            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass


def compute_atr_pct(df: pd.DataFrame) -> pd.Series:
    """ATR como porcentaje del precio (sin leak) usando close.shift(1). Winsoriza 1-99%."""
    atr_pct = (df['atr_14d'] / df['close'].shift(1)).clip(lower=1e-5)
    low, high = atr_pct.quantile([0.01, 0.99])
    atr_pct_w = atr_pct.clip(lower=low, upper=high)
    return atr_pct_w


def map_k_by_regime(regime_series: pd.Series) -> pd.Series:
    """Mapea k por régimen. Defaults razonables si falta el régimen."""
    k_by_regime = {
        'low_vol': 0.8,
        'med_vol': 1.2,
        'high_vol': 1.6,
    }
    return regime_series.map(k_by_regime).fillna(1.2)


def make_intraday_forward_target(df: pd.DataFrame, horizon_bars: int = 12, k_default: float = 1.2) -> pd.DataFrame:
    """
    Target intraday (1-4h) con threshold adaptativo por ATR%.
    horizon_bars: 12=~1h, 24=~2h, 48=~4h en 5m.
    """
    df = df.copy()
    df['close_fwd'] = df['close'].shift(-horizon_bars)
    # Evitar leak: comparar contra open(t+1)
    df['ret_fwd'] = df['close_fwd'] / df['open'].shift(1) - 1
    
    df['atr_pct_w'] = compute_atr_pct(df)
    # Si no hay régimen en intradía todavía, usar k fijo
    df['k'] = k_default
    df['thr_up'] = df['k'] * df['atr_pct_w']
    df['thr_dn'] = -df['k'] * df['atr_pct_w']
    
    # Clasificación ordinal
    conditions = [
        df['ret_fwd'] > df['thr_up'],
        (df['ret_fwd'] > 0) & (df['ret_fwd'] <= df['thr_up']),
        (df['ret_fwd'] <= 0) & (df['ret_fwd'] >= df['thr_dn']),
        df['ret_fwd'] < df['thr_dn']
    ]
    choices = [2, 1, 0, -1]
    df['target_ordinal'] = np.select(conditions, choices, default=np.nan)
    
    # Binario compatible (TP/SL adaptativo)
    df['target_binary'] = np.nan
    df.loc[df['ret_fwd'] >= df['thr_up'], 'target_binary'] = 1
    df.loc[df['ret_fwd'] <= df['thr_dn'], 'target_binary'] = 0
    
    return df


def make_daily_adaptive_target(df: pd.DataFrame, regime_df: pd.DataFrame, n_days: int = 2) -> pd.DataFrame:
    """
    Target diario con threshold adaptativo por ATR% y k por régimen.
    Retorno futuro sin leak: close(t+n)/open(t+1) - 1.
    """
    df = df.copy()
    # Merge de régimen
    regime_df = regime_df.copy()
    regime_df['timestamp'] = pd.to_datetime(regime_df['timestamp'])
    df = df.merge(regime_df[['timestamp', 'ticker', 'regime']], on=['timestamp', 'ticker'], how='left')

    df['close_fwd'] = df['close'].shift(-n_days)
    df['ret_fwd'] = df['close_fwd'] / df['open'].shift(1) - 1

    df['atr_pct_w'] = compute_atr_pct(df)
    df['k'] = map_k_by_regime(df['regime'])
    df['thr_up'] = df['k'] * df['atr_pct_w']
    df['thr_dn'] = -df['k'] * df['atr_pct_w']

    # Ordinal
    conditions = [
        df['ret_fwd'] > df['thr_up'],
        (df['ret_fwd'] > 0) & (df['ret_fwd'] <= df['thr_up']),
        (df['ret_fwd'] <= 0) & (df['ret_fwd'] >= df['thr_dn']),
        df['ret_fwd'] < df['thr_dn']
    ]
    choices = [2, 1, 0, -1]
    df['target_ordinal'] = np.select(conditions, choices, default=np.nan)

    # Binario
    df['target_binary'] = np.nan
    df.loc[df['ret_fwd'] >= df['thr_up'], 'target_binary'] = 1
    df.loc[df['ret_fwd'] <= df['thr_dn'], 'target_binary'] = 0

    return df


def main():
    enable_utf8_output()
    input_path = 'data/daily/features_daily_enhanced.parquet'
    regime_path = 'data/daily/regime_daily.csv'
    output_path = 'data/daily/features_enhanced_adaptive_targets.parquet'

    if not os.path.exists(input_path):
        print(f"[WARN] No existe {input_path}")
        return
    if not os.path.exists(regime_path):
        print(f"[WARN] No existe {regime_path}")
        return

    print("=" * 60)
    print("GENERANDO TARGETS ADAPTATIVOS (ATR% + k por régimen)")
    print("=" * 60)

    print("\n[INFO] Cargando features enhanced...")
    df = pd.read_parquet(input_path)
    regime_df = pd.read_csv(regime_path)

    print("[INFO] Generando targets adaptativos (2 días)...")
    all_targets = []
    for ticker in df['ticker'].unique():
        dft = df[df['ticker'] == ticker].copy()
        dft = make_daily_adaptive_target(dft, regime_df, n_days=2)
        all_targets.append(dft)

    df_with_targets = pd.concat(all_targets, ignore_index=True)

    # Estadísticas rápidas de sanity-check
    print("\n" + "=" * 60)
    print("ESTADÍSTICAS DE TARGETS (SANITY CHECK)")
    print("=" * 60)

    # ATR% y thresholds
    median_atr_pct = df_with_targets['atr_pct_w'].median() * 100
    print(f"ATR%% Mediana: {median_atr_pct:.2f}% (esperado ~1-3%)")
    print(f"thr_up Mediana: {df_with_targets['thr_up'].median()*100:.2f}%")
    print(f"thr_dn Mediana: {df_with_targets['thr_dn'].median()*100:.2f}%")

    # Binario
    binary_valid = df_with_targets['target_binary'].notna().sum()
    binary_pos = (df_with_targets['target_binary'] == 1).sum()
    binary_neg = (df_with_targets['target_binary'] == 0).sum()
    if binary_valid > 0:
        print(f"\n📊 Target BINARIO (TP/SL):")
        print(f"  Total samples: {binary_valid:,}")
        print(f"  Positivos (1): {binary_pos:,} ({binary_pos/max(binary_valid,1)*100:.1f}%)")
        print(f"  Negativos (0): {binary_neg:,} ({binary_neg/max(binary_valid,1)*100:.1f}%)")
        print(f"  Balance:       {binary_pos/max(binary_valid,1):.2f}")
    else:
        print("[WARN] No hubo suficientes casos para target binario con los umbrales actuales.")

    # Ordinal
    ordinal_valid = df_with_targets['target_ordinal'].notna().sum()
    if ordinal_valid > 0:
        ordinal_dist = df_with_targets['target_ordinal'].value_counts().sort_index()
        print(f"\n📊 Target ORDINAL (4 clases):")
        print(f"  Total samples: {ordinal_valid:,}")
        label_map = {-1: 'Strong Down', 0: 'Weak Down', 1: 'Weak Up', 2: 'Strong Up'}
        for label, count in ordinal_dist.items():
            print(f"  {label_map.get(label, 'Unknown'):12s} ({int(label):2d}): {count:,} ({count/ordinal_valid*100:.1f}%)")

    # Guardar
    df_with_targets.to_parquet(output_path, index=False, compression='snappy')
    print(f"\n[OK] Guardado en: {output_path}")

    # Versiones derivadas
    df_binary = df_with_targets[df_with_targets['target_binary'].notna()].copy()
    binary_path = output_path.replace('_adaptive_targets', '_binary_targets')
    df_binary.to_parquet(binary_path, index=False, compression='snappy')
    print(f"[OK] Versión binaria: {binary_path}")

    df_ordinal = df_with_targets[df_with_targets['target_ordinal'].notna()].copy()
    ordinal_path = output_path.replace('_adaptive_targets', '_ordinal_targets')
    df_ordinal.to_parquet(ordinal_path, index=False, compression='snappy')
    print(f"[OK] Versión ordinal: {ordinal_path}")


if __name__ == "__main__":
    main()
