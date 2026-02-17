# =============================================
# compare_sector_kpis.py
# =============================================
import glob, json, pandas as pd

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True)
    ap.add_argument('--forecast_dir', default='reports/forecast')
    args = ap.parse_args()

    kpi_files = glob.glob(f"{args.forecast_dir}/{args.month}/kpi_*.json")
    rows = []
    for f in kpi_files:
        with open(f) as fj:
            row = json.load(fj)
            row['file'] = f
            rows.append(row)
    df = pd.DataFrame(rows)
    print(df[['sector','win_rate','net_pnl_sum','capital_final','trades']])
    df.to_csv(f"{args.forecast_dir}/{args.month}/kpi_compare_sectors.csv", index=False)
    print(f"[compare] KPIs guardados en kpi_compare_sectors.csv")

if __name__ == "__main__":
    main()
