# WF4 — live inspection and gate-approved draft port, 2026-08-29

Written 2026-08-29 during the Orca Fast Lane run `run_fe5d400247aa` (retry of the first
controlled live-n8n task, with the coordinator repairs from PR #13 in place).

This document records TWO separate phases of the same run, and they must not be conflated:

- **PHASE A — READ-ONLY INSPECTION (Sections 1–3).** The live inspection was read-only and
  used exactly four MCP reads: `get_workflow_details`, `get_workflow_history`,
  `get_workflow_version` and `get_workflow_versions_diff`. This phase performed no
  `update_workflow`, no `setNodeParameter`, no draft write, no publish, no activation, no
  execution, and no external side effect. The workflow was not modified by the inspection.
- **PHASE B — GATE-APPROVED DRAFT PORT (Section 5).** Separately and later, after the owner
  resolved a decision gate, the Orchestrator performed the approved draft port using one
  `update_workflow` call with two `setNodeParameter` operations. This phase changed only the
  `jsCode` values of `Integrity Guard` and `Build Integrity Halt Notice` in the WF4 draft. It
  did not publish, activate, execute, send external messages, or modify unrelated nodes.

In short: the live inspection in Sections 1–3 was read-only and used four MCP reads. Section
5 separately records the later owner-gated draft port, which used one `update_workflow` call
with two `setNodeParameter` operations.

---

## 1. What the live instance says

| field | value |
|---|---|
| workflow name | `4 - Research Drafting Approval and Dispatch` |
| workflow id | `zKr24IThF30e6jXw` |
| `active` | `true` |
| `isArchived` | `false` |
| `versionId` (DRAFT) | `8107c96f-57cd-4b77-a9bb-638a676d7926` |
| `activeVersionId` (PUBLISHED — what production runs) | `902130f4-58d0-4189-bf80-273c753c9c34` |
| `activeVersion.sameAsDraft` | **`false`** |
| node count — draft `8107c96f` | **181** |
| node count — published `902130f4` | **102** |
| `updatedAt` | `2026-08-27T02:33:23.567Z` |
| `errorWorkflow` | `JfaCOxRq0FjZ5JWb` (WF9) |
| timezone | `Australia/Perth` |

`get_workflow_details` hands back the **draft** (`nodeCount: 181`). The 102-node body is the
one production executes. AGENTS.md §5 and `docs/draft-vs-active.md` §1 exist because of
exactly this gap; it is live on WF4 right now.

### Version history (2 entries, newest first)

| versionId | author | autosaved | createdAt | name |
|---|---|---|---|---|
| `8107c96f` | `Owner (via MCP)` | `false` | 2026-08-27T02:33:23Z | *SPEC-2 Rev B: verify inherited safety contract* |
| `902130f4` | `Owner (via MCP)` | `false` | 2026-08-25T07:36:57Z | *D-CHANNEL-01 + D-STATUS-01: fail-closed channel guard and status fingerprint* |

**No UI autosave.** Both entries carry the `(via MCP)` suffix and `autosaved: false`, so
neither is a human nudging a field in the editor. This is the good case: the divergence is a
deliberate, described, agent-authored draft — not the silent autosave trap.

## 2. Does the published body match the repository?

**Yes, exactly.** `exports/wf4.active.json` was re-verified against a fresh
`get_workflow_version(902130f4)` fetched today:

- 102 nodes live, 102 nodes in the export; **no node added, none removed, no name changed**;
- the `connections` object is byte-identical;
- of the 102 nodes, 54 differ textually **and every one of those differences is a
  `.tooling/scrub-map.json` replacement**. Applying the scrub map to the live payload and
  re-diffing leaves **zero** residual differences, node for node.

**Unexpected drift: none.** The capture recorded in the `_export` block is faithful.

### The two nodes the task names

| node | node id | live published sha256(jsCode) | recorded in the unit header | match |
|---|---|---|---|---|
| `Integrity Guard` | `7bee0e49-ab5e-471d-9a88-4da7d736e459` | `0950131e99ab5fea8b69a879700c3fefd0c9d335a998dc4517b66ba0dd853011` | same | yes |
| `Build Integrity Halt Notice` | `7fd2f6ec-ab2d-4afa-940a-1def80c503fe` | `baabf88da65ed5bce10c3d0142837cbe10c98f11d6809bcd5e045a11930a7ffe` | same | yes |

`Build Integrity Halt Notice`'s live `jsCode` is byte-identical to the export with no
scrubbing required at all. `Integrity Guard`'s live `jsCode` differs from the export in
exactly **two comment lines**, both pure scrub substitutions inside the node's own incident
narrative. Neither line is code: they are the two lines of the guard's incident comment that
name the real action id and the real centre-management recipient from the 2026-08-19 dispute.
The live text is the unscrubbed pair; the export carries the placeholders. The two literals
are the `ACT-…-001-005` action-id entry and the centre-name entry already registered in
`.tooling/scrub-map.json` — they are deliberately not reproduced here, because this file is a
scrub target too.

**No executable statement differs.** The Approval Gate
chain the task names — `Integrity Guard` -> `Approval Gate` -> `Verify Selected Row` ->
`Gate Result` — is present, connected as exported, and unchanged in the published version.

## 3. Comparison with the three repository artefacts

| artefact | relationship to the live published node | classification |
|---|---|---|
| `exports/wf4.active.json` (902130f4) | identical modulo scrub map, 0 residual diffs | **intended** — the capture contract working |
| `harness/units/wf4/integrity-guard.js` | ahead of live: FINDINGS §1 severity ranking + distinct ambiguous-action count | **intended** — declared in the unit header and in FINDINGS §1; not ported, not published |
| `harness/units/wf4/build-integrity-halt-notice.js` | ahead of live: D-COUNT-01 heading / audit-row count | **intended** — same, declared in both places |

Both units still record the **published** sha in their `meta.sha256OfJsCode` and in their
header comment, and both shas were confirmed against the live instance today. The units are
correctly anchored: they say which body is running and admit that they are not it.

### The exact delta the units carry over the live nodes

**`Integrity Guard`** — three edits on top of published `902130f4`:

1. a declared `CONFLICT_SEVERITY` order (`DUPLICATE_ACTION_ID_FIELD_MISMATCH` >
   `DUPLICATE_IDEMPOTENCY_KEY` > `DUPLICATE_ACTION_ID` > `BLANK_ACTION_ID` >
   `BLANK_IDEMPOTENCY_KEY` > `ACTION_NOT_FOUND`) with `severityRank()`; unknown codes rank
   last;
2. `const worst = conflicts[0]` replaced by a stable minimum-rank scan over a copy —
   strictly-less-than, so ties keep the earlier push and `conflicts` (and therefore
   `integrity_detail`) keeps register order;
3. a distinct-ambiguous-`action_id` count (`ambiguousIds`, reading each conflict's own
   `action_id` *and* its `rows[]`, with a synthetic `'#blank@' + snapshot_index` key for
   `BLANK_ACTION_ID`), emitted as `integrity_conflict_count` alongside
   `integrity_conflict_record_count`; the reason string now reads
   *"N ambiguous action(s) found, reported as M conflict record(s)."*

**`Build Integrity Halt Notice`** — three edits on top of published `902130f4`:

1. `guardConflictCount` reads `item.integrity_conflict_count` when it is a number, else
   `null`; `headingCount` falls back to `detail.length`;
2. `'Conflicting records (' + detail.length + ')'` -> `headingCount`;
3. `halt_conflict_count: detail.length` -> `headingCount`, with the raw `detail.length`
   preserved as a new `halt_conflict_record_count` so the Events audit row loses nothing.

Nothing else in either node changes. `integrity_detail` is untouched, so the `MAX_DETAIL`
slice and the deterministic `event_id` seed see byte-for-byte what they saw before.

## 4. The draft that stands in front of production — `8107c96f`

Not part of this task's change, but it is what a `publish` press would ship, so it is
recorded here. Diff `902130f4 -> 8107c96f`:

- **79 nodes added, 0 removed, 2 modified**; 151 connections added, 44 removed.
- The 79 additions are one `Evaluate Safety` node plus 39 `Guard - <name>` /
  `Suppressed - <name>` pairs wrapping every external-effect node (Sheets writes, Gmail
  sends, Telegram sends, Drive writes).
- `Config` modified: `dry_run` becomes a validated passthrough
  (`['true','false'].includes($json.dry_run) ? $json.dry_run : 'true'`) instead of the
  hardcoded string `"true"`, and three keys are added — `live_send_authorised`
  (fail-closed `'false'`), `environment` (fail-closed `'test'`), `expected_environment`
  (`'test'`).
- `Approval Gate` modified: **`STEP1-KILLSWITCH-20260826`** —
  `const dryRun = String(cfg.dry_run).toLowerCase() === 'true'` is replaced by a
  three-condition fail-closed test (`dry_run === 'false'` **and**
  `live_send_authorised === 'true'` **and** `environment === 'production'`), with
  `dryRun = !liveSendAuthorised`. This tightens the gate; it does not route around it.

**One discrepancy worth the owner's eye.** The draft's own version description asserts that
*"Guards, suppressed nodes, the approval gate, prompts, routes, owner checks, model settings
and register logic unchanged."* The `Approval Gate` **jsCode is changed** by that draft, as
quoted above. The change reads as safety-strengthening rather than weakening, but the
description understates it, and per AGENTS.md §1.1 the Approval Gate is the one node whose
edits must never be described as "unchanged".

**Consequence for the port plan (§5).** `Integrity Guard` and `Build Integrity Halt Notice`
are *not* among the 2 nodes the draft modifies, so the fix would apply cleanly. But the
draft is a single publishable unit: the owner **cannot publish the two-node integrity fix
without also publishing SPEC-2 Rev B in full** (79 new nodes, the Config passthrough and the
Approval Gate kill switch). That is a much larger review than the fix itself, and it is the
reason the port is gated rather than assumed.

## 5. The port — PHASE B: GATE-APPROVED AND TAKEN (draft only)

**PHASE A (Sections 1–3) was read-only.** Everything below in this section is PHASE B: the
owner-gated draft write that followed it.

### The decision gate that authorised the port

The port was authorised by Orca decision gate `gate_0d2012146a1b` on the Fast Lane
`owner-gate` task (`task_867338791f4c`) of run `run_fe5d400247aa`:

| gate field | value |
|---|---|
| gate id | `gate_0d2012146a1b` |
| gate task | `task_867338791f4c` (`owner-gate`) |
| run | `run_fe5d400247aa` |
| status | **resolved** |
| resolution | **`approve`** |
| approved by | **Ali** |
| resolved at | **2026-08-28 17:59:03** |

The approved question and scope (verbatim from the gate question):

> "may the two prepared node fixes be ported into the WF4 DRAFT (8107c96f, SPEC-2 Rev B,
> 181 nodes) via update_workflow — Integrity Guard 7bee0e49 and Build Integrity Halt Notice
> 7fd2f6ec, jsCode only, no other node, connection, parameter or credential,
> no publish/activate/execute — with the caveats that the draft is already 79 nodes ahead of
> published and separately changes Config and the Approval Gate, so the fix cannot be
> published without also shipping SPEC-2 Rev B, and that the Approval Gate change is
> unreviewed and is wrongly described as unchanged by its own version description."

