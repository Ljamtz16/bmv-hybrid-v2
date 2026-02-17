# Manual execution - Run each command one by one

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MANUAL PROBWIN THRESHOLD TESTING" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You already have results for threshold 0.55 in evidence/weekly_analysis/" -ForegroundColor Green
Write-Host ""
Write-Host "To test other thresholds, run these commands manually:" -ForegroundColor Yellow
Write-Host ""

$thresholds = @(0.50, 0.52, 0.58, 0.60, 0.65, 0.70)

foreach ($t in $thresholds) {
    Write-Host "./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold $t --output_base evidence/probwin_tests/pw_$([int]($t*100))" -ForegroundColor White
}

Write-Host ""
Write-Host "Each command takes ~15 minutes. Run them one at a time." -ForegroundColor Yellow
Write-Host ""
Write-Host "After all complete, compare results with:" -ForegroundColor Yellow
Write-Host "  python compare_probwin_results.py" -ForegroundColor White
Write-Host ""
