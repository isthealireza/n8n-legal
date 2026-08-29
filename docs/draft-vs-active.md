# Draft versus active — what this repo exports, and what production runs

Written 2026-08-25, after the trap described below bit us.

---

## 1. The trap

`mcp__n8n__get_workflow_details` returns the **draft**. It does not return the published
version. For a workflow whose draft is ahead of its published version, everything you read
out of that call — nodes, code, prompts, parameters — is **not what is running in
production**.

The signals are all in the same payload and are easy to skim past:

| field | meaning |
|---|---|
| `versionId` | the DRAFT you are being handed |
| `activeVersionId` | the version production is actually executing |
| `activeVersion.sameAsDraft` | `false` means the two differ; the published body is nested under `activeVersion` |

A **UI autosave silently creates a draft ahead of published.** Nobody has to press publish,
nobody gets a prompt, and the workflow keeps running the old code. Open a live workflow in
the n8n editor, nudge a field, walk away — `versionId` has moved, `activeVersionId` has not,
and the next agent to call `get_workflow_details` exports a version that has never run. In
the version history an autosave shows as `autosaved: true`, `name: null`, and an author
string with **no `(via MCP)` suffix** — a bare name means a human in the editor.

The n8n editor also **prunes parameters equal to their default** when it saves. An
MCP-written node that spells a default out explicitly will silently lose that key on the
first UI autosave. That is not a code change, but it looks exactly like one in a diff.

## 2. The naming convention in `exports/`

There is no longer a `wfN.json`. Every file states which side of the line it is on:

```
exports/wfN.active.json    the PUBLISHED version. What production runs. Always present.
exports/wfN.draft.json     an UNPUBLISHED draft that is AHEAD of active. Present only
                           when the two differ.
```

**The absence of a `wfN.draft.json` is itself the statement that draft == active.** Each
file also carries an `_export` block naming its `kind`, where it came from, and when it was
captured.

`.tooling/extract-units.py` globs `wf*.active.json` only. **`harness/units/` is extracted
from active, never from draft.**

### Why active, and not draft

The repo's central claim is that `node harness/run.js` tells you the truth about the live
system in seconds. A suite extracted from drafts breaks that claim in the worst possible
direction: it goes green on code that has never executed, while the code that is executing
against a real practitioner's real matters is untested. "The tests pass" would then mean
"the tests pass on something nobody is running."

The counter-argument — that you want to test the change you are about to ship — is real but
is served differently: extract the draft into a scratch tree and diff it, or publish it and
re-extract. What must never happen is that the default, unqualified `node harness/run.js`
reports on anything other than production. Testing a draft is an opt-in act; testing
production is the floor.

A working consequence, which is the point: switching the extractor from draft to active
turned the baseline from **75/2/60 into 74/3/60**. One assertion that had been green was
green only because it was being run against unpublished code (§4).

## 3. State on 2026-08-25T02:15Z

| wf | id | draft (`versionId`) | active (`activeVersionId`) | diverged | files |
|---|---|---|---|---|---|
| wf1 | `xUcAXTgocHPsHy5Y` | `9cc644ec` | `b1c425bf` | **yes** | `wf1.active.json`, `wf1.draft.json` |
| wf2 | `OaVCEsrt2qpo28rB` | `61e6ffee` | `61e6ffee` | no | `wf2.active.json` |
| wf3 | `1rhaSTTviUBanJIy` | `644bbdb3` | `644bbdb3` | no | `wf3.active.json` |
| wf4 | `zKr24IThF30e6jXw` | `8f6b3704` | `8f6b3704` | no | `wf4.active.json` |
| wf5 | `zDLoMgW42jUm25Q4` | `811b746c` | `983da561` | **yes** | `wf5.active.json`, `wf5.draft.json` |
| wf9 | `JfaCOxRq0FjZ5JWb` | `a5b10619` | `a5b10619` | no (**closed by a publish**) | `wf9.active.json` |

### wf9 — the divergence closed itself while we were not looking