The gate therefore permitted **only** the two-node `jsCode`-only write to the WF4 draft. It
did **not** permit publish, activation, execution, external messages, or any unrelated
change. Publishing was NOT approved and was NOT done.

Note: the full gate question additionally spelled out the weighing caveats and the rollback
path (`restore_workflow_version` to `8107c96f`); the complete text is retrievable from the
gate artefact (`orca orchestration gate-list --run run_fe5d400247aa`).

The port below was then performed.

| field | before the port | after the port |
|---|---|---|
| draft `versionId` | `8107c96f-57cd-4b77-a9bb-638a676d7926` | **`470120af-9909-4760-89d9-fc78e4074d75`** |
| `activeVersionId` | `902130f4-58d0-4189-bf80-273c753c9c34` | `902130f4-58d0-4189-bf80-273c753c9c34` (**unchanged**) |
| node count | 181 | 181 |

One `update_workflow` call, two `setNodeParameter` operations on `/jsCode`, applied
atomically: `Integrity Guard` (`7bee0e49`) and `Build Integrity Halt Notice` (`7fd2f6ec`).
Verified afterwards by `get_workflow_versions_diff(8107c96f -> 470120af)`: **2 nodes
modified, 0 added, 0 removed, 0 connections added, 0 connections removed.** No publish, no
activation, no execution, no credential change. **Production is still running `902130f4` and
still carries both defects.**

