# FINDINGS — production behaviour that does not match what the QA suite asserts

Written 2026-08-25 while wiring `harness/run.js`. Everything here is category **(c)**: the
harness binding was checked and is correct, the scenario's `expect` was checked against its
source QA workflow and is not a transcription slip, and the extracted production code
genuinely does something else. **Neither side was changed.**

Reproduce with `node harness/run.js`. Two scenarios fail; both fail on the same defect.

---

## 1. Integrity Guard headlines the wrong conflict code (push order, not severity)

**Unit** `harness/units/wf4/integrity-guard.js` (WF4 `Integrity Guard`, node
`7bee0e49-ab5e-471d-9a88-4da7d736e459`, sha256 `039f3be3…`)

**Scenarios** `wf4-guard-conflicted-action-approval-route` (case C2),
`wf4-guard-conflicted-matter-draft-route` (case C1) — both mined from
`hTz7VbLHENx8ZB1N`, *QA - WF4 Integrity Guard Runtime*, which copied this node VERBATIM.

**Expected vs actual**

| scenario | key | expected | actual |
|---|---|---|---|
| `…-action-approval-route` | `integrity_code` | `DUPLICATE_ACTION_ID_FIELD_MISMATCH` | `DUPLICATE_IDEMPOTENCY_KEY` |
| `…-matter-draft-route` | `integrity_code` | `DUPLICATE_ACTION_ID_FIELD_MISMATCH` | `DUPLICATE_IDEMPOTENCY_KEY` |
| `…-matter-draft-route` | `conflict_count` | 6 | 12 |

**Why this is a real defect.** The node accumulates every conflict into one array and then
reports the first of them as the headline:

```js
if (conflicts.length) {
  const worst = conflicts[0];
  return halt(worst.code, '…', conflicts);
}
```

The pushes happen in a fixed order — blank `action_id`, blank `idempotency_key`,
duplicate `idempotency_key`, then per-`action_id` duplicates and field mismatches. On the
real `MAT-20260101-002` snapshot every duplicated action id also shares its
`idempotency_key`, so both `DUPLICATE_IDEMPOTENCY_KEY` and
`DUPLICATE_ACTION_ID_FIELD_MISMATCH` fire and the variable named `worst` holds whichever
was pushed first. It is an artefact of statement order, not of severity.

That matters because `integrity_code` is the value carried into `Build Integrity Halt
Notice` and shown to the owner. The two codes describe very different situations:
`DUPLICATE_IDEMPOTENCY_KEY` says "two writes share a key"; `DUPLICATE_ACTION_ID_FIELD_MISMATCH`
says "two rows under one action id disagree about **recipient and channel**" — which is the
condition that could send a `CONTACT_INSURER` letter to a car park manager, and is the
reason this node exists. The owner is told the milder of the two.

`conflict_count` 12 against 6 is the same fact seen from the other side: every duplicated
id is reported twice, once per class. Nothing is lost (`integrity_detail` carries the full
list) but the count in the notice is double the number of ambiguous actions.

**What a fix would look like** (not applied): rank `conflicts` by a declared severity order
before taking the headline, with `DUPLICATE_ACTION_ID_FIELD_MISMATCH` above
`DUPLICATE_IDEMPOTENCY_KEY` above `DUPLICATE_ACTION_ID`, and count distinct in-scope
`action_id`s rather than conflict entries.

**One caveat, stated because it changes who should fix it.** The QA workflow copied the
guard from WF4 draft `5a2a208f`; the unit here is extracted from `exports/wf4.json`. If the
node has been edited since the copy was taken, the expectation may be describing an older
push order rather than a stated intent. Either way the behaviour *today* is push-order
dependent, which Group A reached independently by reading the code
(`_groupA-notes.md`, "Things that look like unfixed production bugs", item 4). Confirm the
node version before choosing between "restore the old order" and "rank properly".

---

## 2. The deterministic ingress test-flag predicate does not exist

**Scenarios** the eight `wf5-testonly-*` files (mined from `RtNgxMxS10ZOJPFG`,
*QA - WF5 Conflict Notice Digest Sections*, "Fix 1, deterministic TEST ONLY isolation").
They are recorded as `target: null` rather than failing, because half of each one cannot be
bound to anything.

Each asserts `resolveTestFlag(ingress) -> { test_data_only, basis }`, an ingress-stage
predicate that reads only the raw inbound text and an explicit internal flag, and
deliberately refuses to fire on "emissions test", "test period", "Sandbox Pty Ltd" or
"Test Corp".

`grep -rn 'resolveTestFlag' exports/*.json harness/units/` returns nothing. Searching for the
field it is supposed to stamp:

