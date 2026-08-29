# WF4 SPEC-2 Rev B — full draft review and publication-readiness assessment, 2026-08-29

Written during the Orca Fast Lane run `run_bfa3412dc1f8`. Subject: the WF4 draft
`470120af` (SPEC-2 Rev B, 181 nodes) against the published `902130f4` (102 nodes), with
the unreviewed `Approval Gate` change `STEP1-KILLSWITCH-20260826` as the focus.

**This review is read-only against n8n.** Five MCP reads were used — `get_workflow_details`
(metadata, then full), `get_workflow_history`, `get_workflow_version(902130f4)` and
`get_workflow_versions_diff(902130f4 -> 470120af)`. No `update_workflow`, no draft write, no
publish, no activation, no execution, no external message. Nothing in n8n was changed, and
**WF4 was not published**. It follows `docs/wf4-live-inspection-2026-08-29.md`, which
recorded the earlier read-only inspection (§1–3) and the separate owner-gated two-node draft
port (§5) that produced `470120af`.

---

## 1. Phase 1 — the live instance, read-only

| field | value |
|---|---|
| workflow name | `4 - Research Drafting Approval and Dispatch` |
| workflow id | `zKr24IThF30e6jXw` |
| `active` | `true` |
| `isArchived` | `false` |
| `activeVersionId` (PUBLISHED — what production runs) | `902130f4-58d0-4189-bf80-273c753c9c34` |
| `versionId` (DRAFT — what `get_workflow_details` hands back) | `470120af-9909-4760-89d9-fc78e4074d75` |
| `activeVersion.sameAsDraft` | **`false`** (read directly from the full `get_workflow_details` payload) |
| published node count (`902130f4`) | **102** |
| draft node count (`470120af`) | **181** |
| `createdAt` | 2026-08-18T07:31:47.067Z |
| `updatedAt` | 2026-08-28T18:05:17.418Z |
| `triggerCount` | 0 (the only trigger is `When Called by Router`, an `executeWorkflowTrigger` — WF4 is a child workflow, not independently triggerable) |
| timezone | `Australia/Perth` |
| error workflow | `JfaCOxRq0FjZ5JWb` (WF9) |
| `executionOrder` | `v1` |
| `callerPolicy` | `workflowsFromSameOwner` |
| tags | none |

### Version history — every entry, newest first

| versionId | author | autosaved | createdAt | name |
|---|---|---|---|---|
| `470120af-9909-4760-89d9-fc78e4074d75` | `Owner (via MCP)` | `false` | 2026-08-28T18:05:17.422Z | *FINDINGS-1 + D-COUNT-01: rank integrity conflicts by severity* |
| `902130f4-58d0-4189-bf80-273c753c9c34` | `Owner (via MCP)` | `false` | 2026-08-25T07:36:57.144Z | *D-CHANNEL-01 + D-STATUS-01: fail-closed channel guard and status fingerprint* |

**Authors.** Both entries: `Owner (via MCP)`.

**Autosave status: none.** Both entries carry the `(via MCP)` suffix and `autosaved: false`,
so neither is a human nudging a field in the editor (AGENTS.md §5). There is no UI-autosave
entry in this history.

**One history change since the 2026-08-29 inspection.** `8107c96f-57cd-4b77-a9bb-638a676d7926`
— the SPEC-2 Rev B draft as originally authored — **is no longer in the version history**. The
owner-gated two-node port (`docs/wf4-live-inspection-2026-08-29.md` §5) replaced it with
`470120af`, and n8n's history now shows two entries, not three. `get_workflow_versions_diff`
against `8107c96f` is therefore no longer available, and the whole SPEC-2 Rev B delta had to
be read as `902130f4 -> 470120af`. That single diff carries both changes: SPEC-2 Rev B **and**
the two ported integrity fixes.

### All relevant version ids

