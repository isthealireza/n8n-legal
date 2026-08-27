# n8n-legal Constitution

Governing principles for every agent (human or AI) that develops this system.
This constitution is the spec-kit encoding of AGENTS.md. **AGENTS.md is the
canonical contract and overrides this file if they ever disagree.**

## Core Principles

### I. The System Is Live

This repo is the source of truth for a live legal-practice automation system
running a real practitioner's real matters in Western Australia. The workflows
execute in n8n. A wrong send is not a failed test — it is correspondence that
went to a real party about a real dispute.

### II. The Approval Gate Is Inviolable

WF4's `Approval Gate` node is the only thing between a model-drafted letter and
a real recipient. Never add a model to it, never route around it, never simplify
its checks, never edit `exports/wf4.active.json` in a way that changes it.

### III. No Production Writes

Never write to the production register, and never send Telegram, Gmail, or
Google Sheets writes. This repo only ever contains scrubbed exports, specs, and
tests. If a task requires a live write, stop and report — do not work around.

### IV. Secrets And Client Data Never Leave

Run `python3 .tooling/scrub.py && ./.tooling/leak-check.sh` before every commit;
both must exit 0. Never expose secrets or client data. Never commit `.mcp.json`,
`.raw/`, or unscrubbed exports.

### V. The Draft Is Not What Is Running

`wfN.active.json` is the published body production runs; `wfN.draft.json`
exists only where the draft is ahead. `harness/units/` is extracted from
**active only** — the harness tells the truth about what is running, never about
unpublished drafts. A change to production logic goes: edit the unit → prove it
with the harness → port to the n8n **draft** via MCP → re-export to
`wfN.draft.json` (never `active`). `wfN.active.json` changes only when the owner
publishes.

### VI. No Direct Pushes

Never push directly to main. Work on a branch and open a pull request. GitHub →
n8n is never automatic; publishing to n8n is always the owner's manual act.

## Quality Gates

### The harness is the floor

`node harness/run.js` must stay green within baseline: **81 passed, 3 failed,
60 skipped**. The 3 failures are real production defects documented in
`harness/FINDINGS.md`. Never make them pass by weakening an assertion, and never
introduce a new failure.

### The Orca gate runs before every commit

`tools/orca/gate.ps1` enforces: harness baseline, scrub, leak-check, branch
guard, active-export guard, and secrets guard. It must exit 0 before any commit.

### Every fix records its incident

Comments record incidents: execution numbers, dates, what broke, what the old
code did and why it failed. When you change something, write down what it did
before and which execution proved the change.

## Governance

- Constitution supersedes all other practices; AGENTS.md supersedes the
  constitution. Amendments require the owner's review and a PR.
- The three-agent model applies: **Claude Code** is the single Orchestrator (the
  only agent with n8n MCP access); **Codex** reviews diffs and reports APPROVE
  or REFUTE; **OpenCode** writes scenario JSON in `fixtures/scenarios/` only.
- Parallelise across independent workflows and defects. Serialise anything that
  touches the same workflow's `configHash` or the shared spreadsheet.
- Every scenario must pass `python3 .tooling/scrub.py --check` with 0
  replacements.

**Version**: 1.0.0 | **Ratified**: 2026-08-27 | **Last Amended**: 2026-08-27