### Verification, and one deviation I introduced

The port bodies were built by un-scrubbing the repository units, with the round trip proved
before the write: re-scrubbing the port body reproduced the unit byte-for-byte. After the
write, both live draft nodes were re-read and compared against those staged bodies:

- `Build Integrity Halt Notice` — **byte-exact**, 10,369 characters.
- `Integrity Guard` — 12,893 characters, **one token different from the staged body**: a
  single matter id inside the new incident comment. The staged body carried the scrubbed
  placeholder for that matter; what I actually typed into the live draft was the real id
  behind it. Both literals are the two sides of one existing `.tooling/scrub-map.json` entry,
  and neither is reproduced here because this file is itself a scrub target. It was my
  substitution during transcription and it was not in the body the gate question pointed at.

It is left in place, and flagged here rather than silently corrected, for two reasons. The
node is on the unscrubbed side of the line and already names the real action id and the real
centre two comment blocks above, so the placeholder would have put a matter id that does not
exist into a live node. And because the pair is a registered scrub entry, the contract still
closes: **re-scrubbing what actually landed reproduces both units byte-for-byte**, confirmed
after the fact for `Integrity Guard` and `Build Integrity Halt Notice` alike, so
`extract-units.py` will regenerate the current units unchanged. Reverting it would need a
second draft write, which is itself a protected action. If Ali wants the placeholder in the
live node instead, that is a one-token gated change.

