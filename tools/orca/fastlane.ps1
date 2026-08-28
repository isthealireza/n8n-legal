# ---------------------------------------------------------------------------
# fastlane.ps1 -- Fast Lane coordinator for ONE owner-approved task card.
#
# The task card (already claimed by watch.ps1 and passed as -TaskFile) IS the
# single owner approval for a repository-only task. It covers repository
# inspection, code changes, test scenario authoring, test execution, branch,
# commit, and one pull request. The coordinator never asks for approval again
# for repository-only work, and never pauses for manual terminal interaction.
#
# Architecture -- Claude is the Orchestrator (AGENTS.md §4):
#   task card
#     -> script (this file) sets up: ONE fresh Orca worktree with an
#        agent-first Claude terminal, an opencode (DeepSeek) terminal, a Codex
#        terminal, a Run bound to CLAUDE's terminal, and three worker tasks
#        (owner-gate, test-deepseek, review-codex).
#     -> script sends the ORCHESTRATOR prompt (tools/orca/orchestrator-prompt.md
#        + the owner's task card) to Claude's terminal.
#     -> CLAUDE orchestrates, as the Run's coordinator:
#          implements the change itself (harness, scrub, gate, commit)
#          stops for Ali via a DECISION GATE on the owner-gate task
#          (orca orchestration gate-create --task <owner-gate> --question ...)
#          before ANY protected n8n action -- never via `ask`, which is
#          worker-to-coordinator only and fails from the coordinator
#          (dispatch_inactive, proven 2026-08-28 on the PR #12 run)
#          dispatches DeepSeek -> authors + runs test scenarios -> result file
#          dispatches Codex    -> reviews diff + test evidence -> APPROVE/REFUTE
#          bounded REFUTE loop (fix, re-dispatch, max 2 rounds)
#          writes a DONE file with the full report
#     -> script polls for the DONE file (never touches the Run mailbox -- a
#        second mailbox consumer would race the acks), then pushes the branch
#        and creates ONE PR (gh pr create).
#
# When the task card declares "N8N-ACCESS: REQUIRED", the script copies the
# primary checkout's .mcp.json into the worktree so Claude can inspect the live
# n8n instance with the full existing connection. There is no command-line
# override: the card marker is the only trigger, so credential copying is always
# card-declared (Codex REFUTE, 2026-08-28). The file is gitignored, never
# committed, never printed, and covered by the gate's secrets guard -- see the
# [mcp] block in the body.
#
# Pauses ONLY for the protected-action set (n8n write, publishing/activation,
# active-export change, external message/side effect, irreversible action,
# scope change). A worker that hits one sends `ask`; the owner answers in the
# Orca UI and the flow resumes automatically.
#
# worker-start is deliberately NOT used: on this host its composed prompt
# injection races the agent boot and revokes the dispatch capability
# (agent_prompt_stalled). Terminals are created agent-first / in the settled
# worktree, and prompts are delivered with `terminal send` or `dispatch
# --inject` -- the proven paths.
#
# Usage:
#   pwsh -File tools/orca/fastlane.ps1 -TaskFile tasks/queued/<name>.processing-<guid>.md
#   pwsh -File tools/orca/fastlane.ps1 -TaskFile tasks/inbox/example.md -RefuteRounds 2
#
# Exit 0 = one PR created. Exit 1 = failed (task moved to tasks/done/<name>.FAILED).
# Every step is journaled to tasks/journal.txt and tasks/logs/.
# ---------------------------------------------------------------------------
param(
  [Parameter(Mandatory = $true)][string]$TaskFile,
  [int]$RefuteRounds = 2,
  [int]$LegTimeoutSec = 1800
)

# NOTE: do NOT use $ErrorActionPreference = 'Stop'. On Windows PowerShell 5.1
# that turns native stderr (e.g. `check --wait`'s JSON keepalive lines, git
# warnings) into a terminating error. Invoke-Orca checks $LASTEXITCODE
# explicitly instead, exactly like gate.ps1 does.
$ErrorActionPreference = 'Continue'

