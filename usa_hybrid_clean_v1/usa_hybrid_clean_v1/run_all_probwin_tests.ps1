# Script para ejecutar pruebas de diferentes umbrales de prob_win
# Ejecuta cada umbral secuencialmente y guarda resultados

$thresholds = @(0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70)

Write-Host "============================================================================================================" -ForegroundColor Cyan
Write-Host "TESTING MULTIPLE PROB_WIN THRESHOLDS - SEQUENTIAL EXECUTION" -ForegroundColor Cyan
Write-Host "============================================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Thresholds to test: $($thresholds -join ', ')" -ForegroundColor Yellow
Write-Host "Total tests: $($thresholds.Count)"
Write-Host "Estimated time: ~$($thresholds.Count * 15) minutes"
Write-Host ""

$results = @()

foreach ($threshold in $thresholds) {
    $index = [array]::IndexOf($thresholds, $threshold) + 1
    
    Write-Host ""
    Write-Host "============================================================================================================" -ForegroundColor Green
    Write-Host "[$index/$($thresholds.Count)] TESTING PROB_WIN >= $threshold" -ForegroundColor Green
    Write-Host "============================================================================================================" -ForegroundColor Green
    
    $startTime = Get-Date
    
    & ./.venv/Scripts/python.exe test_single_threshold.py $threshold
    
    $elapsed = (Get-Date) - $startTime
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Completed in $([int]$elapsed.TotalMinutes) min $([int]$elapsed.Seconds) sec" -ForegroundColor Green
    } else {
        Write-Host "[X] Failed with exit code $LASTEXITCODE" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================================================================================" -ForegroundColor Cyan
Write-Host "ALL TESTS COMPLETED" -ForegroundColor Cyan
Write-Host "============================================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Results stored in: evidence/probwin_tests/" -ForegroundColor Yellow
Write-Host ""
Write-Host "To compare results, run:" -ForegroundColor Yellow
Write-Host "  python compare_probwin_results.py" -ForegroundColor White
Write-Host ""
