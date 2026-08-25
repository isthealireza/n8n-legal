# Group B notes — retired one-shot QA workflows, mined for test knowledge

Nine retired QA workflows in n8n, read-only, converted to 24 portable scenario files in
this directory. Everything below is what the workflows encode, not what they claim in
their descriptions.

All identifiers here are sanitised. The production spreadsheet id is
`SHEET_ID_PLACEHOLDER`, the owner chat id is `OWNER_CHAT_ID`, real matter ids became
`MAT-20260101-00N`, real approval ids became `APR-` + 16 uppercase hex of the same
length, real emails point at `example.test` / `examplecarpark.test`. Formats and string
lengths are preserved so length and hash assertions still mean something.

---

## 1. QA - Ingress Round Trip (`XevQwFviJHUobw0U`, 38 nodes, 2026-08-21)

**What it was really testing.** Not the resolver logic — that was already proven pure
elsewhere. It was testing the *round trip*: that the ingress fingerprint computed on a
first delivery is actually persisted into `Communications` column R, read back off the
sheet on the next round, and compared correctly. A resolver that is right about a
fingerprint it never stores is useless: every replay looks like a first delivery.

**Production node it copied code from.** WF5 → **Build Reply Context**. The comment in
`Resolve R1` says it is "the same compacted copy as the policy harness
(`BAKIml11QKedtH9d`), which mirrors the WF5 draft's Build Reply Context". I confirmed
against `/root/n8n-legal/exports/wf5.active.json`: the production `Build Reply Context` node
carries the identical `ingressFingerprint`, `canon`, `emailOf`, `tagsIn` helpers and the
same five decision values (`ACCEPT`, `ALREADY_RECORDED`, `IDEMPOTENCY_CONFLICT` ×2 bases,
`BLOCKED`), and feeds a `Sender Verified?` IF node with `matched = decision === 'ACCEPT'`
— structurally the same gate the QA workflow calls `Accept R1/R2/R3`.

**Design facts worth keeping.**
- The fingerprint is built from stable *ingress* fields only — `provider_message_id`,
  `thread_id`, sender address, subject, raw body, provider timestamp — and deliberately
  never from `summary`, `classification` or a regenerated `communication_id`. The header
  comment records why: "An earlier harness did exactly that, which is how the mistake was
  found." Comparing downstream products made every ordinary retry a false conflict.
- `communication_id` is `'COM-' + provider_message_id`, deterministic, so the value in
  the Telegram notice, the value written to the sheet and the value returned on replay are
  the same string. Test `t10` in `Report Round Trip` asserts this across all three rounds,
  the stored row *and* the simulated notice text.
- Only the digest is stored, never the raw body: "the body stays in Gmail and Drive."
- Rounds 2 and 3 contain deliberate poison writes behind the gate
  (`COM-SHOULD-NOT-HAPPEN`, `summary: 'R2 OVERWROTE THE ROW'`). They exist so a gate
  failure shows up as text in the sheet instead of as a silent pass.

**Scenarios written.** `wf5-ingress-first-delivery-accept`,
`wf5-ingress-replay-identical-body`, `wf5-ingress-replay-changed-body`,
`wf5-ingress-replay-fingerprint-not-recorded` (all pure),
`wf5-ingress-round-trip-fingerprint-persistence` (integration — the only one that needs
live Sheets), plus two **derived** branch scenarios flagged `"derived": true`:
`wf5-ingress-sender-not-a-party` and `wf5-ingress-thread-tag-mismatch`. The QA workflow
only drove the happy path through those branches; the fixtures are mechanical variants of
its own register, not invented data.

---

## 2. QA - Guarded Replay Test (`c6YPmuWf3cevjZ3r`, 37 nodes, 2026-08-20)

**What it was really testing.** That replay safety comes from a *gate*, not from the
storage layer. The `Decide R1` header states it flatly: "appendOrUpdate is not relied on
for replay safety: it cannot be a no-op, because update-on-match is what it does. The
gate downstream is what makes a replay a no-op." Written the same day as, and directly in
response to, the negative result from QA - Replay Write Test.