| id | what it is |
|---|---|
| `902130f4-58d0-4189-bf80-273c753c9c34` | published; what production executes today; the body `exports/wf4.active.json` was captured from |
| `470120af-9909-4760-89d9-fc78e4074d75` | current draft; SPEC-2 Rev B **plus** the two ported integrity fixes; what a Publish press would ship |
| `8107c96f-57cd-4b77-a9bb-638a676d7926` | SPEC-2 Rev B as first authored; **no longer in history**; named as the rollback target in the gate question that authorised the port |
| `8f6b3704` | the version published before `902130f4`; historic, appears in `docs/draft-vs-active.md` §3's stale table |

---

## 2. Phase 2 — the full SPEC-2 Rev B comparison (`902130f4 -> 470120af`)

Totals: **79 nodes added, 0 removed, 4 modified, 151 connections added, 44 connections
removed.**

### 2.1 The 79 added nodes

One `Evaluate Safety` Code node, plus **39 `Guard - <name>` / `Suppressed - <name>` pairs**
(39 `n8n-nodes-base.if` + 39 `n8n-nodes-base.set`). No credential is attached to any added
node.

`Evaluate Safety` (`dc0ad0fb`, `SPEC-2-SAFETY-CONTRACT-REV-B-20260827`) reads a safety
context **from the trigger node `When Called by Router` directly** — deliberately not from an
intermediate Set node, "so an intermediate rewrite cannot launder a bad context into a good
one" — and checks, first failure wins:

1. presence of `safety_contract_version`, `dry_run`, `live_send_authorised`, `environment`,
   `safety_change_id`, `safety_signature`;
2. `safety_contract_version === '2'`;
3. shape (`dry_run`/`live_send_authorised` exactly `'true'`/`'false'`; `environment` exactly
   `'test'`/`'production'`; signature 64 lowercase hex; no `|` in `safety_change_id`);
4. the triple must form exactly `TEST` (`true`/`false`/`test`) or `LIVE`
   (`false`/`true`/`production`) — nothing else;
5. `Config.expected_environment` must be readable, and
6. must equal the inherited `environment`;
7. SHA-256 over `k=v|k=v|…` of the five signed fields must equal `safety_signature`.

`side_effects_permitted = status === 'OK' && combination === 'LIVE'`. On any failure it
re-emits the normalised fail-closed triple (`dry_run: 'true'`, `live_send_authorised:
'false'`, `environment: 'test'`) and `safety_mode: 'INVALID_FAIL_CLOSED'`, and it emits a
verdict even for zero input items "so a guard can never read undefined".

The node states in its own comment that the signature **is not authentication** — there is no
secret, so anyone who can edit a workflow can recompute a valid digest. It detects partial
propagation and in-transit rewriting, not a hostile author. That is a fair self-description
and it is worth keeping in front of the owner.

### 2.2 The guard wiring — verified mechanically, not by eye

Every one of the 39 pairs is wired identically, and this was checked over the connection
delta rather than sampled:

- all 39 `Guard - X` nodes have **exactly one** condition, byte-identical across all 39:
  `{{ $('Evaluate Safety').first().json.side_effects_permitted === true }}` (one distinct
  parameter shape across the 39 nodes);
- output **0 (true) → the real node `X`**, output **1 (false) → `Suppressed - X`**, for all
  39, with no exceptions;
- every old inbound edge of every guarded node was removed (43 of the 44 removed
  connections) and re-pointed at that node's Guard;
- **no guarded node retains or gains an inbound edge from anything except its own Guard**;
- `Suppressed - X` continues to the same downstream node the real `X` fed, so a suppressed
  run keeps flowing rather than dead-ending (28 of the 39 stand-ins carry an onward edge;
  the remainder were leaf nodes already).

The 44th removed connection and the only two added connections that involve no wrapper are
the single structural insertion: `Config -> Load Matters` became
**`Config -> Evaluate Safety -> Load Matters`**.

