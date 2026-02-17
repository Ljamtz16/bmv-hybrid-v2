# Regime Stress Report

## 1. Pre-2020 Performance (Extended 2015–2020)

Frozen model: {'train_window': {'start': '2020-01-01', 'end': '2025-06-30'}, 'calibrated': True, 'auc': 0.9870365546583312, 'metrics': {'trades': 2, 'wr': 1.0, 'pf': 0.0, 'mean_r': 1.3333333333333321, 'max_dd': 0.0}}

Refit model: None

## 2. Sideways Regime Robustness

{'sideways_days': 198, 'trades': 25, 'wr': 0.64, 'pf': 3.868337511884073, 'mean_r': 0.34826428423520506, 'max_dd': 0.012047781946590135, 'trade_freq_per_day': 1.6666666666666667, 'thresholds': {'atr_pct_lt': 0.6, 'ema50_slope_abs_lt': 0.003, 'ret_30d_between': [-0.05, 0.05]}}

## 3. Crisis 2022 Resilience

Base: {'wr': 0.9340659340659341, 'pf': 20.87134502701846, 'mean_r': 0.7876305564390246, 'max_dd': 0.010000000000000085, 'equity_final': 2.0390660912691914}

Slippage +1: {'wr': 0.9340659340659341, 'pf': 20.584497439420115, 'mean_r': 0.7827229709390329, 'max_dd': 0.010108024691358124, 'equity_final': 2.0300521516801124}

Slippage +2: {'wr': 0.9340659340659341, 'pf': 20.302347414621188, 'mean_r': 0.7778153854390409, 'max_dd': 0.010216049382716107, 'equity_final': 2.0210774709064725}

Worst Month: {'month': '2022-02', 'pf': 0.0, 'wr': 1.0, 'mean_r': 0.7566951507081545}

## 4. Regime Dependency
 trades       wr        pf    avg_r  expectancy       regime
     18 0.944444 22.666667 1.203704    1.203704 vol_high_vol
     25 0.960000 32.000000 1.240000    1.240000   trend_bull

## 5. Slippage Tolerance

{'window': {'start': '2025-07-01', 'end': '2026-02-13'}, 'scenarios': [{'wr': 0.821917808219178, 'pf': 10.081639780701849, 'equity_final': 1.6571757192202665, 'max_dd': 0.013508043478260774, 'mean_r': 0.6966863340679246, 'ticks': 0}, {'wr': 0.821917808219178, 'pf': 10.015640984636217, 'equity_final': 1.6544689883148973, 'max_dd': 0.013623800044342787, 'mean_r': 0.6944295538522414, 'ticks': 1}, {'wr': 0.821917808219178, 'pf': 9.950173452116282, 'equity_final': 1.6517665789373677, 'max_dd': 0.013739546972178508, 'mean_r': 0.6921727736365582, 'ticks': 2}, {'wr': 0.821917808219178, 'pf': 9.885230794172191, 'equity_final': 1.6490684843448484, 'max_dd': 0.013855284262329208, 'mean_r': 0.689915993420875, 'ticks': 3}], 'pf_decay_curve': [{'ticks': 0, 'pf': 10.081639780701849}, {'ticks': 1, 'pf': 10.015640984636217}, {'ticks': 2, 'pf': 9.950173452116282}, {'ticks': 3, 'pf': 9.885230794172191}]}


## 6. Final Institutional Verdict

Review the five tests above. If PF or WR collapses in sideways/crisis regimes, the system is regime-dependent.