**Production node it copied code from.** The three-way decision (`NEW_INBOUND` /
`ALREADY_RECORDED` / `IDEMPOTENCY_CONFLICT`) is the idempotency-key-shaped ancestor of
what became the fingerprint-based resolver in WF5 `Build Reply Context`. Note the
difference and keep it: this version compares `communication_id, subject, summary,
classification, received_at` — i.e. *downstream products*. That is exactly the mistake the
Ingress Round Trip comment says was later found and corrected. **These two workflows
disagree, and the later one is right.** The guarded test's value is the gate topology
(read register → decide → IF on `allow_mutations` → writes), not its comparison field
list.

**Scenarios written.** `wf5-guarded-replay-first-delivery-new-inbound`,
`wf5-guarded-replay-same-key-different-content` (pure),
`wf5-guarded-replay-same-key-identical-content` (pure, **derived** — the workflow drove
only the conflicting branch), `wf5-guarded-replay-event-row-does-not-multiply`
(integration; round 3 re-runs the identical replay to prove one audit row, not two).

---

## 3. QA - Replay Write Test (`xb9hgu2rpMjw9CUt`, 31 nodes, 2026-08-20)

**What it was really testing.** Whether Google Sheets `appendOrUpdate` matched on
`idempotency_key` is, on its own, replay-safe. **The answer was no**, and the workflow
honestly reports it: verdict `PARTIAL - Communication and action deduplication proven;
full replay idempotency not proven`.

**What it proved and disproved.**
| Check | Result | Why |
|---|---|---|
| `r1_communication_rows_unchanged` | passes | one row per key — row-level dedup works |
| `r2_original_content_unchanged` | **fails** | update-on-match overwrites every mapped column; the first delivery's content is destroyed |
| `r3_actions_unchanged` | passes | same key on Actions |
| `r4_matter_unchanged_on_replay` | **fails** | `Touch Matter Replay` writes `REPLAY-RUN-STAMP` over `FIRST-RUN-STAMP` |
| `r5_inbound_event_no_duplicate` | **fails** | events use plain `append` with hand-written distinct ids (`EVT-FIRST-001`, `EVT-REPLAY-002`), so they multiply |

**Two Sheets facts it discovered that the harness must encode.**
1. `appendOrUpdate` only exercises its matching path when the tab already has data rows.
   Against an empty tab the first write always appends and proves nothing — hence the
   canonical seed row per tab, whose `idempotency_key` is *deliberately different* from
   the key under test so it can never be the row matched.
2. A Sheets read of a header-only tab returns **one item whose `json` is an empty
   object**. Item counts and row counts are different quantities; every `Report` node in
   this group filters on `Object.keys(r).filter(k => k !== 'row_number').length > 0`.

**Scenario written.** `wf5-appendorupdate-is-not-replay-safety` (integration). Its
`expect` block deliberately records three **false** values. A harness that turns them
green has changed the meaning of the test, not fixed a bug.

---

## 4. QA - Add Ingress Fingerprint Column (`kBcbUbZAwGifd9rZ`, 4 nodes, 2026-08-21)

A one-shot schema migration, not a test. It `PUT`s the single header cell
`Communications!R1 = "ingress_fingerprint"` through the raw Sheets values API with
`valueInputOption=RAW`, then reads the header row back (`headerRow: 1, firstDataRow: 1`)
and asserts the column is present. Adds a column only; appends no row and touches no data.

Converted to the invariant
`wf5-communications-schema-18-columns-with-ingress-fingerprint`: 18 headers, in the fixed
order, with `ingress_fingerprint` as column R. If that column is dropped, renamed or
reordered, the resolver reads a blank fingerprint on every message and degrades to
`FINGERPRINT_NOT_RECORDED` universally.

---

## 5. QA - Communications Delivery Key Census (`vrP4KZLwrsAbekc1`, 3 nodes, 2026-08-21) — DIAGNOSTIC QUERY

Read-only, `GET` only, one `values:batchGet` over `Communications!A1:Z2000`,
`Approvals!A1:Z2000`, `Actions!A1:Z2000`. Writes nothing. No fixtures were invented for it.

### The 8-char vs 16-char delivery-key question, precisely

The census's two regexes:

```
OLD  ^SND-[0-9a-f]{8}(\|DRY)?$      (case-insensitive)
NEW  ^SND-[0-9a-f]{16}(\|DRY)?$     (case-insensitive)
```

Both formats are produced by the **same** node: **WF4 → `Approval Gate`** (the code node
that derives `send_key`, `dry_key`, `communication_id_send`, `communication_id_dry`).
The pre-image is identical in both eras:

