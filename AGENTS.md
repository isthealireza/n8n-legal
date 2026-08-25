# AGENTS.md — the contract for every agent working in this repo

Read this before touching anything. It is read by Claude Code, Codex, and any future
agent. If you are a human, read it too — the rules exist because each one is a scar.

This repo is the source of truth for a **live legal-practice automation system**. It runs
a real practitioner's real matters in Western Australia. A wrong send is not a failed test;
it is correspondence that went to a real party about a real dispute.

---

## 1. The three lines you do not cross

1. **Never publish.** `mcp__n8n__publish_workflow`, `publish_agent`, `restore_workflow_version`,
   and `update_agent_integration` are the owner's alone. You may create and mutate *drafts*.
   You may not decide what goes live.
2. **Never write to the production register.** Spreadsheet `SHEET_ID_PLACEHOLDER` holds
   live matters, approvals, and correspondence. The real id — along with the real Drive
   folder id, owner chat id, n8n credential ids and party addresses — **is** committed, as
   the *keys* of `.tooling/scrub-map.json`, because the scrub is not reversible without
   them. `leak-check.sh` excludes that one file by design. Treat this repo as
   **private**: it is safe to share a diff, it is not safe to publish the tree. No agent writes to it. Ever. Not "just a
   test row". Not "read-before-mutate so it's safe".
3. **Never bypass the approval gate.** WF4's `Approval Gate` is the only thing between a
   model-drafted letter and a real recipient. It is pure deterministic code with no model in
   the loop, deliberately. Do not add a model to it. Do not add a route around it. Do not
   "simplify" its checks.

If a task seems to require crossing one of these, stop and say so. That is the correct
outcome, not a failure.

## 2. What lives here

| path | what it is |
|---|---|
| `exports/wf{1,2,3,4,5,9}.json` | scrubbed canonical exports of the six production workflows. **Diffable.** This is how you see what changed. |
| `workflows/*.md` | human specs: node graph, invariants, output contract, and the incident behind each guard |
| `harness/units/` | 59 JS modules, one per n8n Code node, extracted byte-identically so the logic runs in plain Node |
| `harness/n8n-shim.js` | the fake `$input` / `$()` / `$now` that lets those modules run offline and deterministically |
| `harness/run.js` | the test runner |
| `fixtures/scenarios/` | 137 scenario files, mined from ~30 retired one-shot QA workflows |
| `fixtures/sheet-schema.json` | the ten register tabs with exact ordered columns |
| `harness/FINDINGS.md` | production defects the suite found and **nobody has fixed** |
| `harness/invariants.md` | properties of the live register that cannot be checked offline |
| `.tooling/` | scrub map, scrubber, leak-check, unit extractor |
| `README.md` | orientation: what the system does end to end, how to run the harness, the layout |
| `docs/decisions.md` | why the repo is shaped this way — read before proposing to reshape it |
| `docs/roadmap.md` | what to do next, in order, and what only the owner can do |

## 3. The loop

```
node harness/run.js                 # must stay green (2 known failures, see below)
node harness/run.js --workflow wf4  # narrow
node harness/run.js --filter delivery-key --verbose
```

The runner is offline, deterministic, and takes seconds. **This is the whole point of the
repo.** Before it existed, testing a change meant hand-building a throwaway workflow in the
n8n UI against live credentials — a twenty-minute human loop, thirty times over five days.

Baseline as of 2026-08-25: **75 passed, 2 failed, 60 skipped.** The two failures are real
production defects (`harness/FINDINGS.md` §1), not flakes. **Do not make them pass by
weakening the assertion.** A weakened assertion is a lie the next agent will trust.

### Changing production logic

1. Edit the unit in `harness/units/`, prove it with the harness.
2. Port the change into the n8n draft via MCP (`update_workflow`), never straight to live.
3. Re-export and re-scrub so the repo matches:
   `python3 .tooling/extract-units.py && python3 .tooling/scrub.py && ./.tooling/leak-check.sh`
4. Hand the owner the diff. They publish.

### Before every commit

```
python3 .tooling/scrub.py && ./.tooling/leak-check.sh
```

Both must exit 0. `leak-check.sh` greps for 26 families of secret shape. It is a gate, not
advice.

## 4. Roles, when several agents run at once

- **Implementer** — has n8n MCP access. Writes code, mutates drafts. One at a time per
  workflow; two agents mutating one workflow will clobber each other's `configHash`.
- **Reviewer (adversarial)** — repo only, **no credentials**. Its job is to refute, not to
  approve. Default to "refuted" when uncertain.
- **Regression guard** — runs `harness/run.js`, reports PASS/FAIL, changes nothing.
- **Domain critic** — legal only: citation integrity, approval gating, whether anything
  could leave without a human saying yes.

Parallelise across *independent* workflows and independent defects. Serialise anything that
touches shared register state. Worktree isolation protects the code; it does **not**
protect the shared n8n instance or the shared spreadsheet.

## 5. Things that are true and will bite you

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
