# ============== Configuración ==============
$months = @("2025-02","2025-03","2025-04","2025-05","2025-06","2025-07")
$probs  = @(0.00, 0.55, 0.60)
$topns  = @(20, 12, 10)
$gates  = @("with_gate","no_gate")  # dos variantes de validación

# Parámetros MXN (mismos que vienes usando)
$sizingArgs = @(
  "--sizing","fixed_cash",
  "--fixed-cash","2000.0",
  "--fixed-shares","100",
  "--risk-pct","0.02",
  "--commission","5.0"
)

# Archivo agregado de resultados
$resultsCsv = "reports/forecast/grid_kpis_mxn.csv"
if (Test-Path $resultsCsv) { Remove-Item $resultsCsv }
"month,min_prob,topn,gate_variant,trades,winrate_pct,pnl_mxn,mdd_mxn,sharpe,expectancy_mxn,kpi_json" | Out-File -FilePath $resultsCsv -Encoding utf8

# ============== Loop principal ==============
foreach ($m in $months) {
  foreach ($p in $probs) {
    foreach ($t in $topns) {
      Write-Host "===== Mes=$m | min_prob=$p | topN=$t =====" -ForegroundColor Cyan

      # 1) Generar forecast con la config actual (esto escribe en reports/forecast/<mes>)
      python scripts/12_forecast_and_validate.py --month $m --use-return --infer-h 3 --min-prob $p --rank-topn $t

      # 2) Validar explícitamente ambas variantes de gate con los archivos ya generados
      foreach ($g in $gates) {
        python scripts/10_validate_month_forecast.py --month $m --variant $g

        $base = "reports/forecast/$m/validation"
        $tag  = "prob_$($p.ToString('0.##'))__topn_$t__gate_$g"

        # 3) KPIs MXN con los CSV de esa variante
        $csvTrades = "$base/validation_trades_$g.csv"
        $csvJoin   = "$base/validation_join_$g.csv"
        $outJson   = "$base/kpi_mxn__$tag.json"

        python scripts/kpi_validation_summary_mxn.py `
          --csv $csvTrades `
          --fallback-join $csvJoin `
          @sizingArgs `
          --out-json $outJson

        # 4) Leer JSON y agregar fila al CSV agregado
        if (Test-Path $outJson) {
          $k = Get-Content $outJson | ConvertFrom-Json
          $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}" -f `
            $m, $p, $t, $g, `
            $k."Total trades válidos", `
            $k."Porcentaje de aciertos", `
            $k."Ganancia total (MXN)", `
            $k."MDD (MXN)", `
            $k."Sharpe aprox", `
            $k."Ganancia promedio por trade (MXN)", `
            $outJson
          Add-Content -Path $resultsCsv -Value $line

          # (Opcional) Guardar artefactos por config para auditoría
          $cfgDir = "reports/forecast/$m/validation_configs/$tag"
          New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
          Copy-Item $csvTrades "$cfgDir/trades.csv" -Force
          Copy-Item $csvJoin   "$cfgDir/join.csv"   -Force
          Copy-Item $outJson   "$cfgDir/kpi_mxn.json" -Force
        }
      }
    }
  }
}

Write-Host "`nListo. Resultados agregados en: $resultsCsv" -ForegroundColor Green









# 1) Filtra por presupuesto diario (ej. $10,000) con $1,000 por trade, ordenando por EV
python .\scripts\11_filter_forecast_daily_budget.py `
  --in-csv reports/forecast/latest_forecast_with_returns.csv `
  --out-csv reports/forecast/latest_forecast_filtered.csv `
  --daily-budget-mxn 10000 `
  --per-trade-cash 2000 `
  --sort-by expected_value `
  --daily-topn 5   # o un tope, p.ej. 8

# 2) Copia el CSV filtrado a la carpeta del mes que se va a validar
Copy-Item reports/forecast/latest_forecast_filtered.csv "reports/forecast/$m/forecast_${m}_with_gate.csv" -Force

# 3) Corre la validación
python .\scripts\10_validate_month_forecast.py --month $m