```
deliveryIdentity = 'apr=' + approval_id
                 + ' act=' + action_id
                 + ' draft=' + draft_id
                 + ' chan=' + UPPER(action.channel || 'NONE')
                 + ' to='  + normEmail(action.recipient)
```

- **8-char (old).** Pre-`F-02` code: a **single 32-bit FNV-1a pass**, offset basis
  `0x811c9dc5`, rendered `('0000000' + h.toString(16)).slice(-8)` → 8 lowercase hex.
  Retired because 32 bits reaches ~1% birthday-collision probability by roughly 10,000
  deliveries, and the gate's own comment spells out why that is not cosmetic: "two
  different approved deliveries would share `communication_id` and `send_key`, so one
  would silently overwrite the other's Communications row and the sheet could no longer
  answer whether a particular legal communication was sent."
- **16-char (new).** Post-`F-02` code:
  `fnv1aHex(s) = fnv1aPass(s, 0x811c9dc5) + fnv1aPass('K2|' + s + '|K2', 0x01000193)` —
  two independent FNV-1a passes with different offset bases over differently salted
  input, 8 hex each, concatenated to 16. It is a doubled FNV rather than a real digest
  because "the n8n Code sandbox has no crypto module". Moves the same 1% point beyond
  ~600 million deliveries.
- Companion ids follow the same hash: `COM-<hash>` for a real send, `COM-DRY-<hash>` for a
  dry run; the dry key is the send key plus the literal suffix `|DRY`.
- Deliberately **excluded** from the key: any clock (the previous code stamped
  `communication_id` with `$now`, so a retry produced a second row), and `delivery_mode`
  (changing it requires a new approval, which already changes `approval_id`).
  `normEmail` strips `Name <addr>` and lowercases, so
  `A. Smith <A.Smith@Example.COM>` and `a.smith@example.com` are one delivery.
- **The known one-time effect, which is why this census exists:** an old 8-character-key
  Communications row is not matched by the new 16-character key, so the first write per
  approval after `F-02` appends instead of updating.

### What the census was looking for

1. How many `SND-` rows are in each format, plus a third bucket (`other_key_format_count`)
   for anything matching neither — a hand-edited or corrupted key.
2. Every `OUTBOUND_PENDING` and `OUTBOUND_UNCERTAIN` row, listed in full. Each of these
   permanently blocks any further send on its key (gate checks 7b and 7b-2), so each is a
   live human-owned obstruction. `OUTBOUND_UNCERTAIN` exists because of `F-04`:
   `Mark Send Failed` used to stamp every send-path error as `OUTBOUND_FAILED`, including
   a network timeout that may have occurred *after* Gmail accepted the message — and
   since check 7c deliberately ignores `OUTBOUND_FAILED` so a known failure doesn't block
   a retry, an uncertain outcome was being converted into permission to send the same
   legal communication twice.
3. The cross-check that is the real point: **PENDING approvals whose Communications rows
   carry an old-format key.** On a decided approval the migration residue is harmless. On
   an undecided one it is dangerous: the gate derives a 16-char key, matches nothing, and
   its duplicate / pending / uncertain checks all see an empty result set — so a send that
   was already attempted proceeds as if it never had been.

**Invariants written:** `wf4-delivery-key-is-16-char-format`,
`wf4-no-unresolved-outbound-pending-or-uncertain`,
`wf4-pending-approval-not-stranded-on-legacy-key`.

---

## 6. QA - Daily Report State Census (`3TVCLIVFGlBNSwK4`, 3 nodes, 2026-08-22) — DIAGNOSTIC QUERY

Read-only `values:batchGet` over `Actions`, `Matters`, `Approvals`, `Drafts` (A1:Z3000
each). Writes nothing. Built because "the daily report discrepancies" needed attributing
to either the digest's arithmetic or the register's contents.

**What it was looking for, and the shape of the answer it was designed to give.**
- `actions_total_rows` vs `distinct_action_ids`, and `open_rows` vs
  `distinct_open_action_ids`. If rows exceed distinct ids, the digest over-reports open
  work by exactly the duplicate count and no change to the digest can fix it. "Done" is
  `COMPLETED | SENT | FAILED`; open is anything else.
- `duplicate_action_ids`, each reported with sheet row number, status, matter_id,
  idempotency_key and a 60-character slice of `blocked_reason`.
