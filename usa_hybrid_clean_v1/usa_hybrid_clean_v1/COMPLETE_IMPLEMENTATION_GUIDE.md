# FASE 1-3 Complete Implementation Guide

**Project**: Swing + Fase 2 (Intraday Selectivo) Trading System  
**Status**: ✅ COMPLETE - Ready for Fase 2-3 Validation & Operation  
**Last Updated**: 2026-02-02

---

## Overview

Complete implementation of 3-phase trading system with capital management, risk controls, quality gates, and automated metrics collection.

### Phases

1. **FASE 1: Structure** (COMPLETE) - Weeks 1
   - CapitalManager (70% Swing / 30% Intraday buckets)
   - RiskManager (Daily/Weekly stops, Drawdown gate)
   - IntraDayGates (4-gate quality filter)
   - Global instances ready

2. **FASE 2: Validación** (IN PROGRESS) - Weeks 2-3
   - Metrics collection via MetricsTracker
   - Weekly reporting with decision support
   - API endpoints for monitoring
   - Decision criteria: Intraday PF > 1.15?

3. **FASE 3: Operación** (READY) - Weeks 4-12
   - Real money execution
   - Automated trade logging via API
   - 12-week validation period
   - Final decision: Fase 2 afinada vs Swing only

---

## Architecture Summary

```
┌─────────────────────────────────────────┐
│     FLASK DASHBOARD (8050)              │
│  ┌───────────────────────────────────┐  │
│  │  API Endpoints (5 new for 2-3)    │  │
│  │  ├─ /api/phase2/metrics           │  │
│  │  ├─ /api/phase2/weekly-report     │  │
│  │  ├─ /api/phase3/log-trade (POST)  │  │
│  │  ├─ /api/phase3/validation-plan   │  │
│  │  └─ /api/phase3/checklist         │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Core Components (Fase 1)         │  │
│  │  ├─ CapitalManager (70/30 buckets)│  │
│  │  ├─ RiskManager (Daily/Weekly/DD) │  │
│  │  ├─ IntraDayGates (4-gate filter) │  │
│  │  └─ MetricsTracker (New for 2-3) │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Data Sources                     │  │
│  │  ├─ trade_plan_EXECUTE.csv        │  │
│  │  ├─ trade_history_closed.csv      │  │
│  │  └─ standard_plan_*.csv           │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Logging                          │  │
│  │  └─ reports/logs/dashboard.log    │  │
│  │     [SWING] [INTRADAY]            │  │
│  │     [CAPITAL] [RISK] [PHASE3]     │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
        │
        ├─ Your Trading System
        ├─ Real Money Execution
        └─ Trade Close Events
```

---

## Files Delivered

### Main Application
- **[dashboard_unified_temp.py](dashboard_unified_temp.py)** (~3,900 lines)
  - Complete Flask dashboard
  - CapitalManager, RiskManager, IntraDayGates, MetricsTracker
  - 5 new API endpoints for Fase 2-3
  - Background tracking thread
  - Logging with file rotation

### Documentation (This Phase)
- **[FASE2_FASE3_IMPLEMENTATION.md](FASE2_FASE3_IMPLEMENTATION.md)** (~450 lines)
  - Complete API reference with JSON examples
  - Fase 2 validation checklist
  - Fase 3 operation workflow
  - Python integration examples

- **[FASE3_QUICK_START.md](FASE3_QUICK_START.md)** (~350 lines)
  - TL;DR quick reference
  - Curl commands for each endpoint
  - Weekly checklists
  - Troubleshooting guide
  - Decision template for Week 8-12

- **[FASE2_FASE3_SUMMARY.md](FASE2_FASE3_SUMMARY.md)** (This file)
  - High-level overview
  - Architecture diagram
  - Integration guide

### Example Scripts
- **[fase3_integration_example.py](fase3_integration_example.py)** (~350 lines)
  - Demonstrates all 5 endpoints
  - Simulates trade logging
  - Test metrics collection
  - Run with: `python fase3_integration_example.py`

### Previous Documentation
- **FASE1_IMPLEMENTATION.md** (if created earlier)
  - Detailed Fase 1 architecture
  - CapitalManager & RiskManager design
  - Test coverage (11/11 passing)

---

## Key Components Detail

### 1. CAPITAL_MANAGER
```python
CapitalManager(total=2000, swing_pct=70, intraday_pct=30)
├─ swing_bucket: $1,400 (max 4 positions, 3 concurrent)
├─ intraday_bucket: $600 (max 4 positions, 2 concurrent)
├─ Tracks: open positions, available capital
└─ Methods: allows(), add_open(), remove_open()
```

### 2. RISK_MANAGER
```python
RiskManager(capital_manager, total_capital=2000)
├─ Daily stop: -3% of intraday bucket
├─ Weekly stop: -6% of total capital
├─ Drawdown gate: -10% (kill-switch)
├─ Auto-reset: daily/weekly based on schedule
└─ Methods: is_intraday_enabled(), update_pnl()
```

