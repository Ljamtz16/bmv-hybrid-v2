import argparse, pandas as pd, json
ap = argparse.ArgumentParser()
ap.add_argument("--csv", required=True)
ap.add_argument("--out", default="")
a = ap.parse_args()

df = pd.read_csv(a.csv)
out = {
  "trades": int(len(df)),
  "tp": int((df["exit_reason"]=="tp").sum()) if "exit_reason" in df.columns else None,
  "sl": int((df["exit_reason"]=="sl").sum()) if "exit_reason" in df.columns else None,
  "horizon": int((df["exit_reason"]=="horizon").sum()) if "exit_reason" in df.columns else None,
  "gross_pnl_sum": float(df.get("gross_pnl",0).sum()),
  "net_pnl_sum": float(df.get("net_pnl",0).sum())
}
print(json.dumps(out, indent=2))
if a.out:
    with open(a.out, "w") as f: json.dump(out, f, indent=2)
