# AGENTS.md — the contract for every agent working in this repo

Read this before touching anything. It is read by Claude Code, Codex, and any future
agent. If you are a human, read it too — the rules exist because each one is a scar.

This repo is the source of truth for a **live legal-practice automation system**. It runs
a real practitioner's real matters in Western Australia. A wrong send is not a failed test;
it is correspondence that went to a real party about a real dispute.

---

## 1. Permission model

Claude Code / Cowork is the single Orchestrator. It has full access to the repository,
GitHub, and the n8n MCP/API.

### Task approval

Show one short plan before starting a task. One owner approval covers the complete approved
task, including n8n inspection, code or workflow changes, tests, export and backup, Git
branch, commit, pull request, and publishing if publishing is part of the approved task.

Do not ask for separate approval for every step.

Ask again only if:

- the scope changes
- a new workflow is affected
- a secret or credential is required
- an unplanned production side effect is required

**Approval examples:**

- `APPROVE TASK: update WF4 draft, run tests, create commit and PR`
- `APPROVE TASK: update and publish WF2 after all tests pass`
- `APPROVE TASK: execute the controlled WF5 test and send no external messages`

### Hard limits

1. **Never bypass the approval gate.** WF4's `Approval Gate` is the only thing between a
   model-drafted letter and a real recipient. Do not add a model to it, route around it, or
   simplify its checks.
2. **Never write to the production register** (`SHEET_ID_PLACEHOLDER`) or send Telegram,
   Gmail, or Google Sheets writes unless the owner explicitly includes those actions in the
   task approval.
3. **Never expose secrets or client data.** Run `python3 .tooling/scrub.py &&
   ./.tooling/leak-check.sh` before every commit. Both must exit 0.
4. **Never push directly to main.** Use a branch and pull request.
5. **GitHub → n8n is never automatic.** It is allowed only when explicitly included in the
   owner-approved task.

If a task seems to require crossing these limits, stop and say so.

## 2. What lives here

| path | what it is |
|---|---|
| `exports/wf{1,2,3,4,5,9}.active.json` | scrubbed canonical exports of the **published** version of each of the six production workflows — what is actually running. **Diffable.** This is how you see what changed. |
| `exports/wf{N}.draft.json` | present **only** where the n8n draft is ahead of published. Today: `wf1`, `wf5`. Not production. Not extracted into units. |
| `workflows/*.md` | human specs: node graph, invariants, output contract, and the incident behind each guard |
| `harness/units/` | 59 JS modules, one per n8n Code node, extracted byte-identically **from `wfN.active.json`** so the logic runs in plain Node |
| `harness/n8n-shim.js` | the fake `$input` / `$()` / `$now` that lets those modules run offline and deterministically |
| `harness/run.js` | the test runner |
| `fixtures/scenarios/` | 137 scenario files, mined from ~30 retired one-shot QA workflows |
| `fixtures/sheet-schema.json` | the ten register tabs with exact ordered columns |
| `harness/FINDINGS.md` | production defects the suite found and **nobody has fixed** |
| `harness/invariants.md` | properties of the live register that cannot be checked offline |
| `.tooling/` | scrub map, scrubber, leak-check, unit extractor |
| `README.md` | orientation: what the system does end to end, how to run the harness, the layout |
| `docs/decisions.md` | why the repo is shaped this way — read before proposing to reshape it |
| `docs/draft-vs-active.md` | the draft/active split: why exports are named the way they are, and the current divergences |
| `docs/roadmap.md` | what to do next, in order, and what only the owner can do |

## 3. The loop

```
node harness/run.js                 # must stay green (3 known failures, see below)
node harness/run.js --workflow wf4  # narrow
node harness/run.js --filter delivery-key --verbose
```

The runner is offline, deterministic, and takes seconds. **This is the whole point of the
repo.** Before it existed, testing a change meant hand-building a throwaway workflow in the
n8n UI against live credentials — a twenty-minute human loop, thirty times over five days.

Baseline as of 2026-08-26: **81 passed, 3 failed, 60 skipped.** The three failures are real
(`harness/FINDINGS.md` §1 and §3), not flakes. **Do not make them pass by weakening the
assertion.** A weakened assertion is a lie the next agent will trust.

It was 74/3/60 before the D-TESTFLAG-01 scenarios were added (WF2 test-data stamp guard,
7 new cases). Before that it was 75/2/60 until the units were re-extracted from the
*published* version rather than the draft — one assertion had been green only because it
was being run against code nobody has published. See `docs/draft-vs-active.md` §4.

### Changing production logic

1. Edit the unit in `harness/units/`, prove it with the harness.
2. Port the change into the n8n draft via MCP (`update_workflow`), never straight to live.
3. Re-export and re-scrub so the repo matches. A draft you just wrote goes to
   `exports/wfN.draft.json`, **not** to `wfN.active.json` — `wfN.active.json` changes only
   when the owner publishes:
   `python3 .tooling/extract-units.py && python3 .tooling/scrub.py && ./.tooling/leak-check.sh`
4. Hand the owner the diff. They publish.

### Before every commit

```
python3 .tooling/scrub.py && ./.tooling/leak-check.sh
```

Both must exit 0. `leak-check.sh` greps for 26 families of secret shape. It is a gate, not
advice.

## 4. Roles, when several agents run at once