# --- Resolve the Orca CLI (same logic as kickoff.ps1) ---------------------
$orca = $env:ORCA_CLI_COMMAND
if (-not $orca) {
  $candidate = Get-Command orca -ErrorAction SilentlyContinue
  if ($candidate) { $orca = $candidate.Source }
}
if (-not $orca) { $orca = 'C:\Users\Alpha\AppData\Local\Programs\orca\resources\bin\orca.exe' }
if (-not (Test-Path $orca)) { throw "Orca CLI not found. Set ORCA_CLI_COMMAND or install Orca." }

$repoId = 'a909e4c8-abba-4141-b63c-590883a1dd6c'   # n8n-legal
$root    = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$queued  = Join-Path $root 'tasks\queued'
$done    = Join-Path $root 'tasks\done'
$logDir  = Join-Path $root 'tasks\logs'
$journal = Join-Path $root 'tasks\journal.txt'
foreach ($d in @($queued, $done, $logDir)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

$taskName = [System.IO.Path]::GetFileNameWithoutExtension($TaskFile)
# watch.ps1 claims inbox files as <name>.processing-<guid>.md -- strip that
# suffix so worktree/PR/log names stay clean and the final rename matches the
# original task name.
$taskName = $taskName -replace '\.processing-[0-9a-f]+$', ''
if ([string]::IsNullOrWhiteSpace($taskName)) { $taskName = 'task' }
$ts       = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$stamp    = Get-Date -Format 'HHmmss'
$logFile  = Join-Path $logDir "$taskName.fastlane-$stamp.log"

# --- Logging ----------------------------------------------------------------
function Log([string]$msg) {
  $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
  Write-Host $line
  Add-Content -Path $logFile -Value $line -Encoding utf8
}
function Journal([string]$msg) {
  Add-Content -Path $journal -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" -Encoding utf8
}

# --- Orca invocation helper -------------------------------------------------
# Windows PowerShell 5.1 strips embedded double quotes when passing args to
# native executables, splitting the argument. Escape every value:  " -> \"
# so the CLI's CommandLineToArgvW parsing receives the literal quote.
#
# fastlane.ps1 usually runs as a DETACHED background process (spawned by
# watch.ps1 via Start-Process), which is never itself a live Orca terminal.
# The CLI therefore cannot auto-resolve a sender for orchestration commands;
# every orchestration call must carry --from <coordinator-handle>. The handle
# is resolved once at startup and injected automatically below.
$script:coordinatorHandle = $null

function Invoke-Orca([string[]]$Argv) {
  # Auto-inject --from for orchestration commands when we have a coordinator
  # handle and the caller did not already pass one. `check` is the exception:
  # it does NOT accept --from (verified against this CLI), and with an explicit
  # --run it does not need a sender. Only inject for subcommands that accept
  # --from (run-create, task-*, dispatch, send, ask, reply, worker-*).
  $sub = if ($Argv.Count -ge 2 -and $Argv[0] -eq 'orchestration') { $Argv[1] } else { $null }
  $injectable = $sub -and ($sub -notin @('check','inbox')) -and $script:coordinatorHandle -and ($Argv -notcontains '--from')
  $argv2 = $Argv
  if ($injectable) {
    $argv2 = @()
    for ($i = 0; $i -lt $Argv.Count; $i++) {
      $argv2 += $Argv[$i]
      if ($i -eq 1) { $argv2 += '--from'; $argv2 += $script:coordinatorHandle }
    }
  }
  $escaped = foreach ($a in $argv2) { if ($a) { $a -replace '"', '\"' } else { $a } }
  # The orca CLI occasionally exits 1 while its JSON payload says ok:true --
  # a Windows console-handle artifact (PostQueuedCompletionStatus / invalid
  # handle) under the harness, not a real failure. The payload is authoritative:
  # parse it, and if ok:true treat the call as succeeded regardless of exit
  # code. Stderr is captured to a temp file, NOT via 2>&1, because PS 5.1
  # turns native stderr lines into spurious NativeCommandError exceptions.
  $maxAttempts = 4
  $attempt = 0
  while ($true) {
    $attempt++
    $stderrFile = Join-Path $env:TEMP ("fastlane-err-" + [guid]::NewGuid().ToString('N') + ".txt")
    $stdout = & $orca $escaped 2>$stderrFile | Out-String
    $exit = $LASTEXITCODE
    $errText = ''
    if (Test-Path $stderrFile) { $errText = (Get-Content $stderrFile -Raw) -join "`n"; Remove-Item $stderrFile -Force -ErrorAction SilentlyContinue }
    $parsed = $null
    if ($stdout) { try { $parsed = $stdout | ConvertFrom-Json } catch { $parsed = $null } }
    if ($exit -eq 0) {
      if (-not $stdout) { return $null }
      return $parsed
    }
    # Exit 1 but a success payload: console-handle artifact, accept it.
    if ($parsed -and $parsed.ok -eq $true) {
      Log "note: orca exit $exit but payload ok:true -- treating as success ($($Argv -join ' '))"
      return $parsed
    }
    # Transient runtime unresponsiveness: bounded retry with backoff.
    $transient = $errText -match 'runtime_timeout|runtime_unavailable|Timed out waiting for the Orca runtime|handle is invalid'
    if ($attempt -ge $maxAttempts -or $sub -eq 'check' -or -not $transient) {
      throw "orca $($Argv -join ' ') exited $exit`n$errText`n$stdout"
    }
    Log "note: transient Orca runtime error, retry $attempt/${maxAttempts}: $errText"
    Start-Sleep -Seconds ([Math]::Min(30, 5 * $attempt))
  }
}

function Resolve-Coordinator {
  if ($env:ORCA_TERMINAL_HANDLE) {
    $script:coordinatorHandle = $env:ORCA_TERMINAL_HANDLE
    Log "Coordinator handle (env): $script:coordinatorHandle"
    return
  }
  try {
    $tl = Invoke-Orca @('terminal','list','--worktree','current','--json')
    $t = $tl.result.terminals | Where-Object { $_.connected -eq $true -and $_.writable -eq $true } | Select-Object -First 1
    if ($t) {
      $script:coordinatorHandle = $t.handle
      Log "Coordinator handle (terminal list): $script:coordinatorHandle"
    } else {
      Log "WARNING: no live writable terminal found; orchestration calls may fail without --from."
    }
  } catch {
    Log "WARNING: could not resolve coordinator handle: $($_.Exception.Message)"
  }
}

function Get-RunId { param($objective, [string]$from = '')
  if ($from) {
    $res = Invoke-Orca @('orchestration','run-create','--objective',$objective,'--from',$from,'--json')
  } else {
    $res = Invoke-Orca @('orchestration','run-create','--objective',$objective,'--json')
  }
  return $res.result.run.id
}

function New-Task { param($run, $title, $spec, [string]$deps = '')
  $argv = @('orchestration','task-create','--run',$run,'--task-title',$title,'--spec',$spec,'--json')
  if ($deps) { $argv = @('orchestration','task-create','--run',$run,'--task-title',$title,'--deps',$deps,'--spec',$spec,'--json') }
  $res = Invoke-Orca $argv
  return $res.result.task.id
}

function Update-Task { param($id, $status, [string]$resultJson = '')
  $argv = @('orchestration','task-update','--id',$id,'--status',$status,'--json')
  if ($resultJson) { $argv = @('orchestration','task-update','--id',$id,'--status',$status,'--result',$resultJson,'--json') }
  Invoke-Orca $argv | Out-Null
}

function New-Terminal { param($worktreeSelector, $title, $command, [string]$agentHint = '')
  # From a DETACHED process (watch.ps1 -> Start-Process) `terminal create` can
  # time out waiting for the Orca UI to adopt the visible tab ("Timed out
  # waiting for terminal handle after creation") even though the terminal IS
  # created. Resolve the handle afterwards via terminal list instead of
  # failing. The fresh worktree also has a DEFAULT SHELL terminal (title
  # "Terminal 1" or empty) from `worktree create`, so pick the terminal that
  # was NOT present before this create call -- never the newest non-shell one,
  # which can be a sibling worker terminal created moments earlier (that bug
  # made the codex leg resolve to the opencode terminal).
  $before = @()
  try {
    $tl0 = Invoke-Orca @('terminal','list','--worktree',$worktreeSelector,'--json')
    $before = @($tl0.result.terminals | ForEach-Object { $_.handle })
  } catch { $before = @() }
  $handle = $null
  try {
    $res = Invoke-Orca @('terminal','create','--worktree',$worktreeSelector,'--title',$title,'--command',$command,'--json')
    if ($res -and $res.result -and $res.result.terminal -and $res.result.terminal.handle) { $handle = $res.result.terminal.handle }
    else { Log "note: terminal create returned no handle for '$title'; resolving via list." }
  } catch {
    Log "note: terminal create did not return a handle for '$title': $($_.Exception.Message)"
  }
  if (-not $handle) {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline -and -not $handle) {
      Start-Sleep -Seconds 5
      try {
        $tl = Invoke-Orca @('terminal','list','--worktree',$worktreeSelector,'--json')
        $candidates = $tl.result.terminals |
             Where-Object { $_.connected -eq $true -and $_.writable -eq $true -and ($before -notcontains $_.handle) }
        # 1) a NEW terminal whose title mentions the agent (claude/codex/opencode)
        if ($agentHint) {
          $t = $candidates | Where-Object { $_.title -and $_.title -match $agentHint } |
               Sort-Object lastOutputAt -Descending | Select-Object -First 1
          if ($t) { $handle = $t.handle; break }
        }
        # 2) any NEW non-shell terminal (a real title, not "Terminal 1"/empty)
        $t = $candidates | Where-Object { $_.title -and $_.title -notmatch '^Terminal \d' } |
             Sort-Object lastOutputAt -Descending | Select-Object -First 1
        if ($t) { $handle = $t.handle; break }
      } catch { }
    }
  }
  if (-not $handle) { throw "Could not resolve terminal handle for '$title' in $worktreeSelector" }
  Log "terminal '$title': $handle"
  return $handle
}

