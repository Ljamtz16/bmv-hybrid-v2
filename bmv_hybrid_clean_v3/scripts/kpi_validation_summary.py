import pandas as pd

# Ruta al archivo de validación
csv_path = r"c:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\bmv_hybrid_clean_v3\reports\runs\20250829_202937_2025-05\validation\validation_trades_auto.csv"

df = pd.read_csv(csv_path)

# Filtrar trades válidos (excluir 'NoBars')
valid_trades = df[df['reason'] != 'NoBars']

total_trades = len(valid_trades)
winning_trades = (valid_trades['pnl'] > 0).sum()
losing_trades = (valid_trades['pnl'] <= 0).sum()

percent_win = 100 * winning_trades / total_trades if total_trades > 0 else 0

# KPIs
sum_pnl = valid_trades['pnl'].sum()
avg_pnl = valid_trades['pnl'].mean() if total_trades > 0 else 0
max_pnl = valid_trades['pnl'].max() if total_trades > 0 else 0
min_pnl = valid_trades['pnl'].min() if total_trades > 0 else 0

print(f"Total trades válidos: {total_trades}")
print(f"Trades ganadores: {winning_trades}")
print(f"Trades perdedores: {losing_trades}")
print(f"Porcentaje de aciertos: {percent_win:.2f}%")
print(f"Ganancia total: {sum_pnl:.2f}")
print(f"Ganancia promedio por trade: {avg_pnl:.2f}")
print(f"Mejor trade: {max_pnl:.2f}")
print(f"Peor trade: {min_pnl:.2f}")