**Guard coverage is complete.** Of the 102 published nodes, 52 touch Gmail, Telegram, Google
Sheets, Google Drive or HTTP. All **39** that *write or send* — 3 Gmail sends, 11 Telegram
sends, 22 Sheets `append`/`appendOrUpdate` writes, 3 Drive create/share operations — are
guarded. The 13 unguarded ones are all reads: `Load Actions/Approvals/Communications/
Conflict Notices/Drafts/Evidence/Matters`, `Reload Conflict Notices`, `Reload After
Notification`, `Download Evidence Text`, `Export Document`, `Find Matter Folder`, and
`Fetch Source` (an outbound HTTP GET of public legal sources). No write or send node is
left unwrapped.

**`Evaluate Safety` dominates every guard.** Reachability over the published graph confirms
the trigger reaches `Config` before any guarded node, and no guarded node is reachable
without passing `Config` — so the node inserted immediately after `Config` has always
executed by the time any `Guard - X` evaluates `$('Evaluate Safety')`. There is no branch on
which the guard expression can throw for want of that node.

**Re-verified independently against the live draft graph.** The wiring claims above were
derived from the version diff and then checked a second time against the 181-node body
returned by `get_workflow_details`, which carries the draft's own `connections`: 39 guards;
every guarded node's **only** inbound edge is its own Guard at output 0; every
`Suppressed - X`'s only inbound edge is that Guard at output 1; `Config -> Evaluate Safety`,
`Evaluate Safety -> Load Matters`; and the gate chain intact as
`Integrity Guard -> Integrity OK? -> … -> Approval Gate -> Verify Selected Row -> Selected
Row Verified? -> Gate Result`. Zero anomalies. The live draft `Approval Gate` body contains
`STEP1-KILLSWITCH-20260826` and no longer contains the published `dryRun` line.

### 2.3 `Config` — modified (the one loosened control)

| assignment | published `902130f4` | draft `470120af` |
|---|---|---|
| `dry_run` | the literal string `"true"` | `={{ ['true','false'].includes($json.dry_run) ? $json.dry_run : 'true' }}` |
| `live_send_authorised` | *absent* | `={{ ['true','false'].includes($json.live_send_authorised) ? $json.live_send_authorised : 'false' }}` |
| `environment` | *absent* | `={{ ['test','production'].includes($json.environment) ? $json.environment : 'test' }}` |
| `expected_environment` | *absent* | the literal string `"test"` |

Nothing else in `Config` changes.

**This is the one change in SPEC-2 Rev B that removes a control rather than adding one.**
AGENTS.md §5 records that `dry_run` is hardcoded to the string `"true"` and that "much of the
safety you observe in testing comes from this one literal". After this change WF4 accepts
`dry_run` from its caller. The passthrough is itself fail-closed — an absent, blank or
unrecognised value becomes `'true'`, and the two new keys default to `'false'` and `'test'` —
so the failure mode is "stays in dry run", not "sends". But the literal is gone, and from the
publish onward WF4's dry-run posture is a property of **WF1's router call**, not of WF4. The
correctness of the caller is now in scope for every WF4 safety argument.

`expected_environment` is the hardcoded literal `'test'`. Combined with `Evaluate Safety`
check 6, that means an inherited `environment: 'production'` produces
`SAFETY_CONTEXT_CONFLICT` and fails closed. **As drafted, `side_effects_permitted` can never
become true**: the LIVE combination requires `environment === 'production'`, and the local
expectation refuses exactly that. See §5.2 — this is the single most important operational
consequence of publishing.

### 2.4 `Approval Gate` — modified: `STEP1-KILLSWITCH-20260826`

The node is 369 lines published and 373 lines in the draft. The diff is **four lines
replacing one, and nothing else** — every other line of the gate is byte-identical:

```diff
-const dryRun = String(cfg.dry_run).toLowerCase() === 'true';
+// STEP1-KILLSWITCH-20260826 - fail closed. Live sending requires all three
+// conditions to be explicitly satisfied; anything else stays in dry run.
+const _s = (v) => String(v === undefined || v === null ? '' : v).trim().toLowerCase();
+const liveSendAuthorised = _s(cfg.dry_run) === 'false' && _s(cfg.live_send_authorised) === 'true' && _s(cfg.environment) === 'production';
+const dryRun = !liveSendAuthorised;
```