function Wait-TuiIdle { param($handle, [int]$timeoutMs = 180000)
  $res = Invoke-Orca @('terminal','wait','--terminal',$handle,'--for','tui-idle','--timeout-ms',"$timeoutMs",'--json')
  return ($res.result.wait.satisfied -eq $true)
}

function Dispatch-Inject { param($task, $handle)
  $res = Invoke-Orca @('orchestration','dispatch','--task',$task,'--to',$handle,'--inject','--json')
  return $res.result.dispatch.id
}

function Dispatch-Track { param($task, $handle)
  $res = Invoke-Orca @('orchestration','dispatch','--task',$task,'--to',$handle,'--json')
  return $res.result.dispatch.id
}

# Wait for worker_done (or an approval question) from a dispatched worker.
# Returns the worker_done message object, or $null on timeout.
# When $expectTaskId is given, worker_done messages from OTHER tasks (e.g. the
# reviewer's worker_done arriving before the orchestrator's) are logged and
# skipped -- only the expected task's worker_done is returned.
# A `question` message is a PAUSE: log the single approval request and keep
# waiting -- the owner answers in the Orca UI, the worker resumes, and the
# flow continues automatically (no re-ask, no menu).
function Wait-WorkerDone { param($run, [int]$timeoutSec, [string]$expectTaskId = '')
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  $prevDelivery = $null
  while ((Get-Date) -lt $deadline) {
    # check does NOT accept --from (verified against this CLI); from a
    # detached process it needs --terminal <coordinator-handle> instead.
    $termFlag = @()
    if ($script:coordinatorHandle) { $termFlag = @('--terminal', $script:coordinatorHandle) }
    $argv = @('orchestration','check','--run',$run) + $termFlag + @('--wait','--types','worker_done,escalation,question','--timeout-ms','300000','--json')
    if ($prevDelivery) { $argv = @('orchestration','check','--run',$run,'--ack',$prevDelivery) + $termFlag + @('--wait','--types','worker_done,escalation,question','--timeout-ms','300000','--json') }
    $res = Invoke-Orca $argv
    if ($res -and $res.result -and $res.result.messages) {
      foreach ($m in $res.result.messages) {
        if ($m.type -eq 'question') {
          Log "APPROVAL REQUIRED (task paused): $($m.body)"
          Log "  Answer in the Orca UI (or: orca orchestration reply --id $($m.id) --body <answer> --json). Flow resumes automatically."
        }
        if ($m.type -eq 'worker_done') {
          if ($expectTaskId) {
            $wdTask = ''
            if ($m.payload) { try { $wdTask = (($m.payload | ConvertFrom-Json).taskId) } catch { $wdTask = '' } }
            if ($wdTask -ne $expectTaskId) {
              Log "note: worker_done from task $wdTask (waiting for $expectTaskId); skipping"
              continue
            }
          }
          # Consume this delivery now so the next leg's first check starts
          # clean instead of replaying this batch.
          if ($res.result.deliveryId) {
            try { Invoke-Orca (@('orchestration','check','--run',$run,'--ack',$res.result.deliveryId) + $termFlag + @('--json')) | Out-Null } catch { }
          }
          return $m
        }
        if ($m.type -eq 'escalation') {
          Log "ESCALATION from worker: $($m.body)"
          throw "Worker escalated: $($m.body)"
        }
      }
      $prevDelivery = $res.result.deliveryId
    }
  }
  return $null
}

