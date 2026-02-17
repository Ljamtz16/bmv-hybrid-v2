# Quick Verification Checklist

## ✅ Run These Commands to Verify Everything Works

### 1. Verify Core Modules Load
```bash
python operability.py
python operability_config.py
```

**Expected Output**:
```
✓ operability.py loaded
CONF_THRESHOLD: 4
ALLOWED_RISKS: ['LOW', 'MEDIUM']
WHITELIST_TICKERS: ['CVX', 'XOM', 'WMT', 'MSFT', 'SPY']
EXPECTED_OPERABLE_COUNT: 3881
```

### 2. Run Production Orchestrator
```bash
python production_orchestrator.py --date=2025-11-19
```

**Expected Output**:
- Breakdown: Global 26,634 → Operables 3,880
- Validation: Delta -1 (OK)
- File: run_audit.json created

### 3. Run Enhanced Metrics Reporter
```bash
python enhanced_metrics_reporter.py
```

**Expected Output**:
- Global Accuracy: ~48.81%
- Operable Accuracy: ~52.19%
- Improvement: +3.38 pts
- File: metrics_global_vs_operable.csv created

### 4. Test Diagnostic Tool
```bash
python diff_operables.py --test=outputs/analysis/signals_to_trade_2025-11-19.csv
```

**Expected Output**:
- Comparison table (missing/extra rows)
- Diagnosis if delta > 1

### 5. Test Ticker Normalization
```bash
python normalize_tickers.py
```

**Expected Output**:
- Normalizes tickers
- Creates backup
- Reports whitelist violations

### 6. Validate Consistency
```bash
python validate_operability_consistency.py
```

**Expected Output**:
- Operables count: 3,881
- Status: ✅ CONSISTENT

---

## 📊 Key Files Created

| File | Purpose | Status |
|------|---------|--------|
| operability.py | Single source of truth | ✅ Created & Tested |
| operability_config.py | Centralized config | ✅ Created & Tested |
| production_orchestrator.py | Refactored | ✅ Refactored & Tested |
| enhanced_metrics_reporter.py | Refactored | ✅ Refactored & Tested |
| diff_operables.py | Diagnostic tool | ✅ Created |
| normalize_tickers.py | Data hygiene | ✅ Created |
| new_script_template.py | Template for new scripts | ✅ Created |
| run_audit.json | Automatic audit | ✅ Auto-generated |
| REFACTORING_COMPLETE.md | Documentation | ✅ Created |
| MIGRATION_GUIDE.md | Migration instructions | ✅ Created |
| STATUS_FINAL_REFACTORING.md | Final status | ✅ Created |

---

## 🎯 Expected Numbers

**Operable Count**: 3,881
- Global: 26,634
- Conf >= 4: 10,383 (38.98%)
- + Risk <= MEDIUM: 10,363 (38.91%)
- + Whitelist: 3,880 (14.57%)

**Accuracy**:
- Global: ~48-50%
- Operable Slice: ~52-54%
- Improvement: +3-4 pts

---

## ❌ Troubleshooting

| Error | Solution |
|-------|----------|
| ModuleNotFoundError: operability | Ensure operability.py is in same dir |
| KeyError: 'macro_risk' | Run `df["macro_risk"] = calculate_risk_level(df["date"])` first |
| Operable count mismatch | Run `python diff_operables.py --test=yourfile.csv` to diagnose |
| Unicode encode errors | Already fixed - use [OK] instead of ✓ |

---

## 📋 Migration Status

**Completed**:
- ✅ operability.py (reference module)
- ✅ operability_config.py (centralized config)
- ✅ production_orchestrator.py (refactored)
- ✅ enhanced_metrics_reporter.py (refactored)

**Pending**:
- ⏳ backtest_confidence_rules.py
- ⏳ validate_operability_consistency.py
- ⏳ Your custom scripts

---

## 🚀 Next Steps

1. Run all verification commands above
2. Confirm all produce expected output
3. If all ✅: Proceed to refactor remaining scripts
4. If any ❌: Check MIGRATION_GUIDE.md troubleshooting section

---

**Created**: 2026-01-13
**Version**: 1.0

