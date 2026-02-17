# -*- coding: utf-8 -*-
"""
Generador de datos sintéticos para entrenamiento intraday
Estrategia: Monte Carlo con preservación de estructura temporal

Usa features reales para:
- Estimar distribuciones marginales (RSI, ATR, spread, etc.)
- Calcular matriz de correlación
- Generar trayectorias sintéticas con autocorrelación

Aumenta positivos (WIN) para balancear dataset (target: 5-10% win rate)

Uso:
  python scripts/generate_synthetic_intraday.py --input-dir features/intraday --output features_synthetic_intraday.parquet --num-days 30 --win-rate-target 0.08
"""


import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Soporte de semilla global reproducible
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from utils.random_utils import set_global_seed


def load_real_features(input_dir: Path, max_days=60):
    """Cargar features reales para análisis."""
    print(f"[synthetic] Cargando features reales desde {input_dir}")
    
    dfs = []
    for f in sorted(input_dir.glob("2025-*.parquet"))[:max_days]:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except Exception as e:
            print(f"  WARN: Error cargando {f.name}: {e}")
    
    if not dfs:
        raise ValueError(f"No se encontraron features en {input_dir}")
    
    df_all = pd.concat(dfs, ignore_index=True)
    print(f"  Cargados {len(df_all)} samples de {len(dfs)} días")
    
    return df_all


def compute_feature_stats(df):
    """Calcular estadísticas de features para generación."""
    print("[synthetic] Calculando estadísticas de features...")
    
    # Features numéricos principales
    feature_cols = [
        'RSI_14', 'EMA_50', 'MACD', 'ATR_pct', 'BB_width',
        'volume_ratio', 'spread_bps', 'turnover_ratio',
        'hour', 'minute', 'dist_to_open', 'dist_to_close'
    ]
    
    # Filtrar columnas existentes
    available_cols = [c for c in feature_cols if c in df.columns]
    
    if len(available_cols) == 0:
        raise ValueError("No hay features numéricos disponibles")
    
    df_feats = df[available_cols].dropna()
    
    stats = {
        'means': df_feats.mean().to_dict(),
        'stds': df_feats.std().to_dict(),
        'mins': df_feats.min().to_dict(),
        'maxs': df_feats.max().to_dict(),
        'corr': df_feats.corr().values,
        'feature_names': available_cols
    }
    
    print(f"  Features analizados: {len(available_cols)}")
    
    return stats


def estimate_win_conditions(df):
    """Analizar condiciones que llevan a WIN para generar positivos."""
    print("[synthetic] Analizando condiciones WIN...")
    
    if 'win' not in df.columns or df['win'].sum() == 0:
        print("  WARN: No hay wins en dataset, usando defaults")
        return None
    
    wins = df[df['win'] == 1].copy()
    losses = df[df['win'] == 0].copy()
    
    conditions = {}
    
    # Comparar distribuciones WIN vs LOSS
    for col in ['RSI_14', 'ATR_pct', 'volume_ratio', 'spread_bps', 'MACD', 'hour']:
        if col in wins.columns and col in losses.columns:
            win_mean = wins[col].mean()
            loss_mean = losses[col].mean()
            win_std = wins[col].std()
            
            conditions[col] = {
                'win_mean': win_mean,
                'loss_mean': loss_mean,
                'win_std': win_std,
                'shift': win_mean - loss_mean  # Dirección de sesgo
            }
    
    print(f"  Wins analizados: {len(wins)} ({len(wins)/len(df)*100:.2f}%)")
    print(f"  Condiciones WIN identificadas: {len(conditions)}")
    
    return conditions


def generate_intraday_session(stats, win_conditions, ticker, date, target_win=False):
    """Generar una sesión intraday sintética (26 bars de 15min)."""
    # La semilla global ya fue fijada al inicio del script
    
    n_bars = 26  # 6.5 horas × 4 bars/hora
    feature_names = stats['feature_names']
    means = np.array([stats['means'][f] for f in feature_names])
    stds = np.array([stats['stds'][f] for f in feature_names])
    corr = stats['corr']
    
    # Generar features correlacionados
    try:
        # Cholesky decomposition para correlación
        L = np.linalg.cholesky(corr + np.eye(len(corr)) * 1e-6)
        z = np.random.randn(n_bars, len(feature_names))
        x_corr = z @ L.T
    except np.linalg.LinAlgError:
        # Fallback si correlación no es positiva definida
        x_corr = np.random.randn(n_bars, len(feature_names))
    
    # Escalar a media/std originales
    x_scaled = x_corr * stds + means
    
    # Ajustar para target WIN si se pide
    if target_win and win_conditions:
        for i, fname in enumerate(feature_names):
            if fname in win_conditions:
                shift = win_conditions[fname]['shift']
                # Sesgar hacia condición WIN (50% del shift)
                x_scaled[:, i] += shift * 0.5
    
    # Crear DataFrame
    df_session = pd.DataFrame(x_scaled, columns=feature_names)
    
    # Agregar metadata
    df_session['ticker'] = ticker
    df_session['date'] = date
    
    # Generar timestamps (9:30-16:00 en intervalos de 15min)
    start_dt = pd.Timestamp(f"{date} 09:30:00", tz='America/New_York')
    timestamps = [start_dt + pd.Timedelta(minutes=15*i) for i in range(n_bars)]
    df_session['timestamp'] = timestamps
    
    # Ajustar rangos físicos
    df_session['RSI_14'] = df_session['RSI_14'].clip(0, 100)
    df_session['ATR_pct'] = df_session['ATR_pct'].clip(0.001, 0.05)
    df_session['volume_ratio'] = df_session['volume_ratio'].clip(0.1, 5.0)
    df_session['spread_bps'] = df_session['spread_bps'].clip(5, 200)
    df_session['hour'] = df_session['hour'].clip(9, 16).astype(int)
    df_session['minute'] = df_session['minute'].clip(0, 59).astype(int)
    
    # Direction (LONG/SHORT basado en MACD y RSI)
    if 'MACD' in df_session.columns and 'RSI_14' in df_session.columns:
        df_session['direction'] = np.where(
            (df_session['MACD'] > 0) & (df_session['RSI_14'] < 70),
            'LONG',
            'SHORT'
        )
    else:
        df_session['direction'] = 'LONG'
    
    # Generar target (win) basado en probabilidades
    if target_win:
        # Sesgo hacia WIN (70% chance)
        df_session['win'] = np.random.choice([0, 1], size=n_bars, p=[0.3, 0.7])
        df_session['hit_type'] = np.where(df_session['win'] == 1, 'TP', 'SL')
    else:
        # Normal (match distribución real ~2%)
        df_session['win'] = np.random.choice([0, 1], size=n_bars, p=[0.98, 0.02])
        df_session['hit_type'] = np.where(df_session['win'] == 1, 'TP', 'SL')
    
    # TTE (time to exit) - bars hasta TP/SL
    df_session['tte_bars'] = np.random.randint(1, 15, size=n_bars)
    
    return df_session