- `exports/wf2.json` → `Finalise Plan` mentions `test_data_only` only in a `CONTROL` set, i.e.
  as a key excluded from the fact vocabulary. It never computes or writes it.
- `exports/wf5.json` → `Build Daily Digest` **reads** `facts.test_data_only` inside
  `isTestMatter`, and its own comment calls it one of "the DETERMINISTIC signals stamped at
  ingress".

Nothing in WF1–WF5 or WF9 stamps it. The digest's test/live separation therefore rests on
the model-generated fallbacks the fix was written to stop relying on — the matter title and
the risk flags — which is precisely the 2026-08-23 incident the QA workflow records: a
synthetic matter was isolated only because the model happened to emit a `TEST_ONLY` risk
flag, and a matter titled `Parked vehicle damage - Perth car park (hit and run) - 17 Aug
2026` carried no marker at all.

The `isTestMatter` half of these scenarios *is* covered, by
`wf5-digest-is-test-matter-predicate` (13 cases, passing).

---

## Two further defects, not asserted by any scenario, confirmed here by execution

Both were flagged by code reading in `_groupA-notes.md` and are carried as KNOWN GAP prose
in `wf4-verify-channel-changed-after-the-gate`. They are recorded here because the harness
can now demonstrate them rather than argue them. Neither is a failing scenario: no scenario
asserts the correct behaviour, so nothing is red.

### 3. `Verify Selected Row` treats a gate channel of `NONE` as a free pass

`harness/units/wf4/verify-selected-row.js`:

```js
if (U(gate.channel) !== U(row.channel) && U(gate.channel) !== 'NONE') { … CHANNEL_MISMATCH … }
```

Probe: guard passes on a single clean row with `channel: GMAIL`; the gate then presents
`channel: 'NONE'`. Result: `integrity_ok: true`, no `integrity_code`. The branch continues
to the writers and the Gmail nodes. The scenario suite injects `MANUAL` (which is caught)
and never injects `NONE`. Given that the node's stated job is to check "the two fields that
decide where an external message would go", a channel the gate could not resolve should
fail closed, not pass.

### 4. The row fingerprint omits `status`, so a cancelled action still verifies

`FP_FIELDS` is `action_id, matter_id, action_type, priority, depends_on_json, recipient,
channel, requires_approval, idempotency_key, created_at` — `status` and `updated_at` are
not in the basis.

Probe: guard fingerprints a row at `status: AWAITING_APPROVAL`; the register row then flips
to `status: CANCELLED` with a new `updated_at`. Result: `integrity_ok: true`, no
`FINGERPRINT_CHANGED`. The node's comment says it exists so that "if the register changes
between the two reads" the branch stops. For a status change — including a concurrent run
marking the row `SENT`, or a human cancelling it — it does not.

Reproduction for both, against the extracted units:

```js
const { makeContext } = require('./harness/n8n-shim');
const guard  = require('./harness/units/wf4/integrity-guard.js');
const verify = require('./harness/units/wf4/verify-selected-row.js');
const row = { action_id:'ACT-1', matter_id:'MAT-1', action_type:'CONTACT_INSURER',
  status:'AWAITING_APPROVAL', priority:'HIGH', depends_on_json:'[]',
  recipient:'claims@x.example', channel:'GMAIL', requires_approval:'TRUE',
  idempotency_key:'K1', created_at:'2026-08-21T00:00:00Z', updated_at:'2026-08-21T00:00:00Z' };
const now = '2026-08-23T06:00:00.000Z';
(async () => {
  const g = (await guard.run(makeContext({ items:[{}], now, nodeOutputs:{
    Config:[{ matter_id:'MAT-1', route_group:'APPROVAL', approval_id:'APR-1' }],
    'Load Actions':[row],
    'Load Approvals':[{ approval_id:'APR-1', matter_id:'MAT-1', action_id:'ACT-1',
                        draft_id:'D1', status:'PENDING' }] } })))[0].json;

  // 3. gate channel NONE against a row that says GMAIL
  console.log((await verify.run(makeContext({ now,
    items:[{ gate:'SEND', action_id:'ACT-1', recipient:row.recipient, channel:'NONE' }],
    nodeOutputs:{ 'Integrity Guard':[g], 'Load Actions':[row] } })))[0].json.integrity_ok);

  // 4. row status flipped to CANCELLED after the guard fingerprinted it
  const cancelled = { ...row, status:'CANCELLED', updated_at:'2026-08-22T00:00:00Z' };
  console.log((await verify.run(makeContext({ now,
    items:[{ gate:'SEND', action_id:'ACT-1', recipient:row.recipient, channel:row.channel }],
    nodeOutputs:{ 'Integrity Guard':[g], 'Load Actions':[cancelled] } })))[0].json.integrity_ok);
})();   // prints: true, true
```
