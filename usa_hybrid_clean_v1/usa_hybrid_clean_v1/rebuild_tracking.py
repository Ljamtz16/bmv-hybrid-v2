import pandas as pd
from pathlib import Path

# Limpiar tracking - empezar desde cero
tracking_path = Path('val/standard_plan_tracking.csv')
if tracking_path.exists():
    tracking_path.unlink()
    print('✓ Archivo de tracking eliminado')

# Cargar plan STANDARD más reciente
plans_dir = Path('evidence/weekly_plans')
std_files = sorted(plans_dir.glob('plan_standard_*.csv'))
if std_files:
    latest = std_files[-1]
    df = pd.read_csv(latest)
    
    # Crear IDs únicos correctos
    df_new = df.copy()
    df_new['trade_id'] = df_new.apply(
        lambda r: f"STD-{r['ticker'].upper()}-{r['side'].upper()}-{float(r['entry']):.4f}",
        axis=1
    )
    
    # Guardar como tracking nuevo
    df_new.to_csv(tracking_path, index=False)
    print(f'✓ Tracking reconstruido desde {latest.name}')
    print(f'  Trades en tracking: {len(df_new)}')
    print(f'  Tickers: {df_new["ticker"].tolist()}')