def generate_synthetic_dataset(stats, win_conditions, num_days, win_rate_target, tickers):
    """Generar dataset sintético completo."""
    print(f"[synthetic] Generando {num_days} días sintéticos...")
    print(f"  Win rate target: {win_rate_target*100:.1f}%")
    print(f"  Tickers: {tickers}")
    
    start_date = datetime(2025, 11, 1)
    
    # Calcular cuántos días WIN necesitamos
    total_sessions = num_days * len(tickers)
    win_sessions_needed = int(total_sessions * win_rate_target / 0.7)  # 0.7 = win rate dentro de sesión WIN
    
    print(f"  Sesiones totales: {total_sessions}")
    print(f"  Sesiones WIN target: {win_sessions_needed}")
    
    all_sessions = []
    win_count = 0
    
    for day_offset in range(num_days):
        date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        
        # Saltar fines de semana
        dt = datetime.strptime(date, "%Y-%m-%d")
        if dt.weekday() >= 5:  # Sábado=5, Domingo=6
            continue
        
        for ticker in tickers:
            # Decidir si esta sesión será WIN-biased
            target_win = win_count < win_sessions_needed
            
            session = generate_intraday_session(stats, win_conditions, ticker, date, target_win)
            all_sessions.append(session)
            
            if target_win:
                win_count += 1
    
    df_synthetic = pd.concat(all_sessions, ignore_index=True)
    
    actual_win_rate = df_synthetic['win'].mean()
    print(f"  Win rate logrado: {actual_win_rate*100:.2f}%")
    print(f"  Total samples: {len(df_synthetic)}")
    
    return df_synthetic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default="features/intraday", help="Dir con features reales")
    ap.add_argument("--output", default="features_synthetic_intraday.parquet", help="Archivo salida")
    ap.add_argument("--num-days", type=int, default=30, help="Días sintéticos a generar")
    ap.add_argument("--win-rate-target", type=float, default=0.08, help="Win rate objetivo (8% default)")
    ap.add_argument("--max-real-days", type=int, default=60, help="Días reales para análisis")
    ap.add_argument("--tickers", nargs="+", default=["AMD", "NVDA", "TSLA", "MSFT"], help="Tickers")
    ap.add_argument("--seed", type=int, default=None, help="Semilla aleatoria global para reproducibilidad (prioridad sobre SEED env)")
    args = ap.parse_args()

    # Fijar semilla global para reproducibilidad
    seed_used = set_global_seed(args.seed)
    print(f"[synthetic] Usando seed global = {seed_used}")
    
    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    
    # 1. Cargar datos reales
    df_real = load_real_features(input_dir, args.max_real_days)
    
    # 2. Calcular estadísticas
    stats = compute_feature_stats(df_real)
    
    # 3. Analizar condiciones WIN
    win_conditions = estimate_win_conditions(df_real)
    
    # 4. Generar sintéticos
    df_synthetic = generate_synthetic_dataset(
        stats, 
        win_conditions, 
        args.num_days, 
        args.win_rate_target,
        args.tickers
    )
    
    # 5. Guardar
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_synthetic.to_parquet(output_path, index=False)
    
    print(f"\n[synthetic] Dataset guardado: {output_path}")
    print(f"  Shape: {df_synthetic.shape}")
    print(f"  Win rate: {df_synthetic['win'].mean()*100:.2f}%")
    print(f"  Tickers: {df_synthetic['ticker'].nunique()}")
    print(f"  Días únicos: {df_synthetic['date'].nunique()}")
    
    # Stats finales
    print(f"\n[synthetic] Distribución de targets:")
    print(f"  WIN (TP):  {(df_synthetic['win']==1).sum()} ({(df_synthetic['win']==1).sum()/len(df_synthetic)*100:.2f}%)")
    print(f"  LOSS (SL): {(df_synthetic['win']==0).sum()} ({(df_synthetic['win']==0).sum()/len(df_synthetic)*100:.2f}%)")
    
    print(f"\n[synthetic] Dirección:")
    print(f"  LONG:  {(df_synthetic['direction']=='LONG').sum()} ({(df_synthetic['direction']=='LONG').sum()/len(df_synthetic)*100:.1f}%)")
    print(f"  SHORT: {(df_synthetic['direction']=='SHORT').sum()} ({(df_synthetic['direction']=='SHORT').sum()/len(df_synthetic)*100:.1f}%)")


if __name__ == "__main__":
    main()
