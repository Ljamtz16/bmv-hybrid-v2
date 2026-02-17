param(
  [ValidateSet('Soft','Hard')]
  [string]$Mode = 'Soft',
  [switch]$DryRun,
  [switch]$NoBackup,
  [switch]$Yes
)

# Resolve repo root (one level up from scripts folder)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "Repo root:" $RepoRoot -ForegroundColor Cyan
Write-Host "Mode:" $Mode " DryRun:" $DryRun " NoBackup:" $NoBackup -ForegroundColor Cyan

# Ensure we never delete raw data or config
$protect = @('data', 'config')

# Targets to clean
$targets = @(
  @{ Path = 'outputs';       Type='dir';  What='generated outputs (CSV/JSON/progress_series/etc.)';         Mode='Soft' },
  @{ Path = 'tmp';           Type='dir';  What='temporary logs and scratch';                               Mode='Soft' },
  @{ Path = 'snapshots';     Type='dir';  What='snapshots';                                                Mode='Soft' },
  @{ Path = 'catboost_info'; Type='dir';  What='CatBoost training logs';                                   Mode='Soft' },
  @{ Path = 'reports';       Type='dir';  What='generated reports/plots';                                  Mode='Soft' },
  @{ Path = 'val';           Type='dir';  What='validation artifacts (oos predictions, trade plans, etc.)'; Mode='Soft' },
  @{ Path = 'models';        Type='dir';  What='trained models';                                           Mode='Hard' }
)

# Backup selection
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $RepoRoot 'backup'
$backupZip = Join-Path $backupDir ("cleanup_" + $stamp + ".zip")

function New-DirIfMissing([string]$p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

function Describe-Plan {
  Write-Host "\nPlanned cleanup:" -ForegroundColor Yellow
  foreach ($t in $targets) {
    if ($Mode -eq 'Hard' -or $t.Mode -eq 'Soft') {
      $p = Join-Path $RepoRoot $t.Path
      if (Test-Path $p) {
        Write-Host " - " $t.Path ":" $t.What -ForegroundColor Gray
      }
    }
  }
  Write-Host " - __pycache__ directories (recursive)" -ForegroundColor Gray
}

function Backup-Targets {
  if ($NoBackup) { return }
  New-DirIfMissing $backupDir
  $toBackup = New-Object System.Collections.Generic.List[string]
  foreach ($t in $targets) {
    if ($Mode -eq 'Hard' -or $t.Mode -eq 'Soft') {
      $p = Join-Path $RepoRoot $t.Path
      if (Test-Path $p) { $toBackup.Add($p) }
    }
  }
  # Add __pycache__ folders (exclude .venv and backup)
  $pyc = Get-ChildItem -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\backup\\" } |
    Select-Object -ExpandProperty FullName
  if ($pyc) { foreach ($p in $pyc) { $toBackup.Add([string]$p) } }

  if ($toBackup.Count -eq 0) {
    Write-Host "Nothing to backup." -ForegroundColor DarkYellow
    return
  }

  Write-Host ("Creating backup: " + $backupZip) -ForegroundColor Green
  if ($DryRun) {
    $toBackup | ForEach-Object { Write-Host "   would include:" $_ -ForegroundColor DarkGreen }
  } else {
    if (Test-Path $backupZip) { Remove-Item $backupZip -Force }
    # Compress-Archive has path length limits; compress parent folder items one by one
    $tempList = Join-Path $backupDir ("list_" + $stamp + ".txt")
    $toBackup | Set-Content -Path $tempList
    foreach ($item in $toBackup) {
      $relative = Resolve-Path $item | ForEach-Object { $_.Path.Replace($RepoRoot + '\\', '') }
      Write-Host "   adding" $relative -ForegroundColor DarkGreen
    }
    Compress-Archive -Path $toBackup -DestinationPath $backupZip -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $backupZip)) {
      Write-Host "Backup zip failed with Compress-Archive; skipping archive step." -ForegroundColor DarkYellow
    }
  }
}

function Remove-Contents([string]$dir) {
  if (-not (Test-Path $dir)) { return }
  # Keep the directory, remove files and subdirs
  Get-ChildItem -Force -LiteralPath $dir | ForEach-Object {
    if ($DryRun) {
      Write-Host ("   would remove: " + $_.FullName) -ForegroundColor DarkRed
    } else {
      try { Remove-Item -Recurse -Force -LiteralPath $_.FullName -ErrorAction Stop } catch { Write-Host $_ -ForegroundColor Red }
    }
  }
}

function Do-Cleanup {
  Write-Host "\nExecuting cleanup..." -ForegroundColor Yellow

  foreach ($t in $targets) {
    if ($Mode -eq 'Hard' -or $t.Mode -eq 'Soft') {
      $p = Join-Path $RepoRoot $t.Path
      if (Test-Path $p) {
        # Always preserve protected roots
        if ($protect -contains $t.Path) { continue }
        Write-Host (" - cleaning " + $t.Path) -ForegroundColor Gray
        Remove-Contents $p
      }
    }
  }

  # __pycache__ folders
  $pycDirs = Get-ChildItem -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\backup\\" }
  foreach ($d in $pycDirs) {
    if ($DryRun) {
      Write-Host ("   would remove: " + $d.FullName) -ForegroundColor DarkRed
    } else {
      try { Remove-Item -Recurse -Force -LiteralPath $d.FullName -ErrorAction Stop } catch { Write-Host $_ -ForegroundColor Red }
    }
  }
}

Describe-Plan

if (-not $Yes) {
  $q = Read-Host "Proceed with cleanup? (y/N)"
  if ($q -notin @('y','Y','yes','YES')) { Write-Host "Aborted."; exit 1 }
}

Backup-Targets
Do-Cleanup

Write-Host "\nCleanup complete." -ForegroundColor Green
if (-not $NoBackup) { Write-Host "Backup (if created): $backupZip" -ForegroundColor DarkGreen }