### 3. INTRADAY_GATES (Function)
```python
intraday_gates_pass(signal_dict)
├─ Gate 1: Macro context (SPY/QQQ trend)
├─ Gate 2: Multi-TF alignment (signal coherence)
├─ Gate 3: Signal strength (confidence >= 50%)
├─ Gate 4: Risk/Reward (RR >= 1.5:1, SL <= 3%)
└─ Returns: (passed: bool, reason: str)
```

### 4. METRICS_TRACKER (New)
```python
MetricsTracker(capital_manager)
├─ swing_trades, intraday_trades: list of {ticker, side, entry, exit, pnl, ...}
├─ Methods:
│  ├─ log_trade(): Record closed trade
│  ├─ get_status(): Current metrics per book
│  ├─ get_weekly_report(): Weekly summary + recommendation
│  └─ _recalculate_stats(): Update PF, winrate, etc.
└─ Data: Per-book PF, winrate, DD, avg_win/loss
```

---

## Fase 2: Validation (Weeks 2-3)

### Goal
Confirm Swing profitability (PF > 1.05) and Intraday adds value (PF > 1.15) before real money.

### Workflow
1. Execute trades with historical/simulated data
2. Daily: Call `GET /api/phase2/metrics`
3. Weekly: Call `GET /api/phase2/weekly-report`
4. Monitor: Swing PF trending up, Intraday PF > 1.10
5. Decide: Continue to Fase 3?

### Success Criteria
- ✅ Swing PF > 1.05 (profitable)
- ✅ Intraday PF > 1.10 (showing promise)
- ✅ DD < 5% (acceptable risk)
- ✅ 20-30 total trades (meaningful sample)

### If Intraday PF < 0.90
→ Disable Intraday, Swing only for Fase 3

---

## Fase 3: Operación Real (Weeks 4-12)

### Goal
Execute with real money and decide on Fase 2 afinada implementation.

### Workflow

#### Week 4-7: Initial Operation
1. Start with real money
2. When trade closes: `POST /api/phase3/log-trade`
3. Dashboard updates metrics automatically
4. Monitor daily `/api/phase2/metrics`

#### Week 8: Checkpoint
1. Call `GET /api/phase3/validation-plan`
2. Check progress toward decision criteria
3. Verify: Intraday contributing value?

#### Week 12: Final Decision
1. Evaluate final metrics:
   - If Intraday PF > 1.25 & DD < 5% → **Fase 2 afinada** ✅
   - If Intraday PF < 1.05 → **Swing only** ✅
   - If 1.05 ≤ PF ≤ 1.25 → **Continue Fase 2 standard** ⚠️

2. Document decision & implement

### Decision Criteria Table

| Metric | Threshold | Result |
|--------|-----------|--------|
| Intraday PF | > 1.25 | Ready for advanced |
| Intraday DD | < 5% | Acceptable risk |
| Swing PF | > 1.05 | Profitable |
| Capital Growth | > 10% | Sustainable |

---

## API Quick Reference

### FASE 2 Endpoints

#### GET /api/phase2/metrics
```bash
curl http://localhost:8050/api/phase2/metrics | python -m json.tool
```
Returns: Current metrics for both books (trades, PnL, PF, winrate, DD)

#### GET /api/phase2/weekly-report
```bash
curl http://localhost:8050/api/phase2/weekly-report | python -m json.tool
```
Returns: Weekly summary + recommendation for next step

### FASE 3 Endpoints

#### POST /api/phase3/log-trade
```bash
curl -X POST http://localhost:8050/api/phase3/log-trade \
  -H "Content-Type: application/json" \
  -d '{
    "book": "swing",
    "ticker": "AAPL",
    "side": "BUY",
    "entry": 225.50,
    "exit": 232.25,
    "qty": 3,
    "pnl": 20.25,
    "reason": "TP"
  }'
```
Used for: Recording closed trades during real operation

#### GET /api/phase3/validation-plan
```bash
curl http://localhost:8050/api/phase3/validation-plan | python -m json.tool
```
Returns: Progress toward final decision (Week 8-12)

#### GET /api/phase3/checklist
```bash
curl http://localhost:8050/api/phase3/checklist | python -m json.tool
```
Returns: Pre-deployment readiness check

---

## Integration with Your System

### When Trade Closes
Your trading execution system should call:

```python
# Option 1: Direct (if same Python process)
from dashboard_unified_temp import METRICS_TRACKER

METRICS_TRACKER.log_trade(
    book='swing',
    ticker='AAPL',
    side='BUY',
    entry=225.50,
    exit_price=232.25,
    qty=3,
    pnl=20.25,
    reason_exit='TP'
)

# Option 2: HTTP (if different process)
import requests

requests.post('http://localhost:8050/api/phase3/log-trade', json={
    'book': 'swing',
    'ticker': 'AAPL',
    'side': 'BUY',
    'entry': 225.50,
    'exit': 232.25,
    'qty': 3,
    'pnl': 20.25,
    'reason': 'TP'
})
```

---

## Logging

### File Location
`reports/logs/dashboard.log` (with rotation: 10MB per file, 5 backups)

