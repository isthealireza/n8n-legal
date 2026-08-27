<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0 → 1.1.1
- Modified principles:
  - III. No Production Writes → III. No Production Writes Without Approval
    (added the owner-approval carve-out from AGENTS.md §1 hard limit 2)
  - VI. No Direct Pushes (added the owner-approval carve-out for publishing from
    AGENTS.md §1 hard limit 5; removed the absolute "always the owner's manual act")
- Added sections:
  - Development Workflow (encodes AGENTS.md §1 "Task approval": one plan, one
    approval, and the four re-ask triggers)
- Added to Governance: Codex REFUTE is advisory but must be addressed or
  explicitly overridden by the owner (AGENTS.md §4)
- Removed sections: none
- Deferred TODOs: none
- v1.1.1 (P1 review fix): Development Workflow restated as three explicit phases
  — (1) prepare a read-only plan, (2) STOP and wait for explicit owner approval
  before executing ANY part of the task (no n8n inspection, file/workflow
  changes, task-performing tests, publishing, or production side effects), then
  (3) execute. One-plan/one-approval model and the III/VI carve-outs preserved.
- Note for the owner (not a constitution change): AGENTS.md §3 line 77 comments
  "2 known failures" while §3 line 86 states the baseline as 81/3/60. The
  constitution follows the 3-failure baseline. AGENTS.md needs the stale
  parenthetical corrected.
-->

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
its checks, never edit `exports/wf4.active.json` in a way that changes it. This
principle has no exception and no approval can waive it.

### III. No Production Writes Without Approval

Never write to the production register, and never send Telegram, Gmail, or
Google Sheets writes, **unless the owner explicitly includes those actions in
the task approval**. Absent that approval the default is absolute: this repo
only ever contains scrubbed exports, specs, and tests. If a task appears to
require a live write the owner did not approve, stop and report — never work
around.

### IV. Secrets And Client Data Never Leave

Run `python3 .tooling/scrub.py && ./.tooling/leak-check.sh` before every commit;
both must exit 0. Never expose secrets or client data. Never commit `.mcp.json`,
`.raw/`, or unscrubbed exports. Codex and OpenCode MUST never receive n8n
credentials.

### V. The Draft Is Not What Is Running

`wfN.active.json` is the published body production runs; `wfN.draft.json`
exists only where the draft is ahead. `harness/units/` is extracted from
**active only** — the harness tells the truth about what is running, never about
unpublished drafts. A change to production logic goes: edit the unit → prove it
with the harness → port to the n8n **draft** via MCP → re-export to
`wfN.draft.json` (never `active`) → hand the owner the diff. `wfN.active.json`
changes only when the owner publishes.

### VI. No Direct Pushes

Never push directly to main. Work on a branch and open a pull request. GitHub →
n8n is never automatic; publishing is allowed only when the owner explicitly
includes it in the approved task, and otherwise remains the owner's manual act.

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

## Development Workflow

### Three phases — prepare, wait, execute

Every task runs in exactly three phases, in order. The agent MUST NOT skip or
merge phases 1 and 2.

**Phase 1 — Prepare (read-only).** Read `AGENTS.md` and this constitution, then
show one short plan for the task. This phase performs no task actions: no n8n
inspection, no file or workflow changes, no tests that perform task actions, no
publishing, and no production side effects.

**Phase 2 — Wait for explicit owner approval.** After showing the plan, the
agent MUST STOP and wait. Nothing in the task is executed — not n8n inspection,
not file or workflow changes, not tests that perform task actions, not
publishing, and not any production side effect — until the owner explicitly
approves the plan. One owner approval covers the complete approved task — n8n
inspection, code or workflow changes, tests, export and backup, Git branch,
commit, pull request, and publishing where publishing is part of the approved
task — so the agent does not ask for separate approval for every step. The
approval gate in Principle II has no exception and no approval can waive it.

**Phase 3 — Execute.** Only after explicit owner approval, carry out the
approved plan completely. Live writes and publishing remain subject to the
carve-outs in Principles III and VI: they are permitted only when the owner
explicitly included them in the approval.

### When to ask again

Ask for a new approval only if the scope changes, a new workflow is affected, a
secret or credential is required, or an unplanned production side effect is
required.

### Open safety issues are not opportunistic fixes

The live safety issues in AGENTS.md §6 MUST NOT be fixed in the middle of
another task. Each requires its own change, its own scenario, and the owner's
review.

## Governance

- Constitution supersedes all other practices; AGENTS.md supersedes the
  constitution. Amendments require the owner's review and a PR.
- The three-agent model applies: **Claude Code** is the single Orchestrator (the
  only agent with n8n MCP access, and the only agent that may call any
  `mcp__n8n__*` tool); **Codex** reviews diffs and reports APPROVE or REFUTE;
  **OpenCode** writes scenario JSON in `fixtures/scenarios/` only.
- Codex's verdict is advisory and does not block the Orchestrator after owner
  approval, but a REFUTE MUST be addressed or explicitly overridden by the owner.
- Parallelise across independent workflows and defects. Serialise anything that
  touches the same workflow's `configHash` or the shared spreadsheet — one agent
  per workflow at a time.
- Every scenario must pass `python3 .tooling/scrub.py --check` with 0
  replacements.

**Version**: 1.1.1 | **Ratified**: 2026-08-27 | **Last Amended**: 2026-08-27
