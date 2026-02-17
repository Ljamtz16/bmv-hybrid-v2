# =============================================
# 21_pattern_features.py
# =============================================
import argparse, pandas as pd, os, glob, json

def _load_memory(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns_dir", default="reports/patterns")
    ap.add_argument("--features_in", default="features_labeled.csv")
    ap.add_argument("--features_out", default="features_labeled_with_patterns.csv")
    ap.add_argument("--pattern_memory", default="reports/patterns/pattern_memory.json")
    args = ap.parse_args()

    files=glob.glob(os.path.join(args.patterns_dir,"*.csv"))
    pats=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
    pats['date']=pd.to_datetime(pats['date'])
    mem=_load_memory(args.pattern_memory)
    for c in ['double_top','double_bottom']:
        if c in pats.columns:
            w=mem.get('pattern_weights',{}).get(c.upper(),1.0)
            pats[f'{c}_w']=pats[c]*w
    base=pd.read_csv(args.features_in)
    base['date']=pd.to_datetime(base['date'])
    out=base.merge(pats,on=['ticker','date'],how='left').fillna(0)
    out.to_csv(args.features_out,index=False)
    print(f"[features] -> {args.features_out}")

if __name__=="__main__":
    main()