At capture time wf9's active was `df3579b2` and its draft `a5b10619`. By 02:12Z the active
was `a5b10619`: **someone published wf9 between the two reads.** Publishing writes no new
history entry and does not move `updatedAt`, so the only trace is `activeVersionId` moving.
The published change (`a5b10619`) is sticky-note text only — `Build Error Record`'s `jsCode`
is byte-identical across `df3579b2` and `a5b10619`, so no unit and no harness result moved.
It is recorded here because *nothing else recorded it*.

### wf1 — an unreviewed UI autosave sitting in front of production

`9cc644ec`, autosaved by **Owner** (bare name — the editor, not MCP) at
2026-08-25T01:19:51Z. Two node changes, no nodes or connections added or removed:

| node | change |
|---|---|
| `DeepSeek - Router` | `options.maxTokens` 64000 → 32768 |
| `Ack Button` | `operation: "answerQuery"` **deleted** |

Both are assessed in §5. Production is unaffected **for now** — active is still `b1c425bf`
— but this draft is what the next person who presses Publish will ship, and nobody reviewed
it.

## 4. wf5 — draft versus active, node by node

One node differs. Nothing else: no node added, no node removed, no connection changed.

### `Build Daily Digest` (Code node `00a4aea9`)

Active is `983da561` (*"Digest: conflict notice sections, EXHAUSTED undroppable"*,
2026-08-22). Draft is `811b746c` (*"Digest: name omitted sections, reserve budget for the
notice"*, 2026-08-23). The draft is ahead in three ways:

1. **Omissions are named.** Active prints a bare
   `[N further section(s) omitted to fit one message.]`. Draft prints an
   `OMITTED TO FIT ONE MESSAGE (N)` block listing each dropped section's title, priority,
   row count and reason.
2. **The omission block is inside the budget measurement.** Active measures the message,
   stops at `CEILING`, *then* appends the omission notice — so a truncated message always
   exceeds 3600 by the length of that notice (3632 observed). Draft renders the notice as
   part of every measurement pass.
3. **New diagnostics**, none of which exist in production: `sections_built`,
   `sections_kept_titles`, `sections_omitted_detail`, `sections_omitted_titles`,
   `budget_ceiling`, `budget_holds`.

The priority-0 guarantee (`DATA_INTEGRITY_CONFLICT`, `TEST AND QA MATTERS`,
`CONFLICT NOTICES NEVER REPORTED` are never dropped) is identical in both.

**The draft also strips the incident narrative.** Confirmed: the active node opens with the
2026-08-22 report incident in full — *"Open actions: 27" and then listed 13 rows*, the
two-dimensions explanation, the "WHAT IT WILL NOT DO" paragraph — and carries a long
justification on `isTestMatter` naming the four adversarial live titles it was tightened
against (`Employment contract - QA Engineer, Perth` and friends), plus the explicit note
that `facts.dry_run` is deliberately not a signal. The draft deletes all of it. Roughly 60
lines of incident record are gone, along with the unused `matterTitle` helper. That is a
direct violation of AGENTS.md §7, and the draft is the version someone will eventually
publish.

**Worse than a deletion, the draft replaces one of those comments with a false one.** The
draft's `isTestMatter` header now reads:

> `facts.test_data_only / matter_flagged_test_only / is_test are the DETERMINISTIC signals stamped at ingress`

Nothing stamps them. That is AGENTS.md §6.7 verbatim — `resolveTestFlag` does not exist —
and the active node does not make the claim. The draft would put a comment in production
asserting a safety property that the system does not have.

### Is any harness unit testing code that is not in production?

**It was. It is not any more.** Before this change, `harness/units/wf5/build-daily-digest.js`
was extracted from the draft, so every WF5 digest scenario was asserting against the
unpublished `811b746c`. Nine WF5 units existed; one of them — this node — was not production
code. The other eight WF5 units, and every wf1/wf2/wf3/wf4/wf9 unit, were already identical
in draft and active, so they were unaffected.

After re-extracting from `wf5.active.json`, `sha256OfJsCode` for
`wf5/build-daily-digest.js` changed and one scenario turned red:

```
FAIL  wf5-digest-budget-pressure    harness/units/wf5/build-daily-digest.js
        x rendered message is within the 3600-char ceiling
            expected: true
            actual:   undefined
```

Be precise about what this failure is and is not:

- **It is not a reproduction of the 3632-character overshoot.** At this fixture's size the
  active node renders 3586 characters — inside the ceiling. The overshoot is real (the
  active code genuinely appends the notice after measuring) but this fixture does not reach
  the size that exposes it.
- **It is a scenario written against draft-only behaviour.** `budget_holds` is a diagnostic
  that only `811b746c` emits; against production it is `undefined`, and
  `mk(..., true, undefined)` fails. The scenario was mined from a QA workflow that was
  itself built against the draft.
- **Two sibling assertions in the same scenario are now silently vacuous.** *"nothing at
  priority 0 was dropped"* reads `(d.sections_omitted_detail || [])` — `undefined` against
  production, so `.every()` passes over an empty array and proves nothing. And the
  scenario's `assertions` list claims the reply prints
  `OMITTED TO FIT ONE MESSAGE (<n>)` and names each omitted section; the adapter never
  checks either string, and against production neither string exists.

Per AGENTS.md the assertion has **not** been weakened and the scenario has **not** been
retargeted. It is now a true statement: this scenario tests a property production does not
have. See `harness/FINDINGS.md` §3.

## 5. The two wf1 autosave changes, assessed

### `Ack Button` lost `operation: "answerQuery"` — HARMLESS

`answerQuery` **is** the default operation for `resource: "callback"` on
`n8n-nodes-base.telegram` typeVersion 1.2, so omitting the key resolves to the same
operation and the inline-button acknowledgement still fires.

Evidence, not assumption:

- `get_node_types` for `n8n-nodes-base.telegram` lists the callback resource's operations as
  `answer_inline_query, answer_query` and resolves `resource=callback, operation=answerQuery`
  to a full parameter schema whose required field is `queryId` — which the node still sets.
- `validate_node_config` on the post-autosave shape
  (`resource: callback`, `queryId`, `additionalFields.cache_time`, **no** `operation`)
  returns `valid: true`.
- The same validator, given a node with neither `resource` nor `operation`, demands `chatId`
  and `text` — i.e. it resolves missing discriminators to the node's declared defaults
  (`message`/`sendMessage`). Defaults are what fills the gap, not "nothing".
- The autosave's own behaviour is the clincher. The n8n editor writes back only parameters
  that differ from their default. It **kept** `resource: "callback"` (default is `message`)
  and **dropped** `operation` — which it can only do if `answerQuery` is that branch's
  default. `additionalFields.cache_time: 0` survived because collection members are retained
  once added, default value or not.

**Verdict: no regression.** The button acknowledgement is intact. The delta is cosmetic
normalisation by the editor, not an edit. It should still not be published unreviewed,
because it travels in the same draft as the change below.

### `DeepSeek - Router` maxTokens 64000 → 32768 — HARMLESS FOR TRUNCATION

`maxTokens` caps the **completion**, not the prompt. What this model has to emit is the
`Intent Schema` structured output: six fields — an enum of ten values, a number, two short
strings, a boolean, and a one-sentence summary. The whole schema is 1085 characters of
node parameter; a conforming response is on the order of 100–200 tokens. 32768 leaves two
orders of magnitude of headroom. The `Classify Intent` prompt is ~3.4 KB and does not
consume the completion budget.

**Verdict: cannot truncate the router's structured output.** Neither 64000 nor 32768 is
anywhere near binding.

One thing the owner should check anyway, which is not a truncation issue: 64000 is above
the per-request output cap of every DeepSeek chat model this node has ever pointed at, and
a `max_tokens` above the model's cap is rejected by the API rather than clamped. The
configured model here is `deepseek-v4-flash`. If 64000 was being rejected outright, this
"harmless" edit may in fact be someone fixing a live 400 in the editor — in which case it is
a fix that is sitting unpublished. Worth one execution log to settle. Either way it is not
a truncation risk.

## 6. What to do when you find a divergence

1. **Never publish, never restore.** AGENTS.md §1.1. Recording the divergence is the job.
2. Capture both sides under the convention above and re-run
   `python3 .tooling/scrub.py && ./.tooling/leak-check.sh`.
3. Re-run `python3 .tooling/extract-units.py`. If a unit's `sha256OfJsCode` moves, the
   harness was testing the wrong body — say so out loud, and say which scenarios moved.
4. Diff the two and write down what the difference is and who authored it. Check the author
   string for `(via MCP)`.
5. Hand the owner the diff. They publish.

## 7. wf4 moved — correction to the §3 table (2026-08-29)

§3 is a snapshot of 2026-08-25T02:15Z and it says wf4 is not diverged, draft and active both
`8f6b3704`. **Both halves of that row are now stale.** Read today, live, read-only:

| wf | id | draft (`versionId`) | active (`activeVersionId`) | diverged | files |
|---|---|---|---|---|---|
| wf4 | `zKr24IThF30e6jXw` | `8107c96f` (181 nodes) | `902130f4` (102 nodes) | **yes** | `wf4.active.json` |

Two moves happened between the two reads:

1. **`8f6b3704` was superseded by a publish.** `902130f4` — *"D-CHANNEL-01 + D-STATUS-01:
   fail-closed channel guard and status fingerprint"*, `Owner (via MCP)`,
   2026-08-25T07:36:57Z — became active. `exports/wf4.active.json` was re-captured from it
   on 2026-08-27 and today's re-read confirms the capture is exact (0 residual diffs after
   the scrub map, 102/102 nodes, connections byte-identical).