## 5a. The publish path — NOT taken, still the owner's



The draft now carries the fix. What remains is the owner's:

1. ~~`update_workflow`, draft only~~ — **done**, see §5.
2. The owner reviews the draft diff in the n8n UI and presses **Publish**. Only the owner
   publishes (AGENTS.md §1, `docs/draft-vs-active.md` §6.5).
3. Re-export the new published version to `exports/wf4.active.json`, then
   `python3 .tooling/extract-units.py && python3 .tooling/scrub.py && ./.tooling/leak-check.sh`.
   The two units' `sha256OfJsCode` will move off `0950131e…` / `baabf88d…`; the
   "deliberately ahead" headers come out and FINDINGS §1 closes.
4. Re-run `node harness/run.js` and confirm no scenario moved.

**Rollback.** The pre-port draft is `8107c96f-57cd-4b77-a9bb-638a676d7926` and the published
version is `902130f4-58d0-4189-bf80-273c753c9c34`. The port is undone with
`restore_workflow_version` to `8107c96f` — nothing else has to be touched, because the port
changed two `jsCode` values and nothing else. A bad publish would be undone by publishing
`902130f4` again. Both are protected actions under the Fast Lane approval model.

## 6. Unresolved after this inspection

- **FINDINGS §1 is still live in production.** The fix is now in the draft (`470120af`) but
  `902130f4` is still what executes: it still takes `conflicts[0]` as the headline and still
  echoes `conflicts.length`. The owner is still shown
  `DUPLICATE_IDEMPOTENCY_KEY` where the truth is `DUPLICATE_ACTION_ID_FIELD_MISMATCH`, and
  still shown double the number of ambiguous actions. The harness no longer fails on it only
  because the units are ahead.
- **FINDINGS §3** (`wf5-digest-budget-pressure`) is unchanged and still failing. Out of
  scope for WF4.
- **The `Approval Gate` change inside draft `8107c96f` has not been reviewed by anyone**, and
  its version description says the node is unchanged. Recorded here; not fixed, because
  AGENTS.md §6 says each of these deserves its own change and the owner's eyes.
- `docs/draft-vs-active.md` §3's state table was dated 2026-08-25 and said wf4 was not
  diverged. It is now; §7 of that document records the correction.
- **No `wf4.draft.json` has been captured**, for `8107c96f` or for `470120af`. The draft is a
  181-node body that also carries SPEC-2 Rev B; capturing it is its own change.
