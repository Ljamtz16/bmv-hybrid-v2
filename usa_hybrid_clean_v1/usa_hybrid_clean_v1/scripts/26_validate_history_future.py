# =============================================
# 26_validate_history_future.py
# =============================================
import subprocess, argparse, pandas as pd

def run(cmd): print(f"▶ {cmd}"); subprocess.run(cmd,shell=True,check=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--back-start",default="2023-01")
    ap.add_argument("--back-end",default="2024-12")
    ap.add_argument("--forward-start",default="2025-01")
    ap.add_argument("--forward-end",default="2025-06")
    args=ap.parse_args()

    months=pd.period_range(args.back_start,args.back_end,freq="M").astype(str)
    for m in months:
        run(f"python scripts/24_simulate_trading.py --month {m} --capital-initial 10000")
    run(f"python scripts/wf_plan.py --train-end-jan {args.back_end} --train-end-forward {args.forward_end}")

if __name__=="__main__":
    main()