2. **A new draft went in front of it.** `8107c96f` — *"SPEC-2 Rev B: verify inherited safety
   contract"*, `Owner (via MCP)`, 2026-08-27T02:33:23Z — adds 79 nodes and modifies `Config`
   and `Approval Gate`.

**No `wf4.draft.json` has been captured for `8107c96f`.** Per §2 the absence of a draft file
is the claim that draft == active, and for wf4 that claim is now false. Capturing it is its
own change (the draft is a 181-node body and touches the Approval Gate, so it needs the
owner's eyes, not an opportunistic export inside another task). Until it is captured, this
section is the record that the divergence exists.

Both entries are `(via MCP)` with `autosaved: false`, so neither is the UI-autosave trap of
§1. Full account — including the `Approval Gate` kill-switch edit that the draft's own
version description calls "unchanged" — is in `docs/wf4-live-inspection-2026-08-29.md`.

## 8. wf4 moved again — the draft named in §7 no longer exists (2026-08-29, later)

§7 was written before the owner-gated two-node integrity port. Read live, read-only, during
Fast Lane run `run_bfa3412dc1f8`:

| wf | id | draft (`versionId`) | active (`activeVersionId`) | `sameAsDraft` | diverged | files |
|---|---|---|---|---|---|---|
| wf4 | `zKr24IThF30e6jXw` | `470120af` (181 nodes) | `902130f4` (102 nodes) | `false` | **yes** | `wf4.active.json` |

`8107c96f` — the draft §7 names — **is gone from the version history**. The port
(`docs/wf4-live-inspection-2026-08-29.md` §5) replaced it with `470120af`, and the history
now holds two entries, not three. Two consequences worth writing down:

1. `get_workflow_versions_diff` can no longer be run against `8107c96f`. The whole SPEC-2
   Rev B delta must be read as `902130f4 -> 470120af`, which carries SPEC-2 Rev B **and** the
   two integrity fixes in one diff.
2. `restore_workflow_version` to `8107c96f` — the rollback named in the gate question that
   authorised the port — is **no longer available**. Restoring the draft to its pre-port state
   would now mean writing the published bodies of `Integrity Guard` and
   `Build Integrity Halt Notice` back into it, which is itself a protected action.

`exports/wf4.active.json` was re-verified against a fresh `get_workflow_version(902130f4)` on
2026-08-29: 102/102 nodes, 0 differing after the scrub map, connections byte-identical. Still
**no `wf4.draft.json`** for either draft id — and that gap is now also why WF4's drafted
`Approval Gate` kill switch has no harness coverage. Full review of the 181-node draft:
`docs/wf4-spec2-revb-review-2026-08-29.md`.
