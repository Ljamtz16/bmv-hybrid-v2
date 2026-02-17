#!/usr/bin/env python3
"""
Script para limpiar duplicados del historial de trades
"""
import pandas as pd
from pathlib import Path

HISTORY_FILE = Path("val/trade_history_closed.csv")

def clean_duplicates():
    if not HISTORY_FILE.exists():
        print("No existe archivo de historial")
        return
    
    df = pd.read_csv(HISTORY_FILE)
    print(f"Total registros: {len(df)}")
    
    # Crear ID único basado en características del trade
    df['trade_id'] = (
        df['ticker'].astype(str) + '_' +
        df['side'].astype(str) + '_' +
        df['entry'].astype(str) + '_' +
        df['date'].astype(str)
    )
    
    # Mantener solo el primer registro de cada trade_id
    df_clean = df.drop_duplicates(subset=['trade_id'], keep='first')
    
    print(f"Registros únicos: {len(df_clean)}")
    print(f"Duplicados eliminados: {len(df) - len(df_clean)}")
    
    # Guardar limpio
    df_clean.to_csv(HISTORY_FILE, index=False)
    print(f"\n✅ Historial limpiado guardado en {HISTORY_FILE}")
    
    # Mostrar resumen
    print("\nRESUMEN DE TRADES ÚNICOS:")
    print("="*70)
    for _, row in df_clean.iterrows():
        print(f"{row['ticker']:6} {row['side']:4} {row['exit_reason']:2} | "
              f"Entry: ${row['entry']:8.2f} → Exit: ${row['exit']:8.2f} | "
              f"P&L: ${row['pnl']:7.2f} ({row['pnl_pct']:+6.2f}%) | "
              f"{row['closed_at']}")
    
    # Estadísticas
    wins = len(df_clean[df_clean['pnl'] > 0])
    losses = len(df_clean[df_clean['pnl'] <= 0])
    total_pnl = df_clean['pnl'].sum()
    
    print("\n" + "="*70)
    print(f"WINS: {wins} | LOSSES: {losses} | Win Rate: {wins/(wins+losses)*100:.1f}%")
    print(f"P&L Total: ${total_pnl:.2f}")
    print("="*70)

if __name__ == "__main__":
    clean_duplicates()
