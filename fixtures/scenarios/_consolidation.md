# Scenario consolidation — 2026-08-25

Three agents mined nine retired QA workflows each, in parallel, and the three sets overlapped.
This file records every merge and deletion. **142 files before, 137 after; 5 clusters merged.**

Method:

1. Every scenario was read and indexed by `(source_qa_workflow, unit, input, expect)`.
2. A mechanical near-duplicate pass compared whitespace- and case-normalised `input` and
   `expect` across all 142 files. Its hits were then reviewed by hand — most were false
   positives (the nine `wf4-live-fetch-*` integration scenarios share an `expect` shape;
   the nine `invariant` scenarios all share an empty `input`).
3. A cluster was merged **only** where two scenarios test the same property over
   substantively the same input — in practice, where the same QA case (same
   `provider_message_id`, same thread, same body) had been mined twice from two different
   harnesses. Similar-but-different inputs were kept apart.

Nothing was deleted without its unique content being carried into the survivor as an
assertion prefixed `MERGED from …`, and the survivor carries a `merged_from` array.

---

## Merged clusters

### 1. `wf5-reply-dry-run-is-not-correspondence` → `wf5-replypolicy-dry-run-is-not-correspondence`

Explicitly flagged in `_groupA-notes.md` as a filename collision between
`VelAeCU71KHELUJP` (QA - WF5 Reply Matching Verification) and `BAKIml11QKedtH9d`
(QA - WF5 Reply Policy v2). Group A judged them "not duplicates". On inspection they are
the same case: the same event (`MSG-IN-7`, `THREAD-BBB`, `HR <hr@…>`, body `"Replying."`,
subject tagging the dry-run matter) against a register whose only outbound row for that
matter is `OUTBOUND_DRY_RUN`. The two files differ only in sanitisation and in which output
vocabulary they name.

Kept the reply-policy version: it carries the full three-matter stateful register, the
accumulated INBOUND rows, and the resolver's own `decision`/`basis`/`write_*` vocabulary.
Carried across: the `unverified_kind: NO_CORRESPONDENCE` adapter-field naming, the
"Events row only" state-change statement, and the recorded production gap about known
parties being seeded from `Actions.recipient`.

### 2. `wf5-reply-sender-not-a-party-refused` → `wf5-reply-sender-not-a-party`

Same message id (`MSG-IN-6`), same thread (`THREAD-AAA`), same body
(`"I am replying to this."`), same property: a sender the matter has never written to is
refused. The reply-policy version carries the register; the Vel version carries none at all.

### 3. `wf5-reply-tag-in-subject-matches-matter` → `wf5-reply-tag-and-registered-thread-agree`

Same message id (`MSG-IN-1`), same registered thread, same subject tag agreeing with the
thread, same ACCEPT. Carried across the adapter-field assertions
(`sender_verified` true, `unverified_kind` empty) and the named write path.

### 4. `wf5-reply-thread-beats-quoted-tag` → `wf5-reply-thread-mismatch-shared-counterparty`

Same message id (`MSG-IN-9`), same thread, same shape: the thread belongs to one matter and
the body tags a different matter shared with the same counterparty.

The Vel file's `expect` (`proposed_basis: THREAD`, `proposed_verified: true`) describes a
**proposed** thread-first matcher that was shadow-evaluated and never deployed, and its
`deployed_matcher_saw_tag` field describes the retired regex-first `Match Reply to Matter`.
Both halves are now historical: the deployed `Match Reply to Matter` no longer matches at
all ("Deliberately no matter_id, no action_id and no matched flag here"), and the resolver
in `Build Reply Context` refuses rather than choosing. Keeping the Vel `expect` as an oracle
would have asserted behaviour the code deliberately no longer has. It is preserved as
historical assertions on the survivor instead.

### 5. `wf5-duplicate-reply-produces-identical-keys` → `wf5-inbound-idempotency-key-stable-across-replay`

Same property (the two reply idempotency-key expressions are stable across a replay), same
matter and message id. The survivor (`4pok4hCJGh60NbM2`, QA - Inbound Key Stability) is
strictly richer: it carries both deliveries in full, with *differing* `communication_id` and
`received_at`, which is what actually proves the key ignores them.

---

## Clusters examined and deliberately NOT merged