**Assessment: safety-strengthening, and correctly implemented.**

- Published, one condition put the gate into send mode: `dry_run` anything other than the
  string `true`. `String(undefined).toLowerCase()` is `'undefined'`, so a *missing* `dry_run`
  already meant **send** — the old line failed **open** on absence, and only the hardcoded
  Config literal kept it shut.
- Drafted, three conditions must **all** be explicitly satisfied, each against an exact
  string, and `dryRun` is the negation. Missing, blank, null, `'TRUE '`, `'yes'`, `1` — every
  one of them lands in dry run. `_s()` null-guards and trims before folding case, so the
  three comparisons cannot be satisfied by accident.
- The change touches **only** the dry-run determination. Steps 1–8 of the gate — owner chat,
  approval exists, still `PENDING`, draft exists and unchanged, latest version, matter owner,
  `delivery_mode` in set, channel `GMAIL`, valid recipient, no `[MISSING:]`, test/placeholder
  data, unsourced legal assertions, test matter, and the four idempotency and
  key-collision refusals — are untouched. `dryRun` is read exactly once, at step 8, as the
  last check before `SEND`.
- Nothing was removed, no check was simplified, no model was added to the decision.

**Verdict on the seven bypass questions in one line: the draft cannot route around the
Approval Gate.** No connection into, out of or across `Integrity Guard -> Approval Gate ->
Verify Selected Row -> Gate Result` is added or removed; the only edges touching that chain
are `Gate Result`'s six outbound edges, each re-pointed from `X` to `Guard - X` **on the same
output index** (0, 2, 3, 4, 5, 6 — preserved pairwise). The gate keeps deciding; the guards
sit strictly *downstream* of its decision and can only ever demote a real write to a
suppressed one.

### 2.5 `Integrity Guard` and `Build Integrity Halt Notice` — modified

These two are **not** SPEC-2 Rev B. They are the owner-gated port of the FINDINGS §1 /
D-COUNT-01 fixes recorded in `docs/wf4-live-inspection-2026-08-29.md` §5, and they appear in
this diff only because `8107c96f` has left the history. Verified in §3.3 below.

### 2.6 Removed nodes, credentials, routes, side effects

- **Removed nodes: none** (0).
- **Credential changes: none.** No added node carries a `credentials` block; no modified
  node's delta touches `credentials`. The four modified nodes changed exactly one parameter
  each (`Config.assignments`, and `jsCode` on the three Code nodes).
- **Route changes:** only the guard interposition and the `Evaluate Safety` insertion
  described above. No route is added that reaches an external system by a new path.
- **Side-effect changes:** strictly subtractive. Every external effect is now conditional on
  `side_effects_permitted === true`, and no new external effect is introduced —
  `Suppressed - X` is a Set node that stamps `safety_suppressed: true`,
  `safety_suppressed_node`, `safety_suppressed_kind` (e.g. `GMAIL_SEND`),
  `safety_suppressed_reason`, `safety_mode`, `side_effect_blocked: true`,
  `safety_gate: 'DRY_RUN'`, `operation_status: 'TEST_SUPPRESSED'` and passes the item on.
- **Changes that could bypass human approval: none found.**
- **Changes that could publish, activate, execute or send externally: none.** The draft adds
  no node capable of any of those.

### 2.7 Safety-strengthening differences

1. `STEP1-KILLSWITCH-20260826` — three explicit conditions replace one, and the
   fail-on-absence direction is inverted from open to closed (§2.4).
2. `Evaluate Safety` — an inherited, verified, fail-closed safety contract read from the
   trigger node, with a normalised fail-closed re-emission (§2.1).
3. 39 guard/suppress pairs covering **every** write and send node, with complete coverage
   confirmed mechanically (§2.2).
4. The new `Config` keys default fail-closed (`'false'`, `'test'`), and `dry_run`'s
   passthrough refuses any value that is not exactly `'true'`/`'false'` by falling back to
   `'true'`.

