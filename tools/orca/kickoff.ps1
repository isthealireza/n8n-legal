# ---------------------------------------------------------------------------
# kickoff.ps1 -- manual trigger: dispatch a task to the Orca Orchestrator agent.
#
# Creates a fresh Orca worktree from the n8n-legal repo (base: dev/orca-setup),
# launches the Claude agent in it, and sends it the gated prompt from
# tools/orca/agent-prompt.md with the task description substituted in.
#
# Usage:
#   pwsh -File tools/orca/kickoff.ps1 -Task "Fix the WF2 test-data stamp guard"
#   pwsh -File tools/orca/kickoff.ps1 -TaskFile tasks/inbox/example.md
#   pwsh -File tools/orca/kickoff.ps1 -TaskFile tasks/inbox/example.md -NoWait
#
# Notes:
#   - The created worktree gets a copy of .mcp.json (n8n MCP access) ONLY if it
#     exists in the primary checkout. .mcp.json is gitignored; never commit it.
#   - -NoWait returns immediately after the prompt is sent; the agent runs in
#     the background and you watch it in Orca.
# ---------------------------------------------------------------------------
param(
  [Parameter(Mandatory = $true, ParameterSetName = 'inline')]
  [string]$Task,
  [Parameter(Mandatory = $true, ParameterSetName = 'file')]
  [string]$TaskFile,
  [switch]$NoWait
)

$ErrorActionPreference = 'Stop'

# --- Resolve the Orca CLI ------------------------------------------------
$orca = $env:ORCA_CLI_COMMAND
if (-not $orca) {
  $candidate = Get-Command orca -ErrorAction SilentlyContinue
  if ($candidate) { $orca = $candidate.Source }
}
if (-not $orca) { $orca = 'C:\Users\Alpha\AppData\Local\Programs\orca\resources\bin\orca.exe' }
if (-not (Test-Path $orca)) { throw "Orca CLI not found. Set ORCA_CLI_COMMAND or install Orca." }

# --- Repo / worktree identity --------------------------------------------
$repoId = 'a909e4c8-abba-4141-b63c-590883a1dd6c'   # n8n-legal (dev/orca-setup)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

# --- Resolve the task text ------------------------------------------------
if ($TaskFile) {
  if (-not (Test-Path $TaskFile)) { throw "Task file not found: $TaskFile" }
  $taskText = Get-Content $TaskFile -Raw
  $taskName = [System.IO.Path]::GetFileNameWithoutExtension($TaskFile)
} else {
  $taskText = $Task
  # derive a short kebab name from the task
  $words = ($Task -split '\s+' | Where-Object { $_ } | Select-Object -First 5) -join '-'
  $taskName = ($words -replace '[^A-Za-z0-9-]', '').ToLowerInvariant()
  if ([string]::IsNullOrWhiteSpace($taskName)) { $taskName = 'task' }
}
$worktreeName = "$taskName-$(Get-Date -Format 'HHmmss')"

# --- Build the prompt ------------------------------------------------------
$template = Get-Content (Join-Path $PSScriptRoot 'agent-prompt.md') -Raw
$prompt = $template -replace '<PUT TASK DESCRIPTION HERE — OR the owner''s task file content>', $taskText.Trim()

# --- Health check ----------------------------------------------------------
$status = & $orca status --json | ConvertFrom-Json
if ($status.result.runtime.reachable -ne $true) {
  throw "Orca runtime not reachable (state: $($status.result.runtime.state)). Open the Orca app first."
}
Write-Host "[ok] Orca runtime ready ($($status.result.runtime.appVersion))."

# --- Create the worktree with the Claude agent -----------------------------
Write-Host "[..] creating worktree '$worktreeName' with claude agent..."
$create = & $orca worktree create --repo "id:$repoId" --name $worktreeName --agent claude --prompt $prompt --json 2>&1 | Out-String
$createJson = $create | ConvertFrom-Json -ErrorAction SilentlyContinue
if (-not $createJson -or $createJson.ok -ne $true) {
  Write-Host "worktree create failed:`n$create" -ForegroundColor Red
  exit 1
}

$worktreeId = $createJson.result.worktree.id
$worktreePath = $createJson.result.worktree.path
$handle = $createJson.result.startupTerminal.handle
if (-not $handle) {
  $tl = & $orca terminal list --worktree $worktreeId --json | ConvertFrom-Json
  $handle = $tl.result.terminals[0].handle
}

Write-Host "[ok] worktree: $worktreeId"
Write-Host "[ok] terminal: $handle"

# --- Copy .mcp.json into the worktree if it exists (n8n MCP access) --------
$primaryMcp = Join-Path $repoRoot '.mcp.json'
if (Test-Path $primaryMcp) {
  $targetDir = if ($worktreePath) { $worktreePath } else { $repoRoot }
  Copy-Item $primaryMcp (Join-Path $targetDir '.mcp.json') -Force
  Write-Host "[ok] copied .mcp.json into $targetDir (gitignored, never committed)"
} else {
  Write-Host "[warn] .mcp.json not found in primary checkout; agent has no n8n MCP access" -ForegroundColor Yellow
}

Write-Host "`nDispatched. Watch the agent in Orca (worktree: $worktreeName)."
Write-Host "PR flow: agent runs tools/orca/gate.ps1 before each commit, then opens a PR."

if ($NoWait) { exit 0 }

# --- Optionally wait for the agent's first reply ----------------------------
Write-Host "Waiting for agent to start (Ctrl+C to stop waiting -- agent keeps running)..."
& $orca terminal wait --terminal $handle --for tui-idle --timeout-ms 60000 --json | Out-Null
Write-Host "Agent is up. Read output with: orca terminal read --terminal $handle --json"
