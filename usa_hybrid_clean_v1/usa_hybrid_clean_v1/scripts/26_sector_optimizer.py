# =============================================
# 26_sector_optimizer.py
# =============================================
import pandas as pd
import json
import argparse
import os

def optimize_sector_weights(df, metric='net_pnl_sum', floor=0.05, cap=0.70):
    """
    Calcula pesos óptimos por sector según la métrica elegida.
    Aplica floor (mínimo) y cap (máximo) a cada peso.
    """
    # Filtrar sectores con trades > 0
    df_active = df[df['trades'] > 0].copy()
    
    if len(df_active) == 0:
        return {}
    
    # Normalizar métrica (mayor es mejor)
    if metric in df_active.columns:
        df_active['score'] = df_active[metric]
        # Si es negativo, convertir a 0
        df_active['score'] = df_active['score'].clip(lower=0)
    else:
        raise ValueError(f"Métrica '{metric}' no encontrada en el CSV")
    
    total_score = df_active['score'].sum()
    if total_score == 0:
        # Distribuir uniformemente
        n = len(df_active)
        return {row['sector']: 1.0/n for _, row in df_active.iterrows()}
    
    # Calcular pesos iniciales
    df_active['weight'] = df_active['score'] / total_score
    
    # Aplicar cap
    df_active['weight'] = df_active['weight'].clip(upper=cap)
    
    # Re-normalizar
    total_weight = df_active['weight'].sum()
    df_active['weight'] = df_active['weight'] / total_weight
    
    # Aplicar floor
    df_active['weight'] = df_active['weight'].clip(lower=floor)
    
    # Re-normalizar nuevamente
    total_weight = df_active['weight'].sum()
    df_active['weight'] = df_active['weight'] / total_weight
    
    return dict(zip(df_active['sector'], df_active['weight']))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True)
    ap.add_argument('--input', required=True, help='Path to kpi_compare_sectors.csv')
    ap.add_argument('--metric', default='net_pnl_sum', 
                    choices=['net_pnl_sum', 'win_rate', 'capital_final', 'sharpe'])
    ap.add_argument('--floor', type=float, default=0.05)
    ap.add_argument('--cap', type=float, default=0.70)
    ap.add_argument('--out-json', required=True, help='Output path for policy_sector_weights.json')
    ap.add_argument('--update-policy', default='', help='Optional: update existing policy JSON file')
    args = ap.parse_args()
    
    # Leer KPIs
    df = pd.read_csv(args.input)
    
    # Filtrar 'all' si existe
    df = df[df['sector'] != 'all']
    
    # Optimizar pesos
    weights = optimize_sector_weights(df, args.metric, args.floor, args.cap)
    
    # Crear output
    output = {
        'month': args.month,
        'metric': args.metric,
        'floor': args.floor,
        'cap': args.cap,
        'weights': weights
    }
    
    # Guardar JSON
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"[optimizer] Pesos sectoriales guardados en {args.out_json}")
    print(f"[optimizer] Pesos: {weights}")
    
    # Actualizar policy si se especifica
    if args.update_policy and os.path.exists(args.update_policy):
        with open(args.update_policy, 'r') as f:
            policy = json.load(f)
        policy['sector_weights'] = weights
        policy['sector_weights_month'] = args.month
        with open(args.update_policy, 'w') as f:
            json.dump(policy, f, indent=2)
        print(f"[optimizer] Policy actualizada: {args.update_policy}")

if __name__ == "__main__":
    main()