- `duplicate_ids_with_conflicting_status` — duplicates whose rows *disagree* about status.
  A plain duplicate is recoverable; a conflicting one means the register cannot answer
  whether the action is done, and "last row wins" is a guess. The census computes
  `status_breakdown` (per row) and `status_breakdown_distinct` (last row per id) side by
  side so the gap is visible.
- `actions_with_multiple_pending_approvals`.
- `approvals_pending_detail`: for each PENDING approval, its `draft_version` against
  `latest_version_for_action` (max version over all Drafts rows for that action), and the
  literal string `(no draft row)` where the `draft_id` resolves to nothing.

**Invariants written:** `wf5-actions-no-duplicate-action-id`,
`wf5-actions-no-conflicting-status-on-one-action-id`,
`wf4-one-pending-approval-per-action`, `wf4-pending-approval-references-latest-draft`.

---

## 7. QA - Approval Supersede Audit (`Z0phpkSNeLngQpl1`, 7 nodes, 2026-08-21)

Not a census — a one-shot *mutation* with a read-before-mutate guard, and the best worked
example of that pattern in the group. It confirmed two named approvals were still PENDING,
marked them `SUPERSEDED`, and wrote one deterministic audit event each.

**The reasoning it encodes, verbatim in its comments.**
- *Why SUPERSEDED and not VOID:* "each of these was a genuine approval request for the
  draft current at the time, and a later draft replaced it. VOID would assert something
  untrue about the original request. SUPERSEDED records what actually happened."
- *KEEP is asserted, not assumed:* if the approval that is supposed to survive is not
  present exactly once and PENDING, **nothing is superseded at all** — "leaving an action
  with no live approval would be a worse state than leaving stale ones."
