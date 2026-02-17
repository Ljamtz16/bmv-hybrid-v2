import pandas as pd
from ..models.adapters import get_features_row, prob_rf, prob_svm, prob_lstm_sim, fuse_probs

def generate_daily_signals(d1_map, rf=None, svm=None, lstm_sim=None,
                           buy_tau=0.0, sell_tau=0.0,
                           tickers=None, dates=None, weights=(0.5,0.3,0.2),
                           min_prob=0.0):
    rows = []
    tickers = tickers or list(d1_map.keys())
    for t in tickers:
        df = d1_map[t]
        idx = df.index if dates is None else [d for d in dates if d in df.index]
        for D in idx:
            sub = df.loc[:D].tail(200).copy()
            if len(sub) < 60: continue
            feats = get_features_row(sub)
            p_buy_rf,  p_sell_rf  = prob_rf(rf, feats)
            p_buy_svm, p_sell_svm = prob_svm(svm, feats)
            p_buy_l,   p_sell_l   = prob_lstm_sim(lstm_sim, sub)
            p_buy, p_sell = fuse_probs((p_buy_rf,p_sell_rf), (p_buy_svm,p_sell_svm), (p_buy_l,p_sell_l), weights=weights)

            if p_buy is None and p_sell is None: continue
            cand = []
            if p_buy is not None and p_buy >= buy_tau and p_buy >= min_prob: cand.append(("BUY", p_buy))
            if p_sell is not None and p_sell >= sell_tau and p_sell >= min_prob: cand.append(("SELL", p_sell))
            if cand:
                side, prob = sorted(cand, key=lambda x: x[1], reverse=True)[0]
                rows.append({"ticker": t, "date": pd.to_datetime(D).date().isoformat(), "side": side, "prob": float(prob)})
    return pd.DataFrame(rows)
