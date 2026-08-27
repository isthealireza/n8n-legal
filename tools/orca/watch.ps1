# ---------------------------------------------------------------------------
# watch.ps1 -- folder-watch trigger: dispatch task files dropped in tasks/inbox/
#             to the Orca Orchestrator agent automatically.
#
# Modes:
#   powershell -File tools/orca/watch.ps1          # watch tasks/inbox/ forever
#   powershell -File tools/orca/watch.ps1 -Once    # sweep inbox once, then exit
#   powershell -File tools/orca/watch.ps1 -TaskFile tasks/inbox/x.md -Once
#                                                  # dispatch a single file, exit
#
# Lifecycle and duplicate prevention:
#   Dropping a file in tasks/inbox/ is the owner's approval to carry out the
#   task. A task file can produce both a Created and a Changed event, and more
#   than one watcher process could see the same file. Duplicate dispatch is
#   prevented by CLAIMING the task file before kickoff: the file is atomically
#   moved from tasks/inbox/ to tasks/queued/<name>.processing-<guid>.md.
#   Only the first claimant wins the move; every later claimant sees the source
#   gone and skips. The claim is the mechanism -- there is no debounce timer.
#
#   On success the claimed file is renamed to tasks/queued/<name>.dispatched-<HHmmss>.md.
#   On kickoff failure it is moved to tasks/done/<name>.FAILED and the failure
#   is appended to tasks/journal.txt. Task files are never deleted.
#
# Recovery after an unexpected shutdown: a file left as
# tasks/queued/<name>.processing-<guid>.md means the process died after the
# claim but before kickoff finished. It is not re-dispatched automatically (it
# is no longer in inbox); recover manually by moving it back to tasks/inbox/.
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
$journal = Join-Path $root 'tasks\journal.txt'
foreach ($d in @($inbox, $queued, $done)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# ---------------------------------------------------------------------------
# Claim-Task: atomically move the source file to tasks/queued/<base>.processing-<guid>.md.
# Returns the claimed path, or $null when another claimant already won (the
# source is gone) or the claim failed transiently (file still present -- a
# later event will retry). The atomic Move-Item is what makes "only one process
# can claim a task" true, across overlapping Created/Changed events and across
# concurrent watcher processes.
# ---------------------------------------------------------------------------
function Claim-Task([string]$path) {
  $base = [System.IO.Path]::GetFileNameWithoutExtension($path)
  $guid = [guid]::NewGuid().ToString('N')
  $claimed = Join-Path $queued "$base.processing-$guid.md"
  try {
    Move-Item -LiteralPath $path -Destination $claimed -ErrorAction Stop
    return $claimed
  } catch {
    if (Test-Path -LiteralPath $path) {
      Write-Host "[watch] claim failed (file still present, will retry on next event): $($_.Exception.Message)" -ForegroundColor Yellow
    }
    return $null
  }
}

# ---------------------------------------------------------------------------
# Dispatch-One: claim first, then kickoff the CLAIMED path, then rename to
# dispatched or move to done/FAILED. Every task file is handled independently:
# a failure in one task is contained here and never stops the loop or other
# tasks. Kickoff failures are never silently ignored -- they are journaled.
# ---------------------------------------------------------------------------
function Dispatch-One([string]$path) {
  $name = [System.IO.Path]::GetFileName($path)                       # e.g. task1.md
  $base = [System.IO.Path]::GetFileNameWithoutExtension($path)       # e.g. task1
  Write-Host "`n[watch] dispatching: $name"
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

  # 1. Claim BEFORE kickoff. If another event/process already claimed this
  #    file, skip it -- do NOT create a FAILED task for a duplicate event.
  $claimed = Claim-Task $path
  if (-not $claimed) {
    Write-Host "[watch] skip (already claimed or gone): $name"
    return
  }

  try {
    # 2. Dispatch using the CLAIMED path (task is already out of inbox).
    & (Join-Path $PSScriptRoot 'kickoff.ps1') -TaskFile $claimed -NoWait
    if ($LASTEXITCODE -ne 0) { throw "kickoff exited $LASTEXITCODE" }
    # 3. Success: rename claim -> dispatched.
    Move-Item -LiteralPath $claimed -Destination (Join-Path $queued "$base.dispatched-$((Get-Date -Format 'HHmmss')).md") -Force
    Add-Content $journal "$ts DISPATCHED $name" -Encoding utf8
  } catch {
    # 4. Failure after claim: claimed file -> done/<base>.FAILED, journal it.
    Write-Host "[watch] FAILED $name : $($_.Exception.Message)" -ForegroundColor Red
    try {
      Move-Item -LiteralPath $claimed -Destination (Join-Path $done "$base.FAILED") -Force
    } catch {
      Write-Host "[watch] could not move failed task to done/: $($_.Exception.Message)" -ForegroundColor Red
    }
    Add-Content $journal "$ts FAILED $name :: $($_.Exception.Message)" -Encoding utf8
  }
}

# --- Single-file mode -------------------------------------------------------
if ($TaskFile) {
  if (-not (Test-Path -LiteralPath $TaskFile)) { throw "Task file not found: $TaskFile" }
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
Write-Host "[watch] watching $inbox (drop .md/.txt/.markdown task files here). Ctrl+C to stop."
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $inbox
$watcher.Filter = '*.*'
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite
$watcher.EnableRaisingEvents = $true

# Events are processed SYNCHRONOUSLY in the main loop (no -Action blocks), so
# there are no overlapping handlers inside one process; the atomic claim makes
# it safe even across processes. Wait-Event is called in a loop so the watcher
# stays alive until Ctrl+C.
$null = Register-ObjectEvent $watcher 'Created' -SourceIdentifier 'Watch.Created'
$null = Register-ObjectEvent $watcher 'Changed' -SourceIdentifier 'Watch.Changed'

try {
  while ($true) {
    $evt = Wait-Event
    Remove-Event -EventIdentifier $evt.EventIdentifier -ErrorAction SilentlyContinue
    $path = $evt.SourceEventArgs.FullPath
    $change = $evt.SourceEventArgs.ChangeType
    if (($change -eq [System.IO.WatcherChangeTypes]::Created -or
         $change -eq [System.IO.WatcherChangeTypes]::Changed) -and
        (Test-Path -LiteralPath $path) -and
        ([System.IO.Path]::GetExtension($path) -in '.md', '.txt', '.markdown')) {
      Dispatch-One $path
    }
  }
} finally {
  Unregister-Event -SourceIdentifier 'Watch.Created' -ErrorAction SilentlyContinue
  Unregister-Event -SourceIdentifier 'Watch.Changed' -ErrorAction SilentlyContinue
  $watcher.EnableRaisingEvents = $false
  $watcher.Dispose()
}
