# ---------------------------------------------------------------------------
# watch.ps1 -- folder-watch trigger: dispatch task files dropped in tasks/inbox/
#             to the Fast Lane coordinator (tools/orca/fastlane.ps1).
#
# Modes:
#   powershell -File tools/orca/watch.ps1          # watch tasks/inbox/ forever
#   powershell -File tools/orca/watch.ps1 -Once    # sweep inbox once, then exit
#   powershell -File tools/orca/watch.ps1 -TaskFile tasks/inbox/x.md -Once
#                                                  # dispatch a single file, exit
#
# Lifecycle and duplicate prevention:
#   Dropping a file in tasks/inbox/ is the owner's single approval to carry out
#   the repository-only task (inspection, code changes, test scenarios, test
#   execution, branch, commit, one PR). fastlane.ps1 never re-asks during
#   repository-only work; it pauses only for n8n writes, publishing/
#   activation, active-export changes, external side effects, or scope changes.
#
#   A task file can produce both a Created and a Changed event, and more than
#   one watcher process could see the same file. Duplicate dispatch is
#   prevented by CLAIMING the task file before dispatch: the file is atomically
#   moved from tasks/inbox/ to tasks/queued/<name>.processing-<guid>.md.
#   Only the first claimant wins the move; every later claimant sees the source
#   gone and skips. The claim is the mechanism -- there is no debounce timer.
#
#   A Created event can fire while the task file is still being written.
#   Before claiming, Wait-Until-Ready requires the file's size and LastWriteTime
#   to remain unchanged across two samples (retrying up to 5s). A file that
#   never settles is NOT claimed or dispatched: it stays in inbox, is journaled
#   as UNREADY, and a later event (or sweep) retries it.
#
#   The claimed file is passed to fastlane.ps1, which OWNS the rest of the
#   lifecycle: on success it renames the claim to
#   tasks/queued/<name>.dispatched-<HHmmss>.md; on failure it moves it to
#   tasks/done/<name>.FAILED and journals FASTLANE FAILED. Task files are
#   never deleted.
#
# Recovery after an unexpected shutdown: a file left as
# tasks/queued/<name>.processing-<guid>.md means the process died after the
# claim but before fastlane finished. It is not re-dispatched automatically (it
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
# Wait-Until-Ready: wait for a task file to finish being written before it is
# claimed. A Created event can fire while the file is still being created, so
# claiming immediately risks dispatching partial task content to kickoff.
# The file is considered ready when its size AND LastWriteTime are unchanged
# across two consecutive samples. Returns $true when ready, $false when the
# file never settles within $timeoutMs (or disappears).
# ---------------------------------------------------------------------------
function Wait-Until-Ready([string]$path, [int]$timeoutMs = 5000) {
  $deadline = (Get-Date).AddMilliseconds($timeoutMs)
  $prev = $null
  while ((Get-Date) -lt $deadline) {
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try {
      $item = Get-Item -LiteralPath $path -ErrorAction Stop
    } catch {
      return $false
    }
    $now = @{ size = $item.Length; write = $item.LastWriteTime }
    if ($null -ne $prev -and $now.size -eq $prev.size -and $now.write -eq $prev.write) {
      return $true
    }
    $prev = $now
    Start-Sleep -Milliseconds 250
  }
  return $false
}

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
# Dispatch-One: claim first, then run fastlane.ps1 SYNCHRONOUSLY with the
# CLAIMED path. fastlane.ps1 must run in THIS process/terminal so it inherits
# the Orca terminal context: from a detached Start-Process child, `terminal
# create` and `check` lose the sender context and fail or race the UI
# adoption. Tasks are therefore serialised one at a time -- which AGENTS.md
# already requires for anything touching shared state. fastlane.ps1 owns the
# remaining lifecycle (run, legs, PR, rename to dispatched or move to
# done/FAILED, journaling); watch.ps1 only claims and invokes it.
#
# Every task file is handled independently: a failure in one task is contained
# here and never stops the loop or other tasks. Launch failures are never
# silently ignored -- they are journaled here.
# ---------------------------------------------------------------------------
function Dispatch-One([string]$path) {
  $name = [System.IO.Path]::GetFileName($path)                       # e.g. task1.md
  $base = [System.IO.Path]::GetFileNameWithoutExtension($path)       # e.g. task1
  Write-Host "`n[watch] dispatching: $name"
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

  # 0. Wait for the file to finish being written BEFORE claiming, so the
  #    coordinator never receives partial content. If it never settles, do NOT
  #    claim or dispatch it: record the failure, leave the file in inbox for a
  #    later event/sweep to retry.
  if (-not (Wait-Until-Ready $path)) {
    Write-Host "[watch] UNREADY $name : task file never became stable within 5s; left in inbox for retry" -ForegroundColor Yellow
    Add-Content $journal "$ts UNREADY $name :: task file never became stable (size/LastWriteTime kept changing); not dispatched, left in inbox" -Encoding utf8
    return
  }

  # 1. Claim BEFORE dispatch. If another event/process already claimed this
  #    file, skip it -- do NOT create a FAILED task for a duplicate event.
  $claimed = Claim-Task $path
  if (-not $claimed) {
    Write-Host "[watch] skip (already claimed or gone): $name"
    return
  }

  # 2. Run fastlane.ps1 synchronously in THIS process (inherits the Orca
  #    terminal context). It owns the task-file lifecycle from here on
  #    (dispatched rename or FAILED move, journaling, its own log under
  #    tasks/logs/).
  $fastlane = Join-Path $PSScriptRoot 'fastlane.ps1'
  try {
    & $fastlane -TaskFile $claimed
    if ($LASTEXITCODE -ne 0) { throw "fastlane exited $LASTEXITCODE" }
    Write-Host "[watch] task completed: $name"
  } catch {
    # 3. fastlane already moved the claim to done/<base>.FAILED and journaled
    #    FASTLANE FAILED. Only report launch-level failures here.
    Write-Host "[watch] task FAILED: $name : $($_.Exception.Message)" -ForegroundColor Red
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