| Agent | Role | n8n access | Repo access |
|---|---|---|---|
| **Claude Code / Cowork** | Single Orchestrator | Full — mutations require task approval | read/write |
| **Codex** | Adversarial reviewer | None | read-only |
| **OpenCode** | Test scenario author | None | `fixtures/scenarios/` only |

**Orchestrator** shows a short plan, waits for owner approval, then carries out the full
approved task. It is the only agent that may call any `mcp__n8n__*` tool. One agent per
workflow at a time to avoid `configHash` collisions.

**Codex** reviews diffs and reports APPROVE or REFUTE with reasons. Its verdict is advisory:
it does not block the Orchestrator after owner approval, but a REFUTE must be addressed or
explicitly overridden by the owner. Codex has no n8n credentials and must never receive them.

**OpenCode** writes scenario JSON in `fixtures/scenarios/` only. It does not touch units,
adapters, exports, or workflow code. It has no n8n credentials and must never receive them.
Every scenario must pass `python3 .tooling/scrub.py --check` with 0 replacements.

**Parallelise** across independent workflows and defects. **Serialise** anything that touches
the same workflow's `configHash` or the shared spreadsheet.

## 5. Things that are true and will bite you

### The draft is not what is running

`mcp__n8n__get_workflow_details` returns the **DRAFT**. It does not return the published
version. For a workflow whose draft is ahead, everything in that payload — code, prompts,
parameters — is code that has never executed. Read three fields before you believe any of
it: `versionId` (the draft you were handed), `activeVersionId` (what production runs), and
`activeVersion.sameAsDraft`.

**A UI autosave silently creates a draft ahead of published.** Nobody presses publish and
nobody is warned. Someone opens a live workflow in the n8n editor, nudges a field, walks
away — `versionId` moves, `activeVersionId` does not, and the next agent exports a version
that has never run. In the history an autosave is `autosaved: true`, `name: null`, and an
author with **no `(via MCP)` suffix**; a bare name means a human in the editor, `(via MCP)`
means an agent or the API. The editor also prunes any parameter equal to its default, so an
explicitly-spelled default silently disappears on first autosave and looks like an edit in
the diff.

Hence the export naming: `exports/wfN.active.json` is the published body and always exists;
`exports/wfN.draft.json` exists only where the draft is ahead. **The absence of a draft file
is the claim that draft == active.** `harness/units/` is extracted from active only — the
harness's job is to tell the truth about what is running. Full account, including the two
current divergences (`wf1`, `wf5`): `docs/draft-vs-active.md`.

**Publishing leaves almost no trace.** It writes no history entry and does not move
`updatedAt`. `activeVersionId` moving is the only signal. WF9 was published by someone
mid-session on 2026-08-25 and nothing else in the instance recorded it.

- **`dry_run` is hardcoded to the string `"true"` in WF4's Config.** It is a string, not a
  boolean. Much of the safety you observe in testing comes from this one literal.
- **Two FNV-1a implementations coexist.** The delivery key was widened to 64-bit (two salted
  passes, `F-02`); the ingress fingerprint in WF5 `Build Reply Context` was not, and is
  still 32-bit. Old 8-hex `SND-` keys exist in the register alongside new 16-hex ones.
- **`action_id` is not unique in the register.** A historical `append` with no matching
  column left duplicate rows. The daily digest over-reports open work by the duplicate count.
- **The Code sandbox is not Node.** `crypto` is unavailable (hence hand-rolled FNV), and the
  `URL` constructor behaves differently. One scenario documents this and will not reproduce
  locally.
- **Three units read the system clock directly.** The runner freezes the global `Date` to
  pin them; their own clock reads are therefore not under test.
- **Matter ids are stamped in UTC while the workflow timezone is `Australia/Perth`.** A
  matter opened after 08:00 local carries the previous day's date.

## 6. Open safety issues nobody has closed

These came out of the extraction. They are live, in production, today:

1. `9vnlGSbNFSkg0qnc` **QA Autopilot is active** with an RCA → fixer → apply-patch → rollback
   loop. Apply and Rollback are still stubs, so it cannot write — implementing them puts a
   model-authored patch one guard away from a live workflow.
2. `T6jGZRxNd9pVOfHi` **a QA clone of WF2 is active** — and is precisely the workflow the
   autopilot's fixer is authorised to patch.
3. `NslQM7zGpacyCwTS` **"ZZ CORRUPT IMPORT — DO NOT USE" holds two live schedule triggers**
   and 52 Sheets nodes aimed at the production register. Inactive, but not archived.
4. `aSygXnnfLDXRR3fK` exposes an **unauthenticated public webhook** whose only job is to
   throw an error at the owner's Telegram.
5. **WF4 `Verify Selected Row` passes a gate channel of `NONE`** against a register row
   saying `GMAIL` — demonstrated by execution, not just by reading.
6. **The row fingerprint omits `status`**, so a row flipped to `CANCELLED` between the guard
   and the writer still verifies.
7. **`resolveTestFlag` does not exist.** The digest's comment calls `facts.test_data_only` a
   deterministic signal stamped at ingress; nothing stamps it. Test/live separation falls
   back to a model-generated title — the exact 2026-08-23 incident it was written for.

Do not fix these opportunistically in the middle of another task. Each deserves its own
change, its own scenario, and the owner's eyes.

## 7. Style

Comments in this codebase record incidents: execution numbers, dates, what broke, what the
old code did and why it failed. That convention is load-bearing — it is how this repo
survived being reconstructed at all. **Keep it.** When you fix something, write down what
it did before and which execution proved it.
