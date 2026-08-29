# Orca automation loop — n8n-legal

This directory is the automation layer that lets the owner run the
n8n-legal development loop through [Orca](https://www.onorca.dev/) with
**gates intact**. The gates are not optional steps the agent might skip — they
are enforced by `gate.ps1` before every commit.

Read `AGENTS.md` first. This README is the operation manual for the loop.

## The loop

```
Owner drops task card in tasks/inbox/  (or runs kickoff.ps1 manually)
  → watch.ps1 dispatches it to a fresh Orca worktree
  → Orca launches the Claude agent (Orchestrator) in that worktree
  → Agent reads AGENTS.md + .specify/memory/constitution.md
  → Agent runs the Spec Kit SDD loop (specify → plan → tasks → implement → converge)
  → Agent proves it: node harness/run.js  (baseline 81/3/60, no new failures)
  → Agent runs tools/orca/gate.ps1   (MUST exit 0 before every commit)
  → Agent commits on a branch, pushes, opens a PR
  → Owner reviews the PR, merges, publishes to n8n manually
```

## Spec Kit (Spec-Driven Development)

This repo is a [GitHub Spec Kit](https://github.com/github/spec-kit) project
(`.specify/` + `.claude/skills/speckit-*`). Every Orca worktree inherits the 10
`/speckit-*` skills because they are committed to `dev/orca-setup`.

- `.specify/memory/constitution.md` — the project constitution: the spec-kit
  encoding of AGENTS.md (live system, approval gate, no production writes,
  secrets, draft-vs-active, PR-only, harness floor, gate.ps1, incident comments).
  Amend it only through the owner's review, mirroring AGENTS.md governance.
- Flow for substantive work: `/speckit-specify` → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement` → `/speckit-converge` (repeat until
  Converged). Optional quality skills: `/speckit-clarify`,
  `/speckit-analyze`, `/speckit-checklist`.
- The gate is the SDD "definition of done": a converged spec that fails
  `gate.ps1` is not done.

## Files

| file | what it does |
|---|---|
| `agent-prompt.md` | The prompt sent to every spawned Orchestrator agent. Embeds the AGENTS.md hard limits and the change loop. |
| `kickoff.ps1` | Manual trigger: create an Orca worktree from `dev/orca-setup`, launch the Claude agent, send it the gated prompt. Optionally copies `.mcp.json` into the worktree. |
| `watch.ps1` | Folder-watch trigger: any `.md`/`.txt` dropped in `tasks/inbox/` is dispatched automatically and moved to `tasks/queued/` (or `tasks/done/<name>.FAILED`). |
| `gate.ps1` | Pre-commit gate the agent MUST run: harness baseline, scrub.py, leak-check.sh, branch guard (no main), active-export guard (no `wfN.active.json` edits), secrets guard. Exit 0 or no commit. |

## Triggers

### Manual (recommended for first runs)

```powershell
pwsh -File tools/orca/kickoff.ps1 -Task "Fix the WF2 test-data stamp guard"
```

### Folder watch

```powershell
# one-shot sweep of tasks/inbox/
pwsh -File tools/orca/watch.ps1 -Once

# continuous watch (run in a terminal you keep open)
pwsh -File tools/orca/watch.ps1
```

Dropping a file in `tasks/inbox/` **is** the owner's approval to carry out the
task — the agent does not re-ask during repository-only work. The task file
itself is moved to `tasks/queued/` on dispatch.

**Live n8n tasks:** a card that needs the live instance carries the marker line
`N8N-ACCESS: REQUIRED`. `fastlane.ps1` then copies the primary checkout's
`.mcp.json` into the worktree (gitignored, never committed, never printed) so
the Orchestrator can inspect the named workflow read-only with the full existing
connection.

**Protected actions stop on a decision gate.** Before any protected action
(publish, activate/deactivate, execute with side effects, external sends,
production writes, irreversible actions, active-export change, scope change)
the Orchestrator creates a gate with `orca orchestration gate-create --task
<owner-gate> --question <action>` and waits; Ali resolves it in the Orca UI and
the flow resumes. `orca orchestration ask` is worker-to-coordinator only and is
NOT used for owner approval (it fails from the coordinator with
`dispatch_inactive`, proven 2026-08-28).

**Coordinator timeout is collect-pending, not task failure.** `fastlane.ps1`
waits `-LegTimeoutSec` (default 1800) for the orchestrator's DONE file, then
extends by `-LegTimeoutExtensionSec` (default 3600) before failing. Live n8n
runs routinely take 30–90 minutes (opencode/DeepSeek TUI + live MCP inspection
+ owner decision-gate waits), so pass a larger `-LegTimeoutSec` (e.g. 5400) for
live tasks. If the timeout still fires, the orchestrator terminal stays live and
a late DONE file can still be collected manually: push the worktree branch and
create the ONE PR with the DONE report as the body (incident 2026-08-29,
`retry-live-wf4-inspection` — DONE file arrived 30 minutes after the timeout;
the run was wrongly marked FAILED and PR #14 was collected manually).

## Gates (enforced by gate.ps1)

1. **Harness**: `node harness/run.js` → passed ≥ 81 and failed ≤ 3. The 3
   baseline failures are real production defects (`harness/FINDINGS.md`); never
   weaken an assertion to make them pass, never introduce a 4th.
2. **Scrub**: `python3 .tooling/scrub.py` must exit 0.
3. **Leak check**: `.tooling/leak-check.sh` (via Git Bash) must exit 0.
4. **Branch**: never on `main`/`master` — PRs only.
5. **Active exports**: the diff must not touch `exports/wfN.active.json` —
   those change only when the owner publishes.
6. **Secrets**: `.mcp.json`, `.raw/`, and `*.unscrubbed.json` must never be
   staged.

## Notes and traps

- `.mcp.json` lives only in the primary checkout and is copied into agent
  worktrees by `kickoff.ps1`. It is gitignored everywhere. Never commit it.
- `leak-check.sh` in working-tree mode was failing on `.mcp.json` (a real JWT —
  the n8n API key, deliberately gitignored). `.tooling/leak-check.sh` now
  excludes that one file with an explanatory comment. This is not a gate
  weakening: the file can never be committed or pushed.
- Agent worktrees branch from `dev/orca-setup`. The `n8n-legal-push` repo is
  the read-only sync repo; agents never write there.
- The three-agent model (orchestrator / reviewer / scenario-author) is
  described in `docs/orca-setup.md`. This loop automates the orchestrator leg;
  the reviewer (Codex) and scenario-author (OpenCode) keep their roles from
  AGENTS.md §4.
