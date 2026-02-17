$csv = Import-Csv val\trade_plan.csv
Write-Host '=== TRADE PLAN SUMMARY ===' -ForegroundColor Green
Write-Host ''
Write-Host "Total Trades: $($csv.Count)"
$totalExp = ($csv | Measure-Object -Property position_cash -Sum).Sum
Write-Host "Total Exposure: `$$totalExp"
$avgProb = ($csv | Measure-Object -Property prob_win_cal -Average).Average
Write-Host "Avg P(win): $($avgProb.ToString('0.000'))"
Write-Host ''
$csv | Format-Table ticker, regime, prob_win_cal, qty, position_cash, exp_pnl_net -AutoSize