- Per-target refusals for: absent, duplicated (a duplicate key must be resolved by a
  human), already SUPERSEDED, any status other than PENDING ("I will not overwrite a
  recorded decision"), and wrong matter.
- The audit message states in words that this was an audit action and not a decision: "it
  was NOT approved and NOT rejected." Truncated to 900 characters.
- Event id `EVT-APPROVAL-SUPERSEDED-<approval_id>` written with `appendOrUpdate` on
  `event_id`, so re-running updates one row per approval rather than appending more.

**Root cause it records:** each end-to-end QA rerun of one drafting action raised a fresh
approval request, so three PENDING approvals accumulated on a single action.

**Scenario written:** `wf4-supersede-stale-pending-approval-read-before-mutate` (pure —
the decision logic is a function of the register snapshot; only the Sheets write is I/O).

---

## 8. QA - Sources Row Census (`k0IFnNVRdtMOEmjP`, 3 nodes, 2026-08-21) — DIAGNOSTIC QUERY

Read-only, writes nothing. Its own comment states the question better than a summary
could: "after changing Append Sources from append to appendOrUpdate on source_id, did the
rerun CORRECT the four contaminated rows in place, or did it add four more alongside them?
A row count is the only honest way to tell, because both outcomes look identical in the
execution log."

**Looking for:** total Sources rows, rows per matter, any `source_id` appearing more than
once anywhere, and for one nominated matter the row count against the distinct-source_id
count plus `title`, `url`, `publisher`, `source_type`, `verification_status` and an
80-character slice of `pinpoints` so citation integrity can be checked by eye. Rows with a
blank `source_id`, and a stray literal header row where `source_id == 'source_id'`, are
excluded before counting.

**Invariant written:** `wf4-sources-no-duplicate-source-id`. The generalisable lesson,
recorded as an assertion: switching a writer from `append` to `appendOrUpdate` must be
verified by reading row counts back off the sheet, never by reading the execution log.

---

## 9. QA - Stage 2 Single TEST ONLY Matter (`TryzWP4S2VpL8OU0`, 4 nodes, 2026-08-23)

The newest of the group and the most disciplined. One synthetic scenario, `dry_run: true`,
no recipient, no channel, no external destination, calling QA WF2 (`T6jGZRxNd9pVOfHi`) in
`mode: each` with `waitForSubWorkflow: true`. Settings pin
`saveDataSuccessExecution: 'all'` and a 180-second timeout so the whole plan stays
inspectable. Deliberately shrunk to the smallest bounded case after larger autopilot loops
made failures hard to attribute; the item shape mirrors what QA Autopilot's
`Loop Scenarios` hands to QA WF2.

**Eighteen assertions**, grouped: matter creation; classification
(`motor_vehicle_damage_v1` from a car-park damage narrative); missing-information handling
(`requires_information`, `matter_status = NEEDS_INFORMATION`, ≥1 missing fact, ≥1 question,
no duplicated questions after normalising to lower-case alphanumerics); action creation
with no duplicate `action_id` and no duplicate `idempotency_key`, every action carrying the
matter's id; and the "nothing escaped" set — no `approval_id` on any action, `channel` in
`{NONE, ''}`, empty `recipient`, no action already `SENT | COMPLETED | FAILED`.

**Production node it copied code from.** The last assertion embeds the `isTestMatter`
predicate **verbatim from WF5 `Build Daily Digest`, node `983da561`** — id prefixes
`MAT-TEST` / `MAT-QA` / `MAT-SANDBOX`, title wording `TEST ONLY` or `DO NOT USE`, fact
flags `test_data_only` / `matter_flagged_test_only` / `is_test` equal to `TRUE`, and risk
flags matching `TEST_ONLY | SYNTHETIC | DO_NOT_USE`. Copying it verbatim is the point: it
catches drift between the digest's copy and the harness's copy.

**Honest about coverage.** Its `not_exercised` array names three things it did *not*
prove: WF4 Integrity Guard (unreachable from WF2 classification — no draft or approval
stage ran), the ConflictNotices write path (no writer exists yet), and Daily Digest
reporting of this matter (QA WF2 writes nothing, so the matter never reaches the
register). That list is preserved in the scenario's `expect`.

**Scenarios written:** `wf2-stage2-single-test-only-matter` (integration — it genuinely
executes a sub-workflow) and `wf5-digest-is-test-matter-predicate` (pure, 13 cases
including malformed JSON, a null matter, and one genuinely live matter that must **not**
be flagged).

---

## Assertions that could not be converted, and why

- **"Verdict: ROUND TRIP PROVEN" / "FULLY_PROVEN" as single booleans.** These are `&&`
  chains over 7–8 sub-checks. Collapsing them loses which check failed, so each sub-check
  became a named assertion instead. The composite verdict is kept only as a field in the
  integration scenarios' `expect`.
- **`comms_header_count_after_seed = 18` measured by `Object.keys` of the first read
  row.** This is a Sheets-read artefact, not a schema fact — it counts keys present on the
  first data row, which a sparse row would undercount. Kept as an integration expectation
  and restated properly as a header-row invariant in
  `wf5-communications-schema-18-columns-with-ingress-fingerprint`.
- **`simulated_telegram_notice`** in `Report Round Trip` is a hand-built string
  (`'Logged as: ' + d1.communication_id`) standing in for WF5's `Build Reply Notice`. It
  is not the production node, so it is captured as an assertion about determinism
  ("`communication_id` is identical in the owner notice") rather than as a fixture with an
  expected message body.
- **Live-register counts.** The five census workflows return actual numbers off the
  production sheet (row counts, per-matter breakdowns, lists of specific approval and
  action ids). None of those numbers were converted into fixtures — they are observations
  of a moving register, not test data. Each became an invariant with an empty `input`
  describing the property the harness should assert, per instruction.
- **`Approval Gate` gate outcomes** (`DRY_RUN`, `SEND`, `STALE`, `DUPLICATE`, delivery-mode
  validation, the `suspectData` and `citesLaw` sniffers, check 7d collision detection).
  These are referenced from the delivery-key invariants because the census exists to
  protect them, but they belong to WF4's own harness and were not in scope here. No
  fixtures invented.
- **`APR-…` / `MAT-…` ids from the supersede audit.** Sanitised to synthetic values of
  identical format and length. None of that scenario's assertions depend on the id values
  themselves, so no `needs_hash_regen` was required. Where a fingerprint *is* load-bearing
  (the three ingress replay scenarios), `"needs_hash_regen": true` is set and the exact
  derivation is spelled out in `expect.ingress_fingerprint_spec` — the fixtures
  intentionally do not hard-code a digest, so a change to the hash function fails loudly.

## Overlap with another group

`wf5-reply-*.json` and `wf5-testonly-*.json` in this directory were written by a parallel
agent from different source workflows. Several cover the same production units as mine
(`Build Reply Context` replay resolution; the digest's test-matter predicate). They are
left untouched. Before wiring the harness, de-duplicate deliberately: prefer whichever set
names its source QA workflow for the behaviour actually under test, and keep both where
the fixtures differ in substance.
