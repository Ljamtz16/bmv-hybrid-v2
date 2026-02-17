<#
.SYNOPSIS
  Registra tareas programadas en Windows para el ciclo diario y resumen semanal.

.PARAMETER DailyHour
  Hora (mercado) para la evaluación EOD. Default 16.

.PARAMETER DailyMinute
  Minuto (mercado) para la evaluación EOD. Default 10.

.PARAMETER WeeklyHour
  Hora (mercado) para el resumen semanal (viernes). Default 16.

.PARAMETER WeeklyMinute
  Minuto (mercado) para el resumen semanal (viernes). Default 20.

.PARAMETER MarketWindowsTz
  Zona horaria de Windows para el mercado ("Eastern Standard Time" para NY).

.PARAMETER WhatIf
  Muestra los comandos sin registrar las tareas.

#>
param(
  [int]$DailyHour = 16,
  [int]$DailyMinute = 10,
  [int]$DailySummaryHour = 16,
  [int]$DailySummaryMinute = 20,
  [int]$WeeklyHour = 16,
  [int]$WeeklyMinute = 20,
  # Inicio del monitor intradía en hora del mercado (NY)
  [int]$IntradayStartHour = 9,
  [int]$IntradayStartMinute = 30,
  [string]$MarketWindowsTz = 'Eastern Standard Time',
  [switch]$WhatIf
)

function Convert-MarketTimeToLocal([datetime]$marketDt, [string]$marketTzId) {
  $mtz = [System.TimeZoneInfo]::FindSystemTimeZoneById($marketTzId)
  $ltz = [System.TimeZoneInfo]::Local
  # Interpretar marketDt como hora en zona de mercado (Unspecified) y convertir a local
  $unspec = [datetime]::SpecifyKind($marketDt, [System.DateTimeKind]::Unspecified)
  return [System.TimeZoneInfo]::ConvertTime($unspec, $mtz, $ltz)
}

function New-MarketDate([datetime]$baseDate, [int]$hour, [int]$minute) {
  return [datetime]::new($baseDate.Year, $baseDate.Month, $baseDate.Day, $hour, $minute, 0)
}

function Get-NextDailyLocalTime($hour, $minute, $marketTzId) {
  $today = Get-Date
  $md = New-MarketDate $today $hour $minute
  $local = Convert-MarketTimeToLocal $md $marketTzId
  if ($local -lt (Get-Date)) {
    $md = $md.AddDays(1)
    $local = Convert-MarketTimeToLocal $md $marketTzId
  }
  return $local
}

function Get-NextWeeklyLocalTime($hour, $minute, $marketTzId, [System.DayOfWeek]$dow) {
  $d = Get-Date
  # construir fecha mercado para el próximo $dow
  $delta = ($dow.value__ - $d.DayOfWeek.value__)
  if ($delta -lt 0 -or ($delta -eq 0 -and $d.TimeOfDay -gt ([TimeSpan]::FromHours($hour) + [TimeSpan]::FromMinutes($minute)))) {
    $delta += 7
  }
  $targetBase = (Get-Date).AddDays($delta)
  $targetMarket = New-MarketDate $targetBase $hour $minute
  return (Convert-MarketTimeToLocal $targetMarket $marketTzId)
}

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ps1Daily = Join-Path $ROOT 'scripts/run_eod_eval.ps1'
$ps1DailySummary = Join-Path $ROOT 'scripts/run_daily_summary.ps1'
$ps1Weekly = Join-Path $ROOT 'scripts/run_weekly_summary.ps1'
$ps1Intraday = Join-Path $ROOT 'scripts/monitor_intraday.ps1'

$dailyLocal = Get-NextDailyLocalTime -hour $DailyHour -minute $DailyMinute -marketTzId $MarketWindowsTz
$dailySumLocal = Get-NextDailyLocalTime -hour $DailySummaryHour -minute $DailySummaryMinute -marketTzId $MarketWindowsTz
$weeklyLocal = Get-NextWeeklyLocalTime -hour $WeeklyHour -minute $WeeklyMinute -marketTzId $MarketWindowsTz -dow ([System.DayOfWeek]::Friday)
${intradayLocal} = Get-NextDailyLocalTime -hour $IntradayStartHour -minute $IntradayStartMinute -marketTzId $MarketWindowsTz

# Safe display strings for hour:minute
$dh = "{0:D2}:{1:D2}" -f $DailyHour, $DailyMinute
$wh = "{0:D2}:{1:D2}" -f $WeeklyHour, $WeeklyMinute
$dsh = "{0:D2}:{1:D2}" -f $DailySummaryHour, $DailySummaryMinute

$tnDaily = 'HybridClean_Daily_EOD_Evaluate'
$tnDailySummary = 'HybridClean_Daily_Summary'
$tnWeekly = 'HybridClean_Weekly_Summary'
$tnIntraday = 'HybridClean_Intraday_Monitor'

$cmdDaily  = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ps1Daily`""
$cmdDailySummary = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ps1DailySummary`" -SendText"
$cmdWeekly = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ps1Weekly`" -SendText"
$cmdIntraday = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ps1Intraday`""

Write-Host "[schedule] Diario (mercado $dh -> local $($dailyLocal.ToString('HH:mm'))): $tnDaily"
Write-Host "[schedule] Resumen diario (mercado $dsh -> local $($dailySumLocal.ToString('HH:mm'))): $tnDailySummary"
Write-Host "[schedule] Semanal viernes (mercado $wh -> local $($weeklyLocal.ToString('HH:mm'))): $tnWeekly"
Write-Host "[schedule] Monitor intradía (mercado $($IntradayStartHour.ToString('D2')):$($IntradayStartMinute.ToString('D2')) -> local $(${intradayLocal}.ToString('HH:mm'))): $tnIntraday"

if ($WhatIf) {
  Write-Host "[whatif] schtasks /Create /SC DAILY   /TN $tnDaily  /TR $cmdDaily  /ST $($dailyLocal.ToString('HH:mm')) /F"
  Write-Host "[whatif] schtasks /Create /SC DAILY   /TN $tnDailySummary  /TR $cmdDailySummary  /ST $($dailySumLocal.ToString('HH:mm')) /F"
  Write-Host "[whatif] schtasks /Create /SC WEEKLY /D FRI /TN $tnWeekly /TR $cmdWeekly /ST $($weeklyLocal.ToString('HH:mm')) /F"
  Write-Host "[whatif] schtasks /Create /SC DAILY   /TN $tnIntraday /TR $cmdIntraday /ST $(${intradayLocal}.ToString('HH:mm')) /F"
  return
}

schtasks /Create /SC DAILY   /TN $tnDaily  /TR $cmdDaily  /ST $($dailyLocal.ToString('HH:mm')) /F | Out-Null
schtasks /Create /SC DAILY   /TN $tnDailySummary  /TR $cmdDailySummary  /ST $($dailySumLocal.ToString('HH:mm')) /F | Out-Null
schtasks /Create /SC WEEKLY /D FRI /TN $tnWeekly /TR $cmdWeekly /ST $($weeklyLocal.ToString('HH:mm')) /F | Out-Null
schtasks /Create /SC DAILY   /TN $tnIntraday /TR $cmdIntraday /ST $(${intradayLocal}.ToString('HH:mm')) /F | Out-Null

Write-Host "[schedule] Tareas registradas. Puedes verlas en el Programador de tareas."