### 2.8 Differences that are unreviewed or inaccurately described

1. **The draft's own version description understates the change.** `8107c96f` was titled
   *"SPEC-2 Rev B: verify inherited safety contract"* and asserted that "guards, suppressed
   nodes, the approval gate, prompts, routes, owner checks, model settings and register logic
   unchanged". The `Approval Gate` `jsCode` **is** changed by that draft. Per AGENTS.md §1.1
   the Approval Gate is the one node whose edits must never be described as "unchanged". The
   edit is safety-strengthening, but it was described inaccurately and, until this review,
   nobody had read it. **This review closes that gap.** (The current draft's own description,
   `470120af`, describes only the integrity port — it does not restate the SPEC-2 Rev B
   contents at all, so the inaccurate description is what remains on the record for those
   79 nodes.)
2. **`Config.dry_run` losing its literal is not called out anywhere** in the draft
   description, and it is the one control the change removes (§2.3).
3. **`expected_environment: 'test'` makes the LIVE combination unreachable**, which is not
   stated in any description (§2.3, §5.2).
4. **`Evaluate Safety` depends on `crypto.subtle`.** AGENTS.md §5 records that the n8n Code
   sandbox has no `crypto` module — that is why WF4 hand-rolls FNV-1a. If `crypto.subtle` is
   likewise unavailable at runtime, `computed` stays `''` and the node returns
   `SAFETY_SIGNATURE_UNVERIFIABLE` and fails closed. That is the safe direction, but it means
   the whole contract could be permanently in its failure state for a reason nobody has
   tested. **This is not verifiable offline** — the harness cannot answer it and neither can
   a diff. It needs one controlled execution, which no approval in this run covers.

---

## 3. Phase 3 — repository comparison

### 3.1 Does the published export still match production? **Yes, exactly.**

`exports/wf4.active.json` was compared against a fresh `get_workflow_version(902130f4)`
fetched today: 102 nodes live, 102 in the export, same names, none added or removed. Applying
`.tooling/scrub-map.json` to the live payload leaves **0 nodes differing** and the
`connections` object **byte-identical**. No unexpected drift. (This re-confirms the same
check made on 2026-08-27 and 2026-08-29.)

### 3.2 Does the draft match the documented 181-node version? **Yes, with one correction.**

The live draft is 181 nodes, as documented. But the documents name the draft `8107c96f`; the
live draft is `470120af`, and `8107c96f` is gone from the history. `docs/draft-vs-active.md`
§7 and `docs/wf4-live-inspection-2026-08-29.md` §4 both describe SPEC-2 Rev B under the
`8107c96f` id. §4 of the inspection record remains accurate as a description of the 79-node
delta — this review re-derived every claim in it from `902130f4 -> 470120af` and found no
error — but the id it is filed under is stale. `docs/draft-vs-active.md` §8 (added by this
review) records the move.

### 3.3 Are the two integrity fixes present only in the draft? **Yes — proved byte-for-byte.**

Re-scrubbing the live bodies with `.tooling/scrub-map.json` and comparing against the
BEGIN/END VERBATIM block of each unit:

| node | scrubbed **published** body == unit | scrubbed **draft** body == unit |
|---|---|---|
| `Integrity Guard` | **no** (unit is ahead, as declared) | **yes, byte-for-byte** |
| `Build Integrity Halt Notice` | **no** (unit is ahead, as declared) | **yes, byte-for-byte** |
| `Approval Gate` | **yes, byte-for-byte** | **no** (draft carries the kill switch) |

Three things follow. The port recorded in `docs/wf4-live-inspection-2026-08-29.md` §5 landed
exactly as staged — including the one-token transcription deviation flagged there, which
re-scrubs to the placeholder and therefore leaves the round trip intact, now independently
re-confirmed. Production still runs both defects. And `harness/units/wf4/approval-gate.js` is
the **published** gate, not the drafted one.

### 3.4 Is the Approval Gate change fully documented? **Now, yes. Before this review, no.**

