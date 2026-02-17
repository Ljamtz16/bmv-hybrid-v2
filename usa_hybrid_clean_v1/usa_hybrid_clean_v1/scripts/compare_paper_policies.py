# -*- coding: utf-8 -*-
"""
Genera reporte comparativo de políticas A/B desde paper_summary.csv

Uso:
  python scripts/compare_paper_policies.py --input paper_summary.csv
"""

import argparse
import pandas as pd
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="paper_summary.csv", help="CSV con resultados paper trading")
    args = ap.parse_args()

    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"ERROR: {csv_path} no existe")
        return

    df = pd.read_csv(csv_path)
    
    if len(df) == 0:
        print("CSV vacío")
        return

    print("\n" + "="*70)
    print("ANÁLISIS COMPARATIVO PAPER TRADING")
    print("="*70 + "\n")

    # Agrupar por tag
    tags = df['tag'].unique()
    
    for tag in tags:
        tag_df = df[df['tag'] == tag].copy()
        
        # Métricas globales
        total_days = len(tag_df)
        days_with_trades = (tag_df['num_plan_trades'] > 0).sum()
        total_trades = tag_df['num_plan_trades'].sum()
        total_exp_pnl_usd = tag_df['exp_pnl_sum_usd'].sum()
        
        # Métricas condicionales (solo días con trades)
        trade_days = tag_df[tag_df['num_plan_trades'] > 0]
        
        if len(trade_days) > 0:
            avg_trades_per_day = trade_days['num_plan_trades'].mean()
            avg_exposure = trade_days['exposure_total'].mean()
            avg_prob_win = trade_days['prob_win_mean'].mean()
            avg_p_tp_sl = trade_days['p_tp_before_sl_mean'].mean()
            avg_etth = trade_days['etth_median_days'].mean()
            avg_spread = trade_days['spread_mean_bps'].mean()
            avg_exp_pnl_day = trade_days['exp_pnl_sum_usd'].mean()
        else:
            avg_trades_per_day = 0
            avg_exposure = 0
            avg_prob_win = 0
            avg_p_tp_sl = 0
            avg_etth = 0
            avg_spread = 0
            avg_exp_pnl_day = 0
        
        print(f"Tag: {tag or '(sin tag)'}")
        print("-" * 70)
        print(f"  Días totales:              {total_days}")
        print(f"  Días con trades:           {days_with_trades} ({days_with_trades/total_days*100:.1f}%)")
        print(f"  Trades totales:            {total_trades}")
        print(f"  Trades/día (condicional):  {avg_trades_per_day:.2f}")
        print(f"  \n  E[PnL] total:              ${total_exp_pnl_usd:.2f}")
        print(f"  E[PnL] por día (cond.):    ${avg_exp_pnl_day:.2f}")
        print(f"  \n  Exposure medio (cond.):    ${avg_exposure:.2f}")
        print(f"  Prob_win media (cond.):    {avg_prob_win:.3f}")
        print(f"  P(TP<SL) media (cond.):    {avg_p_tp_sl:.3f}")
        print(f"  ETTH mediana (cond.):      {avg_etth:.3f} días ({avg_etth*6.5:.1f}h)")
        print(f"  Spread medio (cond.):      {avg_spread:.1f} bps")
        print("\n")

    # Comparación directa si hay múltiples tags
    if len(tags) > 1:
        print("="*70)
        print("COMPARACIÓN DIRECTA")
        print("="*70 + "\n")
        
        summary = []
        for tag in tags:
            tag_df = df[df['tag'] == tag]
            trade_days = tag_df[tag_df['num_plan_trades'] > 0]
            
            summary.append({
                'Tag': tag,
                'Días': len(tag_df),
                'Días_Trade': len(trade_days),
                'Trades': tag_df['num_plan_trades'].sum(),
                'E[PnL]_Total': tag_df['exp_pnl_sum_usd'].sum(),
                'E[PnL]/Día': trade_days['exp_pnl_sum_usd'].mean() if len(trade_days) > 0 else 0,
                'Prob_Win': trade_days['prob_win_mean'].mean() if len(trade_days) > 0 else 0,
                'Spread_bps': trade_days['spread_mean_bps'].mean() if len(trade_days) > 0 else 0
            })
        
        comp_df = pd.DataFrame(summary)
        print(comp_df.to_string(index=False))
        print("\n")

    # Timeline diario
    print("="*70)
    print("TIMELINE DIARIO")
    print("="*70 + "\n")
    
    timeline = df.sort_values(['tag', 'date'])[
        ['tag', 'date', 'num_plan_trades', 'exposure_total', 'exp_pnl_sum_usd', 'prob_win_mean']
    ].copy()
    
    timeline['exp_pnl_sum_usd'] = timeline['exp_pnl_sum_usd'].fillna(0)
    timeline['prob_win_mean'] = timeline['prob_win_mean'].fillna(0)
    
    # Formato más legible
    timeline.columns = ['Tag', 'Fecha', 'Trades', 'Exposure', 'E[PnL]', 'Prob_Win']
    timeline['Exposure'] = timeline['Exposure'].apply(lambda x: f"${x:.0f}" if x > 0 else "-")
    timeline['E[PnL]'] = timeline['E[PnL]'].apply(lambda x: f"${x:.2f}" if x != 0 else "-")
    timeline['Prob_Win'] = timeline['Prob_Win'].apply(lambda x: f"{x:.3f}" if x > 0 else "-")
    
    print(timeline.to_string(index=False))
    print("\n")


if __name__ == "__main__":
    main()