# Poll an agent terminal's output until it contains the completion marker.
# Returns the line(s) containing the marker, or $null on timeout.
function Wait-Marker { param($handle, [string]$marker, [int]$timeoutSec)
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    $res = Invoke-Orca @('terminal','read','--terminal',$handle,'--limit','400','--json')
    if ($res -and $res.result -and $res.result.terminal) {
      $text = $res.result.terminal.tail -join "`n"
      if ($text -match [regex]::Escape($marker)) {
        return (($text -split "`n") | Where-Object { $_ -match [regex]::Escape($marker) }) -join "`n"
      }
    }
    Start-Sleep -Seconds 15
  }
  return $null
}

# ---------------------------------------------------------------------------
Log "=== Fast Lane start: $TaskFile ==="
Journal "FASTLANE START $taskName :: $TaskFile"

try {
  # --- Health check ----------------------------------------------------------
  $status = Invoke-Orca @('status','--json')
  if ($status.result.runtime.reachable -ne $true) {
    throw "Orca runtime not reachable. Open the Orca app first."
  }
  Log "Orca runtime ready ($($status.result.runtime.appVersion))."

  # --- Read the task card (the single owner approval) ------------------------
  if (-not (Test-Path -LiteralPath $TaskFile)) { throw "Task file not found: $TaskFile" }
  $taskText = (Get-Content -LiteralPath $TaskFile -Raw).Trim()
  if ([string]::IsNullOrWhiteSpace($taskText)) { throw "Task file is empty: $TaskFile" }
  Log "Task card loaded ($($taskText.Length) chars)."

  # --- Determine whether this task needs n8n MCP access ----------------------
  # The task card's "N8N-ACCESS: REQUIRED" marker is the ONLY way a worktree
  # gets the primary checkout's .mcp.json. There is deliberately NO command-line
  # override: copying credentials must be card-declared so the approval trail is
  # the task card itself (Codex REFUTE, 2026-08-28). Repository-only cards omit
  # the marker and get no credentials. The orchestrator prompt still governs HOW
  # the tools are used (read-only inspection is card-authorised, protected
  # actions need a gate).
  $needsMcp = ($taskText -match 'N8N-ACCESS:\s*REQUIRED')
  Log "n8n MCP access requested for this task: $needsMcp"

  # --- Resolve the coordinator terminal for --from injection ------------------
  Resolve-Coordinator

  # --- Create ONE fresh worktree (ONE branch for all legs, ONE PR) -----------
  # Agent-first: worktree create --agent claude launches Claude in its first
  # terminal and returns agentTerminalHandle reliably (a bare terminal create
  # in a brand-new worktree times out at handle resolution on this host).
  $wtName = "fastlane-$taskName-$stamp"
  $wtRes = Invoke-Orca @('worktree','create','--repo',"id:$repoId",'--name',$wtName,'--agent','claude','--json')
  $wtId    = $wtRes.result.worktree.id
  $wtPath  = $wtRes.result.worktree.path
  $wtSel   = "path:$wtPath"
  $claudeTerm = $wtRes.result.agentTerminalHandle
  if (-not $claudeTerm) { $claudeTerm = $wtRes.result.startupTerminal.handle }
  Log "Worktree created: $wtId"
  Log "Worktree path: $wtPath"
  Log "Claude terminal (agent-first): $claudeTerm"

  # From here on, every orchestration call the script makes on this Run must
  # carry --from CLAUDE's terminal: Claude is the Run's coordinator, and the
  # script's own terminal is fenced to its previous Run (consumer_fenced). The
  # Invoke-Orca auto-inject uses this handle.
  $script:coordinatorHandle = $claudeTerm
  Log "Coordinator handle switched to Claude terminal: $script:coordinatorHandle"

  # --- Make .mcp.json available in the worktree when the task requires it -----
  # The file is copied from the PRIMARY checkout only (it is gitignored there
  # and never exists in git). It is never committed (repo .gitignore + gate
  # secrets guard) and never printed: logs mention only its presence and the
  # configured server name, never its contents. The orchestrator prompt tells
  # Claude to verify the n8n MCP tools are actually reachable and to pause with
  # a decision gate if they are not.
  if ($needsMcp) {
    $primaryMcp = Join-Path $root '.mcp.json'
    if (Test-Path -LiteralPath $primaryMcp) {
      $wtMcp = Join-Path $wtPath '.mcp.json'
      Copy-Item -LiteralPath $primaryMcp -Destination $wtMcp -Force
      Log "[mcp] copied .mcp.json into worktree (gitignored, never committed)"
      # Verify structurally WITHOUT printing credentials: present, valid JSON,
      # an n8n server configured.
      $mcpOk = $false
      if (Test-Path -LiteralPath $wtMcp) {
        try {
          $parsed = Get-Content -LiteralPath $wtMcp -Raw | ConvertFrom-Json
          if ($parsed.mcpServers -and $parsed.mcpServers.n8n) {
            $mcpOk = $true
            Log "[mcp] verified: worktree .mcp.json parses and configures server 'n8n'"
          } else {
            Log "[mcp] WARNING: worktree .mcp.json has no 'n8n' server entry"
          }
        } catch {
          Log "[mcp] WARNING: worktree .mcp.json does not parse as JSON: $($_.Exception.Message)"
        }
      } else {
        Log "[mcp] WARNING: .mcp.json copy did not land in the worktree"
      }
      if (-not $mcpOk) {
        Log "[mcp] NOTE: the orchestrator will pause with a decision gate if the n8n MCP tools are unavailable"
      }
    } else {
      Log "[mcp] WARNING: task requests n8n access but $primaryMcp does not exist in the primary checkout. The orchestrator must stop and ask rather than approximate."
    }
  } else {
    Log "[mcp] no n8n access requested for this task (no 'N8N-ACCESS: REQUIRED' marker in the task card)"
  }

  # --- Create the Run, bound to CLAUDE'S terminal -----------------------------
  # Claude is the Run's coordinator: it reads the Run mailbox, dispatches the
  # workers, and collects worker_done itself. The script deliberately stays out
  # of the mailbox (a second consumer would race the acks); it communicates
  # with Claude through files only (the orchestrator prompt in, the DONE file
  # out).
  $run = Get-RunId "Fast Lane: $taskName" $claudeTerm
  Log "Run created: $run (coordinator: Claude terminal $claudeTerm)"

  # --- Create the worker terminals (settled worktree -> handles return fast) --
  # Claude (the orchestrator) receives these handles in its prompt and manages
  # the two workers itself; the coordinator only sets them up.
  Log "[setup] starting DeepSeek (opencode) terminal..."
  $deepTerm = New-Terminal $wtSel 'deepseek-test' 'opencode' 'opencode|OC'
  Log "[setup] DeepSeek terminal: $deepTerm"
  Log "[setup] starting Codex terminal..."
  $codexTerm = New-Terminal $wtSel 'codex-review' 'codex' 'codex'
  Log "[setup] Codex terminal: $codexTerm"

  # File handoffs inside the worktree (never committed, vanish with it):
  # DeepSeek result file and Claude's DONE file.
  $testResultFile = Join-Path $wtPath '.fastlane-test-leg-result.txt'
  $doneFile = Join-Path $wtPath '.fastlane-orchestrator-done.txt'
  foreach ($f in @($testResultFile, $doneFile)) { if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force } }

  # --- Create the worker tasks (test -> review) --------------------------------
  # Test leg spec (dispatch target for Claude; the real instructions travel in
  # Claude's terminal-send prompt).
  $testSpec = @"