It was described as "unchanged" by the draft that made it (§2.8.1), recorded as unreviewed in
`docs/wf4-live-inspection-2026-08-29.md` §6 and `docs/draft-vs-active.md` §7, and quoted but
not analysed. This document is the review: the exact diff (§2.4), its fail-open-to-fail-closed
direction, its interaction with `Config` (§2.3), and its bypass analysis (§2.4, §2.2).

### 3.5 The approved gate record `gate_0d2012146a1b`

Retrieved with `orca orchestration gate-list --run run_fe5d400247aa`:

| field | value |
|---|---|
| gate id | `gate_0d2012146a1b` |
| task | `task_867338791f4c` (`owner-gate`) |
| run | `run_fe5d400247aa` |
| options | `["approve","deny"]` |
| status | **resolved** |
| resolution | **`approve`** |
| resolved at | **2026-08-28 17:59:03** |

The question is reproduced verbatim in `docs/wf4-live-inspection-2026-08-29.md` §5. It
authorised **only** the two-node `jsCode` write to the draft. It did not authorise publish,
activation, execution or any external effect, and none was taken then or now. What actually
landed matches what the question described (§3.3).

### 3.6 The other repository artefacts

- `harness/units/wf4/integrity-guard.js` and `build-integrity-halt-notice.js` — ahead of
  published, equal to the draft, headers correctly declaring the **published** sha they are
  ahead of. Correct and honest.
- `harness/FINDINGS.md` — §1 carries an accurate 2026-08-29 status block. Its **intro line
  was stale**: it said three scenarios fail, when the §1 fixes moved two of them to passing.
  Corrected by this review; §1 itself is unchanged and stays open, because production still
  runs the defect.
- `docs/draft-vs-active.md` — §3's table is stale (it predates the publish), §7 corrects it
  but names the superseded draft id. §8 added by this review.

### 3.7 Can the draft be safely considered for publication?

**No — not today. This review's verdict is NO-GO, and it is not close to a GO.** The draft may
be *considered* — it is a coherent candidate, and nothing in the 79-node delta weakens the
approval gate, bypasses human approval, or creates a new external effect; the one genuine
loosening (`Config.dry_run`) is compensated twice over by the kill switch and the guards. But
"considered" is not "ready", and the distinction is the whole point of this section. Every one
of the four conditions in §5.3 is unmet as of today, and two of them (the untested drafted
gate body, the unverified `crypto.subtle` dependency) mean the safety behaviour that makes
this draft attractive **has been read and not run**. A change to the one node standing between
a model-drafted letter and a real recipient does not get published on a reading.

Publication readiness is therefore **not proven**, and nothing in this document should be
cited as proving it.

---

## 4. Testing

### 4.1 What was added, and why it was needed

Before this run, `harness/units/wf4/approval-gate.js` was exercised only by the three
delivery-key families (`delivery-key`, `delivery-key-retry`, `delivery-key-no-clock`). All
three assert the derivation block — `send_key`, `communication_id`, the 16-hex shape, clock
independence — and the delivery-key adapter's `default:` arm **fails** any scenario that
tries to assert `gate`. So every gate DECISION (`INVALID`, `DUPLICATE`, `STALE`, `REJECTED`,
`EDIT`, `DRY_RUN`, `SEND`) was unasserted: the node AGENTS.md §1.1 calls the only thing
between a model-drafted letter and a real recipient had **no executable fail-closed test**.

This review adds the `approval-gate` adapter (`harness/adapters.js`). It feeds the real
extracted node a full five-register context (`Config`, `Load Approvals`, `Load Actions`,
`Load Drafts`, `Load Communications`, `Load Matters`) and asserts `gate`, `gate_reason`
substrings, the `dry_run` boolean, `Config` passthrough on a refusal, and the presence or
absence of the delivery identity. Unknown `expect` keys still fail through `default:`, so the
anti-weakening rule of `harness/adapters.js` holds. No existing assertion was weakened and no
unit was edited.

