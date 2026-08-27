# ---------------------------------------------------------------------------
# gate.ps1 -- pre-commit gate for the Orca agent loop.
#
# The Orca Orchestrator agent MUST run this before every commit. It enforces
# the AGENTS.md hard limits mechanically, so a wrong send never happens because
# an agent "forgot" a step. Exit 0 = safe to commit. Exit 1 = stop and fix.
#
# Gates enforced:
#   1. node harness/run.js  -> passed >= 81 AND failed <= 3 (baseline is
#      81 passed / 3 failed / 60 skipped; the 3 failures are real production
#      defects documented in harness/FINDINGS.md -- never weaken an assertion
#      to make them pass, and never introduce a 4th failure).
#   2. python3 .tooling/scrub.py        -> exit 0 (idempotent; applies the map)
#   3. .tooling/leak-check.sh (Git Bash)-> exit 0 (the secret gate)
#   4. Branch guard                     -> not on main/master (PRs only)
#   5. Active-export guard              -> no exports/wfN.active.json in the
#      diff: wfN.active.json changes ONLY when the owner publishes.
#   6. Secrets guard                    -> .mcp.json / .raw never staged.
#
# Usage (from the repo root of an Orca worktree):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/orca/gate.ps1
#   pwsh -NoProfile -File tools/orca/gate.ps1
# ---------------------------------------------------------------------------
# Note: do NOT use $ErrorActionPreference = 'Stop'. On Windows PowerShell 5.1
# that turns native stderr (e.g. git's CRLF warning) into a terminating error.
# We check $LASTEXITCODE explicitly after every external call instead.
$fail = $false
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $repoRoot

function Fail([string]$msg) {
  Write-Host "### GATE FAIL: $msg" -ForegroundColor Red
  $script:fail = $true
}

function Ok([string]$msg) {
  Write-Host "  [ok] $msg" -ForegroundColor Green
}

Write-Host "== Orca gate: $repoRoot =="

# --- 1. Harness -----------------------------------------------------------
Write-Host "`n[1/6] harness (node harness/run.js)"
$harnessOut = (& node harness/run.js 2>&1 | Out-String)
$exit = $LASTEXITCODE
$passed  = [regex]::Match($harnessOut, 'passed\s+(\d+)').Groups[1].Value
$failed  = [regex]::Match($harnessOut, 'failed\s+(\d+)').Groups[1].Value
$skipped = [regex]::Match($harnessOut, 'skipped\s+(\d+)').Groups[1].Value
if ($passed -eq '' -or $failed -eq '') {
  Fail "harness summary not parsed. Output was:`n$harnessOut"
} else {
  Write-Host "  passed=$passed failed=$failed skipped=$skipped (harness exit $exit)"
  $p = [int]$passed; $f = [int]$failed
  if ($p -lt 81) { Fail "harness passed count $p < 81 (regression)." }
  if ($f -gt 3)  { Fail "harness failed count $f > 3 (new failure). Baseline 3 are documented in harness/FINDINGS.md." }
  if ($p -ge 81 -and $f -le 3) { Ok "harness within baseline (passed>=81, failed<=3)." }
}

# --- 2. Scrub -------------------------------------------------------------
Write-Host "`n[2/6] scrub (python3 .tooling/scrub.py)"
& python3 .tooling/scrub.py 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "scrub.py exited $LASTEXITCODE." } else { Ok "scrub.py clean." }

# --- 3. Leak check --------------------------------------------------------
Write-Host "`n[3/6] leak-check (Git Bash .tooling/leak-check.sh)"
$gitBash = 'C:\Program Files\Git\bin\bash.exe'
if (-not (Test-Path $gitBash)) { $gitBash = (Get-Command bash -ErrorAction SilentlyContinue).Source }
if (-not $gitBash) { Fail "Git Bash not found; cannot run leak-check.sh." }
else {
  & $gitBash .tooling/leak-check.sh 2>&1 | Select-Object -Last 2 | ForEach-Object { Write-Host "  $_" }
  if ($LASTEXITCODE -ne 0) { Fail "leak-check.sh exited $LASTEXITCODE (secret gate)." } else { Ok "leak-check clean." }
}

# --- 4. Branch guard ------------------------------------------------------
Write-Host "`n[4/6] branch guard"
$branch = (& git rev-parse --abbrev-ref HEAD 2>&1 | Out-String).Trim()
Write-Host "  branch=$branch"
if ($branch -in @('main','master')) {
  Fail "on branch '$branch' -- never commit/push to main directly. Create a branch + PR."
} else { Ok "branch '$branch' (not main/master)." }

# --- 5. Active-export guard -----------------------------------------------
Write-Host "`n[5/6] active-export guard"
$changedActive = @()
$d1 = & git diff --name-only HEAD 2>$null
if ($LASTEXITCODE -eq 0) { $changedActive += $d1 | Where-Object { $_ -match '^exports/wf\d+\.active\.json$' } }
$d2 = & git diff --cached --name-only 2>$null
if ($LASTEXITCODE -eq 0) { $changedActive += $d2 | Where-Object { $_ -match '^exports/wf\d+\.active\.json$' } }
$changedActive = $changedActive | Where-Object { $_ } | Sort-Object -Unique
if ($changedActive.Count -gt 0) {
  Fail "diff touches active exports: $($changedActive -join ', '). wfN.active.json changes only when the OWNER publishes. Write draft changes to exports/wfN.draft.json instead."
} else { Ok "no wfN.active.json in diff." }

# --- 6. Secrets guard -----------------------------------------------------
Write-Host "`n[6/6] secrets guard"
$stagedSecrets = @()
$s = & git diff --cached --name-only 2>$null
if ($LASTEXITCODE -eq 0) {
  $stagedSecrets += $s | Where-Object { $_ -match '(^|/)(\.mcp\.json|\.raw/|.*\.unscrubbed\.json|.*\.raw\.json)$' }
}
$stagedSecrets = $stagedSecrets | Where-Object { $_ } | Sort-Object -Unique
if ($stagedSecrets.Count -gt 0) {
  Fail "staged files that must never be committed: $($stagedSecrets -join ', ')"
} else { Ok "no secrets staged." }

# ---------------------------------------------------------------------------
Write-Host ""
if ($fail) {
  Write-Host "GATE: FAILED -- do not commit." -ForegroundColor Red
  Pop-Location
  exit 1
}
Write-Host "GATE: PASSED -- safe to commit." -ForegroundColor Green
Pop-Location
exit 0
