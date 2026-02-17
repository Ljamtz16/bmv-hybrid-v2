# =============================================
# 37_label_time_to_event.py
# =============================================
"""
Etiqueta trades históricos con tiempo hasta evento (TP/SL)
para entrenar modelos de time-to-hit.

Input: simulate_results*.csv (históricos)
Output: time_to_event_labeled.parquet
"""

import pandas as pd
import argparse
import os
from pathlib import Path

def label_time_to_event(trades_df):
    """
    Procesa trades históricos y genera etiquetas para TTH.
    
    Args:
        trades_df: DataFrame con trades simulados
        
    Returns:
        DataFrame con time_to_event_days, event_type, features
    """
    labeled = []
    
    for _, row in trades_df.iterrows():
        # Calcular tiempo hasta evento
        if pd.notna(row.get('entry_date')) and pd.notna(row.get('exit_date')):
            entry = pd.to_datetime(row['entry_date'])
            exit_date = pd.to_datetime(row['exit_date'])
            time_to_event = (exit_date - entry).days
        else:
            # Si no hay exit_date, usar horizon_days como censura
            time_to_event = row.get('horizon_days', 3)
        
        # Determinar tipo de evento
        outcome = str(row.get('outcome', row.get('close_reason', 'CENSORED'))).upper()
        
        if 'TP' in outcome or outcome == 'WIN':
            event_type = 'TP'
            event_observed = 1
        elif 'SL' in outcome or outcome == 'LOSS':
            event_type = 'SL'
            event_observed = 1
        else:
            # EXPIRE, HORIZON, CENSORED
            event_type = 'CENSORED'
            event_observed = 0
        
        # Features al momento de la señal
        features = {
            'ticker': row.get('ticker', ''),
            'entry_date': row.get('entry_date', ''),
            'time_to_event_days': time_to_event,
            'event_type': event_type,
            'event_observed': event_observed,
            
            # Features predictivas
            'prob_win': row.get('prob_win', 0.5),
            'y_hat': row.get('y_hat', 0.0),
            'abs_y_hat': abs(row.get('y_hat', 0.0)),
            'tp_pct': row.get('tp_pct', 0.06),
            'sl_pct': row.get('sl_pct', 0.01),
            'horizon_days': row.get('horizon_days', 3),
            
            # Indicadores técnicos
            'atr_pct': row.get('atr_pct', 0.02),
            'rsi14': row.get('rsi14', 50.0),
            'vol_z': row.get('vol_z', 0.0),
            
            # Patrones
            'pattern_weight': row.get('pattern_weight', 1.0),
            'pscore_adj': row.get('pscore_adj', 1.0),
            'double_top': row.get('double_top', 0),
            'double_bottom': row.get('double_bottom', 0),
            
            # Contexto
            'sector': row.get('sector', 'all'),
            
            # Resultado real
            'pnl': row.get('pnl', 0.0),
            'actual_return': row.get('actual_return', 0.0),
        }
        
        labeled.append(features)
    
    return pd.DataFrame(labeled)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades-dir", default="reports/forecast", 
                    help="Directorio con subdirectorios por mes")
    ap.add_argument("--months", default="", 
                    help="Meses a procesar (comma-separated), vacío = todos")
    ap.add_argument("--output", default="data/trading/time_to_event_labeled.parquet")
    ap.add_argument("--min-trades", type=int, default=5, 
                    help="Mínimo de trades por mes para incluir")
    args = ap.parse_args()
    
    # Buscar archivos de trades históricos
    trades_dir = Path(args.trades_dir)
    all_trades = []
    
    if args.months:
        months = [m.strip() for m in args.months.split(",")]
    else:
        # Buscar todos los subdirectorios YYYY-MM
        months = [d.name for d in trades_dir.iterdir() 
                  if d.is_dir() and d.name.count('-') == 1]
    
    print(f"[label_tth] Procesando {len(months)} meses...")
    
    for month in sorted(months):
        month_dir = trades_dir / month
        
        # Buscar archivos de trades
        trade_files = [
            "trades_detailed_enriched.csv",
            "trades_detailed.csv",
            "simulate_results_merged.csv",
            "simulate_results_all.csv",
        ]
        
        trades_df = None
        for fname in trade_files:
            fpath = month_dir / fname
            if fpath.exists():
                try:
                    trades_df = pd.read_csv(fpath)
                    print(f"[label_tth] {month}: {fname} ({len(trades_df)} trades)")
                    break
                except Exception as e:
                    print(f"[label_tth] Error leyendo {fpath}: {e}")
        
        if trades_df is None or len(trades_df) < args.min_trades:
            print(f"[label_tth] {month}: skip (sin datos suficientes)")
            continue
        
        # Etiquetar
        labeled = label_time_to_event(trades_df)
        labeled['month'] = month
        all_trades.append(labeled)
    
    if not all_trades:
        print("[label_tth] ERROR: No se encontraron trades para etiquetar")
        return
    
    # Consolidar
    df_all = pd.concat(all_trades, ignore_index=True)
    
    # Filtrar registros válidos
    df_all = df_all[df_all['time_to_event_days'] > 0].copy()
    df_all = df_all[df_all['time_to_event_days'] <= 10].copy()  # Max 10 días
    
    # Estadísticas
    print(f"\n[label_tth] === ESTADÍSTICAS ===")
    print(f"Total registros: {len(df_all)}")
    print(f"Eventos observados: {df_all['event_observed'].sum()}")
    print(f"Censurados: {(df_all['event_observed']==0).sum()}")
    print(f"\nPor tipo de evento:")
    print(df_all['event_type'].value_counts())
    print(f"\nTiempo promedio hasta evento:")
    print(f"  TP: {df_all[df_all['event_type']=='TP']['time_to_event_days'].mean():.2f} días")
    print(f"  SL: {df_all[df_all['event_type']=='SL']['time_to_event_days'].mean():.2f} días")
    print(f"  CENSORED: {df_all[df_all['event_type']=='CENSORED']['time_to_event_days'].mean():.2f} días")
    
    # Guardar
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df_all.to_parquet(args.output, index=False)
    print(f"\n[label_tth] Guardado → {args.output}")
    
    # Guardar también CSV para inspección
    csv_path = args.output.replace('.parquet', '.csv')
    df_all.to_csv(csv_path, index=False)
    print(f"[label_tth] CSV → {csv_path}")

if __name__ == "__main__":
    main()