Scenario counts, and the DeepSeek test leg's results, are recorded in the run report
(`.fastlane-orchestrator-done.txt`) and in the pull request.

### 4.2 The coverage gap this review could not close

**The drafted Approval Gate is not under test, and cannot be, today.** `harness/units/` is
extracted from `exports/wfN.active.json` only (AGENTS.md §5) — that is deliberate: the
harness's job is to tell the truth about what is *running*. No `wf4.draft.json` has been
captured, so no unit exists for the drafted gate, for `Evaluate Safety`, or for the guard
expression. Everything asserted by the harness about WF4's Approval Gate is an assertion
about **`902130f4`, the body without the kill switch**.

The kill switch is therefore reviewed here by inspection of the live draft body (§2.4), which
is exact — the diff is four lines and was read verbatim from the instance — but it is *not*
executed. Closing that gap is §5.3 condition 1.

---

## 5. Publication-readiness assessment

### 5.1 What publishing would ship

The 79-node safety contract, the `Config` passthrough, the Approval Gate kill switch, **and**
the two integrity fixes — as one indivisible unit. The owner cannot publish the two-node
integrity fix without also publishing SPEC-2 Rev B in full. That remains true and is the
reason this review exists.

### 5.2 The operational consequence the owner must want

With `expected_environment` hardcoded to `'test'`, `side_effects_permitted` cannot become
`true` (§2.3). On the first execution after a publish, **every Gmail send, every Telegram
message, every Sheets write and every Drive write in WF4 routes to its suppressed stand-in.**
The workflow keeps running end to end and stamps `operation_status: 'TEST_SUPPRESSED'`, but
the register stops being written and the owner stops receiving Telegram messages from WF4.

That is the fail-closed design working as intended — and it may be exactly what is wanted
while SPEC-2 is bedded in. But it is a behaviour change to a live system that no version
description states, and it must be a decision, not a discovery. To ever send again, WF1 must
author and sign a valid LIVE context **and** WF4's `expected_environment` must be moved to
`'production'` — a second draft change, and its own protected action.

### 5.3 What must be fixed before publication

Until all four are done, the answer to "may we publish?" is **no**.

1. **Capture `exports/wf4.draft.json` and extract draft units for `Approval Gate`,
   `Evaluate Safety` and one `Guard -` node, then cover the kill switch with scenarios**
   against the drafted body: `dry_run: 'false'` alone must stay `DRY_RUN`; all three
   conditions must be required; missing/blank/`'TRUE '`/non-string values must stay
   `DRY_RUN`; `side_effects_permitted` must be `false` for every non-LIVE verdict. Right now
   the kill switch has been read, not run.
2. **Confirm `crypto.subtle` exists in the n8n Code sandbox** (§2.8.4) by one controlled
   execution. If it does not, `Evaluate Safety` is permanently in
   `SAFETY_SIGNATURE_UNVERIFIABLE` and the contract's verification step is decorative — safe,
   but not what it claims to be.
3. **Verify the caller.** `Config.dry_run` is now WF1's to set (§2.3). WF1 must be shown to
   author the full six-field signed context, or WF4 arrives with an absent context, fails
   closed, and §5.2 becomes permanent by accident rather than by choice.
4. **Decide §5.2 explicitly**, and correct the record: the draft description that calls the
   Approval Gate "unchanged" should not be the last word in the instance's own history.

Publishing is a protected action under the Fast Lane approval model and under AGENTS.md §1 —
only the owner publishes. **No approval to publish was sought or given in this run.**

### 5.4 Rollback

This review changed nothing in n8n, so there is nothing in n8n to roll back; the repository
change is undone by reverting the pull request. Had a publish occurred, it would be undone by
publishing `902130f4` again. The draft's own pre-port ancestor `8107c96f` is **no longer in
the version history**, so `restore_workflow_version` to it — the rollback named in the
approved gate question of 2026-08-28 — is no longer available. The two integrity fixes could
now only be reversed by writing the published bodies back into the draft.

---

## 6. Unresolved after this review

