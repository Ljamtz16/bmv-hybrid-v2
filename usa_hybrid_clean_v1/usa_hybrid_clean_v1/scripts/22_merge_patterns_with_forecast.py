# =============================================
# 22_merge_patterns_with_forecast.py
# =============================================
import argparse, os, pandas as pd, json, numpy as np

def _load_memory(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--month",required=True)
    ap.add_argument("--forecast_dir",default="reports/forecast")
    ap.add_argument("--features_with_patterns",default="features_labeled_with_patterns.csv")
    ap.add_argument("--pattern_memory",default="reports/patterns/pattern_memory.json")
    ap.add_argument("--outname",default="forecast_with_patterns.csv")
    ap.add_argument("--gate_threshold",type=float,default=0.65)
    args=ap.parse_args()

    f_fore=os.path.join(args.forecast_dir,args.month,"forecast_signals.csv")
    fore=pd.read_csv(f_fore)
    feats=pd.read_csv(args.features_with_patterns)
    fore['date']=pd.to_datetime(fore['date'])
    feats['date']=pd.to_datetime(feats['date'])
    merged=fore.merge(feats,on=['ticker','date'],how='left')
    mem=_load_memory(args.pattern_memory)

    merged['pattern_weight']=1.0
    for p,w in mem.get('pattern_weights',{}).items():
        pcol=p.lower()
        if pcol in merged.columns: merged['pattern_weight']+=merged[pcol]*w
    merged['pscore_adj']=merged['pattern_weight']
    # gate_pattern_ok combina el threshold de patrones y, si existe, el gate_ok base
    base_gate = merged['gate_ok'] if 'gate_ok' in merged.columns else 1
    merged['gate_pattern_ok'] = ((merged['pscore_adj']>=args.gate_threshold) & (base_gate==1)).astype(int)
    # Asegurar entry_price si falta: usar close/price como fallback
    if 'entry_price' not in merged.columns or merged['entry_price'].isna().all():
        if 'close' in merged.columns:
            merged['entry_price'] = merged['close']
        elif 'price' in merged.columns:
            merged['entry_price'] = merged['price']
        else:
            merged['entry_price'] = np.nan
    merged.to_csv(os.path.join(args.forecast_dir,args.month,args.outname),index=False)
    print(f"[merge] Guardado forecast_with_patterns.csv ({len(merged)})")

if __name__=="__main__":
    main()