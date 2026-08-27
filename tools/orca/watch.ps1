# ---------------------------------------------------------------------------
# watch.ps1 -- folder-watch trigger: dispatch task files dropped in tasks/inbox/
#             to the Orca Orchestrator agent automatically.
#
# Modes:
#   pwsh -File tools/orca/watch.ps1            # watch tasks/inbox/ forever
#   pwsh -File tools/orca/watch.ps1 -Once      # sweep inbox once, then exit
#   pwsh -File tools/orca/watch.ps1 -TaskFile tasks/inbox/x.md -Once
#                                             # dispatch a single file and exit
#
# Lifecycle: a file dropped in tasks/inbox/ is read, dispatched via kickoff.ps1,
# and moved to tasks/queued/ (success) or tasks/done/<name>.FAILED (failure).
# The file itself is the approval: dropping it is the owner approving the task.
# ---------------------------------------------------------------------------
param(
  [switch]$Once,
  [string]$TaskFile
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$inbox = Join-Path $root 'tasks\inbox'
$queued = Join-Path $root 'tasks\queued'
$done = Join-Path $root 'tasks\done'
foreach ($d in @($inbox, $queued, $done)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

function Dispatch-One([string]$path) {
  $name = [System.IO.Path]::GetFileName($path)
  Write-Host "`n[watch] dispatching: $name"
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  try {
    & (Join-Path $PSScriptRoot 'kickoff.ps1') -TaskFile $path -NoWait
    if ($LASTEXITCODE -ne 0) { throw "kickoff exited $LASTEXITCODE" }
    Move-Item $path (Join-Path $queued "$name.dispatched-$((Get-Date -Format 'HHmmss')).md") -Force
    Add-Content (Join-Path $root 'tasks\journal.txt') "$ts DISPATCHED $name" -Encoding utf8
  } catch {
    Write-Host "[watch] FAILED $name : $($_.Exception.Message)" -ForegroundColor Red
    Move-Item $path (Join-Path $done "$name.FAILED") -Force
    Add-Content (Join-Path $root 'tasks\journal.txt') "$ts FAILED $name :: $($_.Exception.Message)" -Encoding utf8
  }
}

# --- Single-file mode -------------------------------------------------------
if ($TaskFile) {
  if (-not (Test-Path $TaskFile)) { throw "Task file not found: $TaskFile" }
  Dispatch-One (Resolve-Path $TaskFile).Path
  exit 0
}

# --- One sweep mode ----------------------------------------------------------
if ($Once) {
  Get-ChildItem $inbox -File | Where-Object { $_.Extension -in '.md', '.txt', '.markdown' } |
    Sort-Object LastWriteTime | ForEach-Object { Dispatch-One $_.FullName }
  Write-Host "[watch] sweep complete."
  exit 0
}

# --- Continuous watch mode ----------------------------------------------------
Write-Host "[watch] watching $inbox (drop .md/.txt task files here). Ctrl+C to stop."
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $inbox
$watcher.Filter = '*.*'
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite
$watcher.EnableRaisingEvents = $true

$action = {
  $path = $Event.SourceEventArgs.FullPath
  $change = $Event.SourceEventArgs.ChangeType
  Start-Sleep -Milliseconds 300   # let the file finish writing
  if ($change -in @('Created', 'Changed') -and (Test-Path $path) -and
      [System.IO.Path]::GetExtension($path) -in '.md', '.txt', '.markdown') {
    & (Join-Path $PSScriptRoot 'watch.ps1') -TaskFile $path -Once
  }
}
Register-ObjectEvent $watcher 'Created' -Action $action | Out-Null
Register-ObjectEvent $watcher 'Changed' -Action $action | Out-Null

try {
  Wait-Event   # block forever; events are handled by the actions
} finally {
  $watcher.EnableRaisingEvents = $false
  $watcher.Dispose()
}