### Log Prefixes
```
[CAPITAL]   - Capital manager warnings (bucket overflow, limit exceeded)
[RISK]      - Risk manager triggers (daily stop, weekly stop, kill-switch)
[SWING]     - Swing trade actions
[INTRADAY]  - Intraday trade actions
[PHASE3]    - Operación real trade logging
[STARTUP]   - Dashboard startup events
[HTTP]      - API requests
```

### Example Log
```
2026-02-02 14:30:00 [INFO] [SWING] Trade closed: AAPL BUY @ 225.50 -> 232.25 (PnL: +20.25)
2026-02-02 14:31:15 [INFO] [INTRADAY] Trade closed: SPY BUY @ 510.30 -> 510.80 (PnL: +5.00)
2026-02-02 15:00:00 [INFO] [CAPITAL] Swing bucket available: 1,200 / 1,400
2026-02-02 16:45:00 [WARNING] [RISK] Daily PnL: -45.00, Intraday disabled until tomorrow
2026-02-02 17:30:00 [INFO] [PHASE3] Trade logged: swing AAPL, PnL=20.25
```

---

## Testing & Validation

### Unit Tests (From Fase 1)
- **test_capital_risk.py**: 11/11 tests PASSING ✅
  - Tests CapitalManager limits & bucket enforcement
  - Tests RiskManager daily/weekly stops
  - Tests IntraDayGates logic

### Integration Tests (From Fase 1)
- **example_integration.py**: 5/5 scenarios PASSING ✅
  - Scenario 1: Normal trade execution
  - Scenario 2: Capital limit enforcement
  - Scenario 3: Daily stop trigger
  - Scenario 4: Weekly stop trigger
  - Scenario 5: Gate failure (intraday rejected)

### Fase 2-3 Testing
- **fase3_integration_example.py**: Demonstrates all endpoints
  - Can be run standalone
  - Simulates trade logging
  - Verifies metrics collection

---

## Weekly Monitoring Checklist

### Monday (Inicio)
- [ ] Dashboard running: `python dashboard_unified_temp.py`
- [ ] Health check: `GET /api/health` returns 200
- [ ] Read metrics: `GET /api/phase2/metrics`

### Wednesday-Friday (Durante)
- [ ] Register trades: `POST /api/phase3/log-trade` for each close
- [ ] Monitor DD: Daily drawdown < limits?
- [ ] Check logs: `tail -f reports/logs/dashboard.log`

### Friday (Fin)
- [ ] Export report: `GET /api/phase2/weekly-report` → save JSON
- [ ] Analyze: PF trend, winrate, DD
- [ ] Document: Spreadsheet entry for week

### Week 8-12 (Decision)
- [ ] Get plan: `GET /api/phase3/validation-plan`
- [ ] Evaluate: Intraday PF vs threshold (1.25?)
- [ ] Decide: Fase 2 afinada, Swing only, or continue?

---

## Troubleshooting

### Dashboard Won't Start
```bash
# Check Python errors
python dashboard_unified_temp.py

# If port 8050 is in use:
netstat -an | grep 8050
# Kill process on that port and retry
```

### Metrics Not Updating
```bash
# Verify trade logging
tail -f reports/logs/dashboard.log | grep "Trade logged"

# Check POST body format
# Required fields: book, ticker, side, entry, exit, qty, pnl, reason
```

### Historical Data Missing
- Ensure `trade_plan_EXECUTE.csv` and `trade_history_closed.csv` exist
- Dashboard will show "empty_state": true if no trades found
- Start with at least 1 trade to begin metrics collection

---

## Next Steps

### Immediate (Today)
1. ✅ Review this guide
2. ✅ Run `python fase3_integration_example.py` to test API
3. ✅ Verify all endpoints respond with expected data

### This Week (Fase 2)
1. Execute trades (historical/simulated data)
2. Call `/api/phase2/metrics` daily
3. Call `/api/phase2/weekly-report` Friday
4. Evaluate: Intraday PF > 1.10?

### Next Week (Fase 3 Start)
1. Switch to real money execution
2. Call `POST /api/phase3/log-trade` on each trade close
3. Continue daily monitoring
4. Evaluate at week 8-12

### Week 8-12 (Final Decision)
1. Use `/api/phase3/validation-plan` to check progress
2. Evaluate decision criteria
3. Implement: Fase 2 afinada, Swing only, or continue

---

## Summary

**FASE 1-3 Implementation Complete!**

- ✅ CapitalManager: 70/30 buckets, position limits enforced
- ✅ RiskManager: Auto stop-losses, kill-switches active
- ✅ IntraDayGates: 4-gate quality filter implemented
- ✅ MetricsTracker: Track metrics separately by book
- ✅ API Endpoints: 5 endpoints for monitoring & logging
- ✅ Documentation: 3 guides + example scripts
- ✅ Testing: 11/11 unit tests + 5/5 integration scenarios PASSING
- ✅ Ready for: Weeks 2-12 validation & operation

**Now deploy and validate! 🚀**
