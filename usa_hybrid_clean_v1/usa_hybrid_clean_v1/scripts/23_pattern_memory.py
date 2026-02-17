# =============================================
# 23_pattern_memory.py
# =============================================
import argparse, pandas as pd, numpy as np, json, os

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--trades",default="reports/trades_history.csv")
    ap.add_argument("--outdir",default="reports/patterns")
    args=ap.parse_args()
    os.makedirs(args.outdir,exist_ok=True)

    df=pd.read_csv(args.trades)
    if 'pattern' not in df.columns or 'ret' not in df.columns:
        print("Faltan columnas 'pattern' y 'ret'"); return
    weights=df.groupby('pattern')['ret'].mean().to_dict()
    norm={k:v/np.mean(list(weights.values())) for k,v in weights.items()}
    mem={'pattern_weights':norm}
    json.dump(mem,open(os.path.join(args.outdir,"pattern_memory.json"),"w"),indent=2)
    print(f"[memory] Guardado pattern_memory.json con {len(norm)} patrones")

if __name__=="__main__":
    main()