| Cluster | Why kept apart |
|---|---|
| `wf5-ingress-replay-{identical-body,changed-body,fingerprint-not-recorded}` vs `wf5-reply-{identical-replay-is-already-recorded,replay-with-edited-body-is-conflict,prefingerprint-row-fails-closed}` | Same three replay outcomes, but over genuinely different registers: the ingress set uses the round-trip register with full 18-column Communications rows, the policy set uses the three-matter stateful register. Two independent instantiations of the same rule are worth more than one. |
| `wf5-ingress-thread-tag-mismatch` vs `wf5-reply-thread-mismatch-unknown-tag` | Different registers and different matter ids. The ingress one is marked `derived` (a mechanical variant of its own register) and additionally pins `event_type` / `severity`. |
| `wf5-ingress-sender-not-a-party` vs `wf5-reply-sender-not-a-party` | Different registers; the ingress one pins the audit-event vocabulary (`INBOUND_REPLY_SENDER_NOT_A_PARTY`, `WARNING`) that the policy one does not. |
| `wf5-digest-is-test-matter-predicate` (13 cases) vs the eight `wf5-testonly-*` files | Overlapping on `isTestMatter`, but each `wf5-testonly-*` file also pins `resolveTestFlag(ingress)` — a *different* predicate, at a different stage. See the note below. |
| `wf5-reply-identical-replay-is-already-recorded` vs `wf5-reply-whitespace-reflow-is-not-a-conflict` | Flagged SAME-INPUT by the mechanical pass only because that pass collapses whitespace — which is exactly the variable under test. The bodies differ (`"We have received your letter."` vs `"We have received   your\nletter."`). |
| `wf5-reply-resolver-is-deterministic` vs `wf5-reply-tag-and-registered-thread-agree` | Identical input, different property: one asserts the ACCEPT outcome, the other asserts that two runs over the same base register produce byte-identical output. |
| `wf4-delivery-key-first-send` vs `wf4-delivery-key-dry-run-separated-from-send` | Identical input, different property: the key basis and value vs the dry/send id separation over one shared hash. |
| The nine `wf4-live-fetch-*` files | Identical `expect` *shape*, different URLs and different live pages. All `integration`. |
| The nine `invariant` files | All carry an empty `input` by construction. |

## Note on `resolveTestFlag`

The eight `wf5-testonly-*` scenarios assert a WF5 **ingress** predicate
`resolveTestFlag(ingress) -> { test_data_only, basis }`. A grep across all six workflow
exports (`exports/wf{1,2,3,4,5,9}.active.json`) and all 59 extracted units finds no such function.
The only test-matter predicate in the estate is `isTestMatter` in WF5 `Build Daily Digest`,
which reads a *persisted* `facts_json.test_data_only` — nothing in the estate computes and
stamps that value at ingress. These scenarios are therefore left with `target: null` rather
than being half-bound to the digest, and the gap is recorded in `harness/FINDINGS.md`.

---

## Category (b) corrections made while wiring the runner

Five expectations were mis-transcribed from their source QA workflow and were corrected in
place. Each corrected file carries a `_correction_2026-08-25` key inside `expect` recording
exactly what changed and why. No assertion was weakened to make a test pass: in every case
the machine-checkable half (`decision`, `basis`, `event_id`, `event_type`, `severity`,
`write_*`) was already correct and is still asserted.

| scenario | correction |
|---|---|
| `wf5-ingress-first-delivery-accept` | `expect.ingress_fingerprint` was the prose `"computed, not asserted literally"`. Replaced by the sentinel `REGENERATE`, which the runner resolves through the independent `ingressFingerprint` in `harness/oracles.js`. The assertion is now real rather than decorative. |
| `wf5-ingress-replay-identical-body` | `expect.stored_fingerprint` was the prose `"equals the incoming ingress_fingerprint"` → `REGENERATE`. Its register row also carried the literal placeholder `<computed by ingressFingerprint(EV_FIRST); recompute, do not hard-code>`, which the normaliser now resolves; until it did, the scenario tested `IDEMPOTENCY_CONFLICT` on a garbage fingerprint instead of `ALREADY_RECORDED` on a real one. |
| `wf5-ingress-replay-identical-body` | `expect.reason` was the paraphrase `"Already recorded, raw message identical. Ignored."`; the node emits `"Message <id> is already recorded on <matter> and the raw message is identical. Ignored."` Demoted to `reason_shape` (informational). |
| `wf5-ingress-replay-fingerprint-not-recorded` | `expect.reason` was the paraphrase `"No stored fingerprint."` Demoted to `reason_shape`. |
| `wf5-ingress-thread-tag-mismatch` | `expect.reason` was the paraphrase `"Thread and tag disagree."` Demoted to `reason_shape`. |

The three `reason` paraphrases were written by the mining agent as summaries; the source
workflow asserted on `decision` / `basis`, not on the sentence. Two other scenarios in the
same family (`wf5-ingress-replay-changed-body`, `wf5-ingress-sender-not-a-party`) already
used `reason_shape` for the same purpose, which is what made the slip visible.
