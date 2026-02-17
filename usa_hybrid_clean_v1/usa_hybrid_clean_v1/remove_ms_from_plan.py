import pandas as pd

# Leer plan STANDARD actual
df_plan = pd.read_csv('evidence/weekly_plans/plan_standard_2026-01-29.csv')

print('Posiciones en plan STANDARD antes:')
print(df_plan[['ticker', 'side', 'entry']].to_string(index=False))

# Remover MS
df_plan = df_plan[df_plan['ticker'] != 'MS']

# Guardar plan actualizado
df_plan.to_csv('evidence/weekly_plans/plan_standard_2026-01-29.csv', index=False)

print('\nPosiciones en plan STANDARD después:')
print(df_plan[['ticker', 'side', 'entry']].to_string(index=False))
print('\n✅ MS removida del plan STANDARD')