- **FINDINGS §1 is still live in production.** `902130f4` still takes `conflicts[0]` as the
  headline and still echoes `conflicts.length`. The fix is in the draft and cannot reach
  production without a publish that also ships SPEC-2 Rev B.
- **FINDINGS §3** (`wf5-digest-budget-pressure`) still fails. WF5, out of scope.
- **No `wf4.draft.json` has been captured** for `8107c96f` or `470120af`. Per
  `docs/draft-vs-active.md` §2 the absence of a draft file is the claim that draft == active,
  and for WF4 that claim is false. This is now also the reason the kill switch has no test
  (§4.2, §5.3.1).
- **`8107c96f` is unrecoverable** — out of history, so out of reach of
  `restore_workflow_version` (§5.4).
- **`crypto.subtle` in the Code sandbox is unverified** (§2.8.4).
- **WF1's side of the safety contract is unverified** (§5.3.3).
- AGENTS.md §6's seven open safety issues are untouched by this review. §6.5 and §6.6 of that
  list (`Verify Selected Row` treating a gate channel of `NONE` as a free pass; the row
  fingerprint omitting `status`) were closed in `902130f4` by D-CHANNEL-01 / D-STATUS-01;
  the rest stand.

---

## 7. Adversarial review of this document (Codex, run `run_bfa3412dc1f8`)

Codex reviewed the three commits on this branch, this document, the `approval-gate` adapter,
the eleven `wf4-gate-*` scenarios, and the DeepSeek test evidence. It has no n8n credentials
and did not re-fetch the live readings; it checked them for internal consistency and against
the repository. Its verdict is advisory (AGENTS.md §4).

**Round 1 — REFUTE, "WF4 publication readiness not yet proven".** Its seven answers:

1. *Is the Approval Gate fail-closed?* The **published** gate's exercised paths are, but the
   **drafted** gate cannot be certified fail-closed while its kill-switch body is not
   harness-executed and `Evaluate Safety`'s `crypto.subtle` dependency is unverified.
2. *Can any route bypass human approval?* No bypass route was found in the documented draft
   graph.
3. *Is the kill switch correctly implemented?* Correctly expressed as an
   all-three-conditions-required fail-closed check **by inspection**, but untested.
4. *Are the 79 nodes understood and documented?* Internally consistent and extensively
   documented.
5. *Is the draft safe to consider for publication?* Not yet safe to publish.
6. *What must be fixed first?* Capture and test the draft units, verify `crypto.subtle`,
   verify WF1's signed caller contract, and explicitly decide and document the
   `expected_environment: 'test'` suppression consequence.
7. *Is another decision gate required?* Yes — a separate owner decision gate before any
   publish or live-environment change; none is needed for this read-only review.

Evidence it cites: harness 109/1/60 with the sole pre-existing WF5 failure, `scrub.py --check`
0 replacements, and all eleven new fixtures pure, unique, and adapter-validated with unknown
`expect` keys failing rather than being silently dropped.

**What was changed in response.** Codex named no factual error — its six conditions are
§5.3's four conditions, and its answers 1–4 and 7 restate §§2.2, 2.4, 4.2 and 5.3. What it
refused was the *framing*: §3.7 answered "can the draft be considered for publication?" with
"yes, as a candidate", which reads as a qualified go when the honest answer is a no-go with a
route to yes. §3.7 and §5.3 were rewritten to say that plainly. No finding, no test and no
assertion was changed, because none was disputed.

**Round 2 — APPROVE, "round-1 framing fix is complete".** Codex re-read the document and
`c056bc5` and found no remaining defect: the qualified-GO ambiguity is gone, §7 accurately
records the prior REFUTE and that the drafted gate was read rather than run, and no n8n change
occurred. Its seven answers are unchanged from round 1, with (5) restated as *"the draft is
not safe to publish today"* and (6) as the four §5.3 conditions.

**Two REFUTE rounds were available; one was used.** The final verdict is APPROVE — of *this
review record*, not of the draft. The draft's verdict is §3.7: NO-GO.
