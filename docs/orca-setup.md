# Orca Three-Agent Setup

This repo is designed to run three agents in parallel via [Orca](https://www.onorca.dev/).
See `AGENTS.md` for the permission model each agent operates under.

## Prerequisites

1. **Orca** installed and the `n8n-legal` project open on branch `dev/orca-setup`.
2. **n8n API key** — from your n8n instance under Settings → API.
3. **Node.js 20+** available in your PATH.

## Step 1 — Create `.mcp.json`

Copy the example and fill in your credentials. This file is gitignored and must never be committed.

```powershell
Copy-Item .mcp.json.example .mcp.json
# then open .mcp.json and replace the two placeholder values
```

The file only needs to exist in the primary worktree (the `dev/orca-setup` checkout).
Orca agent worktrees are separate directories — if an agent worktree needs n8n access,
copy `.mcp.json` into it, or symlink it.

## Step 2 — Orca Setup Script

In Orca → project `n8n-legal` → Configure → Setup script, enter:

```
node --version
```

This is a no-op that confirms Node is available. Replace with `npm install` if you add
npm dependencies in future.

## Step 3 — Add Agents

Orca creates each agent as a separate worktree from the same branch.
In the Orca UI, click the `+` next to the project and add each agent below.

### Agent 1: Claude Code — Orchestrator

| Field | Value |
|---|---|
| Name | `orchestrator` |
| Model | Claude Sonnet or Opus |
| Branch | `dev/orca-setup` |
| MCP | `.mcp.json` (n8n full access) |
| Role | Single orchestrator; only agent that may call n8n MCP tools |

System prompt addition (paste into the agent's custom instructions if Orca supports it):

```
You are the Orchestrator for the n8n-legal repo. Read AGENTS.md before every task.
Show a short plan, wait for owner approval, then carry it out completely.
You are the only agent with n8n MCP access.
```

### Agent 2: Codex — Adversarial Reviewer

| Field | Value |
|---|---|
| Name | `reviewer` |
| Model | o3 or o4-mini |
| Branch | `dev/orca-setup` (read-only worktree) |
| MCP | **None** |
| Role | Reviews diffs, returns APPROVE or REFUTE with reasons |

System prompt:

```
You are the adversarial reviewer for the n8n-legal repo. Read AGENTS.md.
You have no n8n credentials and must never request them.
When given a diff, return APPROVE or REFUTE with specific reasons.
Your verdict is advisory — it does not block the Orchestrator after owner approval,
but a REFUTE must be addressed or explicitly overridden by the owner.
```

### Agent 3: OpenCode — Test Scenario Author

| Field | Value |
|---|---|
| Name | `scenario-author` |
| Model | Any capable model |
| Branch | `dev/orca-setup` |
| MCP | **None** |
| Allowed paths | `fixtures/scenarios/` only |
| Role | Writes new scenario JSON files |

System prompt:

```
You are the test scenario author for the n8n-legal repo. Read AGENTS.md.
You write JSON scenario files in fixtures/scenarios/ only.
Never modify harness/, exports/, workflows/, or any other path.
You have no n8n credentials and must never request them.
Every scenario you write must pass: python3 .tooling/scrub.py --check
with 0 replacements before it is committed.
```

## Step 4 — Verify

In the Orchestrator's terminal:

```powershell
node harness/run.js
```

Expected baseline: **74 passed, 3 failed, 60 skipped.**
The 3 failures are known production defects documented in `harness/FINDINGS.md`.
Do not make them pass by weakening assertions.

## Normal Workflow

```
Owner writes task in Orca chat
  → Orchestrator shows plan
  → Owner types: APPROVE TASK: <description>
  → Orchestrator implements, runs harness, commits
  → Orchestrator sends diff to Reviewer (Codex)
  → Reviewer returns APPROVE or REFUTE
  → If APPROVE: Orchestrator creates PR
  → Owner reviews PR and merges (never auto-merged)
  → Owner publishes to n8n manually (never automatic from GitHub)
```

## Security Notes

- `.mcp.json` is gitignored. Never commit it.
- `scrub.py` and `leak-check.sh` must both exit 0 before every commit.
- `n8n-legal-push` (the sync repo) is read-only from an agent perspective.
  GitHub → n8n is forbidden. See AGENTS.md §1 hard limits.