DeepSeek test-scenario leg for an n8n-legal Fast Lane task. The orchestrator
(Claude) sends you the full instruction via the terminal. Author the scenario(s)
the task card requires under fixtures/scenarios/ ONLY, execute node
harness/run.js (passed >= 81, failed <= 3) and python3 .tooling/scrub.py --check
(0 replacements), commit ONLY the allowed scenario file(s), then WRITE
TEST-LEG-COMPLETE: <counts> <files> to the result file.
"@
  $testTask = New-Task $run 'test-deepseek' $testSpec
  Log "Task test-deepseek: $testTask"

  # Review leg spec (dispatch target for Claude; Codex receives it via --inject).
  $reviewSpec = @"
Adversarial reviewer for an n8n-legal Fast Lane task. Review the full diff on
the current branch (git diff origin/dev/orca-setup...HEAD) plus the DeepSeek
test evidence (harness passed/failed/skipped counts in .fastlane-test-leg-result.txt,
scrub.py --check, scenario files). Return exactly one verdict in your
worker_done body: APPROVE or REFUTE with specific reasons. You have no n8n
credentials and must never request them. Your verdict is advisory.
"@
  $reviewTask = New-Task $run 'review-codex' $reviewSpec ('["' + $testTask + '"]')
  Log "Task review-codex: $reviewTask (depends on $testTask)"

  # Owner decision-gate task: the supported owner-facing approval channel.
  # `orca orchestration ask` is worker-to-coordinator only and fails from the
  # coordinator (dispatch_inactive, proven 2026-08-28 on the PR #12 run). The
  # supported coordinator->owner mechanism is `orca orchestration gate-create
  # --task <id> --question <text>`: it blocks this task until Ali resolves the
  # gate in the Orca UI, and the coordinator waits by polling gate-list. The
  # orchestrator prompt instructs Claude to use this task as the gate target
  # before ANY protected n8n action.
  $ownerGateTask = New-Task $run 'owner-gate' 'Owner decision gate target. Never dispatched. The orchestrator creates a gate on this task with orca orchestration gate-create before any protected n8n action, then waits for Ali to resolve it in the Orca UI.'
  Log "Task owner-gate: $ownerGateTask"

  # --- Launch Claude as the orchestrator ---------------------------------------
  # Claude is the Run's coordinator, not a dispatched worker: no preamble, no
  # worker_done for Claude itself. The orchestrator prompt is long (template +
  # task card) and `terminal send` truncates long text (verified live), so the
  # full prompt is written to a file in the worktree and Claude is told to read
  # it. The file is never committed and vanishes with the worktree.
  $orchTemplate = Get-Content (Join-Path $PSScriptRoot 'orchestrator-prompt.md') -Raw
  $orchPrompt = $orchTemplate `
      -replace '\{\{RUN_ID\}\}', $run `
      -replace '\{\{DEEP_TERM\}\}', $deepTerm `
      -replace '\{\{CODEX_TERM\}\}', $codexTerm `
      -replace '\{\{WT_PATH\}\}', $wtPath `
      -replace '\{\{RESULT_FILE\}\}', $testResultFile `
      -replace '\{\{DONE_FILE\}\}', $doneFile `
      -replace '\{\{OWNER_GATE_TASK\}\}', $ownerGateTask `
      -replace '\{\{TASK_TEXT\}\}', $taskText
  $promptFile = Join-Path $wtPath '.fastlane-orchestrator-prompt.md'
  Set-Content -LiteralPath $promptFile -Value $orchPrompt -Encoding utf8
  Log "[orch] orchestrator prompt written to $promptFile"
  Log "[orch] waiting for Claude TUI idle..."
  if (-not (Wait-TuiIdle $claudeTerm)) { throw "Claude TUI never idle." }
  Log "[orch] telling Claude to read the orchestrator prompt..."
  $go = "Read the file '$promptFile' in the repo root and follow it exactly. It is your complete task and orchestration instructions."
  Invoke-Orca @('terminal','send','--terminal',$claudeTerm,'--text',$go,'--enter','--json') | Out-Null
  Log "[orch] Claude is implementing and orchestrating DeepSeek + Codex. Waiting for its DONE file (pauses surface as APPROVAL REQUIRED)..."
  $deadline = (Get-Date).AddSeconds($LegTimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $doneFile) { break }
    # Surface any owner decision gate without touching the mailbox: Claude's
    # gate-create is resolved by Ali in the Orca UI and the flow resumes.
    Start-Sleep -Seconds 20
  }
  if (-not (Test-Path -LiteralPath $doneFile)) { throw "Orchestrator (Claude) timed out after ${LegTimeoutSec}s; no DONE file at $doneFile" }
  $orchReport = (Get-Content -LiteralPath $doneFile -Raw).Trim()
  Log "[orch] DONE file received:"
  Log $orchReport
  Log "[orch] orchestrator reported success."

  # ---------------------------------------------------------------------------
  # COLLECT -- one PR
  # ---------------------------------------------------------------------------
  Log "Collecting results; creating ONE PR..."
  Push-Location $wtPath
  try {
    $branch = (& git branch --show-current 2>&1 | Out-String).Trim()
    Log "Branch: $branch"
    Log "Pushing branch to origin..."
    & git push -u origin $branch 2>&1 | Out-String | ForEach-Object { Log "  $_" }
    if ($LASTEXITCODE -ne 0) { throw "git push failed (exit $LASTEXITCODE)." }

    # PR body via --body-file, NOT --body: the body contains flags-looking text
    # (e.g. "scrub.py --check") and quotes, and Windows PowerShell 5.1 native-arg
    # quoting would split them into extra gh flags ("unknown flag: --check").
    $prBody = "Fast Lane task: $taskName`n`nTask card: $TaskFile`n`nOrchestrator (Claude) report:`n$orchReport"
    $prBodyFile = Join-Path $env:TEMP ("fastlane-pr-body-" + [guid]::NewGuid().ToString('N') + ".md")
    Set-Content -LiteralPath $prBodyFile -Value $prBody -Encoding utf8
    $prOut = (& gh pr create --base dev/orca-setup --head $branch --title "Fast Lane: $taskName" --body-file $prBodyFile 2>&1 | Out-String)
    Remove-Item -LiteralPath $prBodyFile -Force -ErrorAction SilentlyContinue
    Log $prOut
    if ($LASTEXITCODE -ne 0) { throw "gh pr create failed (exit $LASTEXITCODE)." }
    if ($prOut -match 'https://github\.com/\S+/pull/\d+') {
      $prUrl = $Matches[0]
    } else {
      $prUrl = $prOut.Trim()
    }
    Log "PR created: $prUrl"
  } finally {
    Pop-Location
  }

  # --- Finalize: rename claim -> dispatched, journal, close terminals ---------
  $dispatched = Join-Path $queued "$taskName.dispatched-$stamp.md"
  if (Test-Path -LiteralPath $TaskFile) { Move-Item -LiteralPath $TaskFile -Destination $dispatched -Force }
  Journal "FASTLANE COMPLETED $taskName :: PR $prUrl"
  Log "=== Fast Lane complete. PR: $prUrl ==="

  foreach ($h in @($claudeTerm, $deepTerm, $codexTerm)) {
    try { Invoke-Orca @('terminal','close','--terminal',$h,'--json') | Out-Null } catch { Log "note: terminal close $h failed: $($_.Exception.Message)" }
  }
  Write-Host "FASTLANE_RESULT: OK PR=$prUrl"
  exit 0

} catch {
  $err = $_.Exception.Message
  Log "=== Fast Lane FAILED ==="
  Log $err
  Journal "FASTLANE FAILED $taskName :: $err"
  try {
    $failed = Join-Path $done "$taskName.FAILED"
    if (Test-Path -LiteralPath $TaskFile) { Move-Item -LiteralPath $TaskFile -Destination $failed -Force }
  } catch { Log "note: could not move task to done/: $($_.Exception.Message)" }
  Write-Host "FASTLANE_RESULT: FAILED $err"
  exit 1
}
