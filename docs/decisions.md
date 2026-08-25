# Decision log

Every significant choice made while reconstructing this repo (2026-08-25), in the format
**decision / why / rejected / consequence**. If you are about to change one of these, read
the "rejected" line first: it is usually the thing you are about to propose.

---

## (a) Scrubbed JSON exports are the canonical form, not the workflow-as-code SDK

**Decision.** `exports/wf{1,2,3,4,5,9}.json` — the n8n export, run through
`.tooling/scrub.py` in place — is what this repo treats as the workflows. Everything else
(`workflows/*.md`, `harness/units/`) is derived from it or describes it.

**Why.** The export is what n8n actually holds. It round-trips: you can diff it against a
fresh export and see exactly what drifted, node id by node id, including the fields nobody
writes by hand — `versionId`, `activeVersionId`, cached column schemas, webhook ids, retry
settings. Those fields are where the interesting facts live: two of the six workflows (WF5 and WF9)
have a draft ahead of the published version, and several Sheets nodes carry a stale cached
header. A representation that pretty-printed the graph would have thrown all of that away.

**Rejected.** The n8n workflow-as-code SDK. It is the better authoring format, but this
system was not authored in it — it was built in the UI over five days by an AI builder, and
102 of WF4's nodes exist as JSON. Re-expressing them in the SDK would have meant a
translation nobody could verify against production, and the first translation error would
have been invisible: the repo would have quietly stopped describing the live system.

**Consequence.** The exports are large (370 KB for WF4) and diffs are noisy. That is the
price of losslessness. It also means re-export → re-scrub → leak-check is a mandatory
ritual, because an unscrubbed re-export carries real ids straight into the tree.

---

## (b) Code nodes are extracted into offline units with a shim, not tested by executing workflows in n8n

**Decision.** `.tooling/extract-units.py` lifts every `n8n-nodes-base.code` node into a
standalone CommonJS module — 59 of them — with the `jsCode` byte-identical between
`BEGIN/END VERBATIM` markers. `harness/n8n-shim.js` fakes `$input`, `$('Node')`, `$now`,
`$json` and `this.helpers`, and `harness/run.js` runs them against JSON scenarios.

**Why.** Executing the real workflows to test them means live credentials, the live
register, and a live Telegram bot and Gmail account. There is no test double for the
production spreadsheet, and the whole risk model of this system is "a wrong send is real
correspondence about a real dispute". The extraction also has a second effect that matters
more than speed: the logic becomes *readable*. Four of the seven open safety issues in
`AGENTS.md` §6 were found by reading extracted units, not by running anything.

**Rejected.** (1) Executing the workflows in n8n against production — the three lines you
do not cross. (2) A staging n8n project with its own credentials and its own spreadsheet —
not rejected on merit, it is step 2 of `docs/roadmap.md`; it just did not exist yet, and it
does not replace the offline harness, it complements it. (3) Rewriting the node logic into
"proper" testable functions — that would test the rewrite, not production.

**Consequence.** Only Code nodes are covered. Set-node expressions, IF conditions, Sheets
operations, Gmail sends and sub-workflow dispatch are not — which is exactly why 19
scenarios are `integration` and 9 are `invariant`, and why `harness/invariants.md` exists to
say out loud what the harness cannot see. The `VERBATIM` invariant is load-bearing: hand-edit
a unit and the repo starts lying about production, so the extractor is the only writer.

---

## (c) The scrub map's keys are committed, even though they are the real literals

**Decision.** `.tooling/scrub-map.json` is committed with the real spreadsheet ids, Drive
folder id, owner Telegram chat id, six n8n credential ids, real matter/action ids, a party
name and three real email addresses as its **keys**. `leak-check.sh` excludes that one file
by name so the gate does not fire on it.

**Why.** The scrub has to be re-runnable and auditable. Every re-export must be scrubbed
with the *same* map or the tree becomes inconsistent, and a reviewer must be able to check
that a placeholder maps to what it claims — including that hashed values were replaced with
same-length substitutes (WF4's delivery key FNV-1a's the recipient address, so a
length-changing swap would have silently invalidated five oracles). A map with only the
replacement side is a map you cannot verify and cannot re-apply.

**Rejected.** (1) Keeping the map out of the repo entirely — then the scrub is not
reproducible and the next agent regenerates a different one. (2) Hashing the keys — you
cannot do a substring replacement against a hash. (3) Splitting into a committed
"replacements" file and an ignored "literals" file — same problem as (1), with extra
machinery and an invitation to commit the wrong half.

**Consequence.** **This repo is private and must never be pushed to a public remote.** That
is now stated in `AGENTS.md` §1.2 and in `.gitignore`. Two earlier documents claimed the
opposite ("the map holds only placeholder values, never the real literals") — both were
factually wrong and were corrected on 2026-08-25. Diffs and individual scrubbed files are
safe to share; the tree is not.

---

## (d) The two failing scenarios were left failing

**Decision.** `wf4-guard-conflicted-action-approval-route` and
`wf4-guard-conflicted-matter-draft-route` fail, `node harness/run.js` exits 1, and that is
the committed baseline.

**Why.** The failure is real. WF4's `Integrity Guard` accumulates conflicts into one array
and headlines `conflicts[0]` — whichever class was *pushed* first, not the most severe. On a
register where every duplicated `action_id` also shares its `idempotency_key`, the owner is
told `DUPLICATE_IDEMPOTENCY_KEY` ("two writes share a key") when the true condition is
`DUPLICATE_ACTION_ID_FIELD_MISMATCH` ("two rows under one action id disagree about recipient
and channel") — the condition the node was written to catch. The binding was verified, the
`expect` was verified against the source QA workflow, and neither is at fault. Full write-up
in `harness/FINDINGS.md` §1.

**Rejected.** (1) Relaxing the assertion to accept either code — that is a lie the next
agent trusts. (2) Fixing the unit here — units are generated from the export; a fix must go
into the n8n draft and come back through re-export, and it needs the owner's eyes because it
changes what a halt notice says. (3) Marking the two scenarios `skip` — a skip is invisible;
a red test is a standing instruction.

**Consequence.** Green is not the success condition of this repo; **75/2/60** is. Any
change that moves those numbers has to explain itself. The cost is that a naive CI hook
would consider the repo broken — so the baseline is written into `AGENTS.md`, `README.md`
and here.

---

## (e) `exports/` is committed rather than gitignored

**Decision.** The scrubbed exports are in git. The directory used to be `.raw/` and used to
be ignored, precisely because it held unscrubbed exports; it was renamed and scrubbed in
place, and `.raw/`, `exports-unscrubbed/`, `*.unscrubbed.json` remain ignored as the staging
area for anything not yet through the scrubber.

**Why.** The exports *are* the record of the workflows. Ignoring them would leave the repo
describing a system it does not contain: the specs would be unverifiable prose and the
extractor would have no input. Diffability is the entire reason the repo exists — you see
what changed in production by diffing a fresh scrubbed export against the committed one.

**Rejected.** Ignoring `exports/` and keeping only the units and specs. That looked
attractive (smaller tree, less leak surface) and is wrong: the units are a projection of the
Code nodes only, and the specs are hand-written. Neither can reconstruct a Sheets column
mapping or a retry setting.

**Consequence.** The leak-check is not advice, it is the gate — a re-export committed
without scrubbing puts live ids in history, where they cannot be removed by a later commit.
Hence the ordering rule stated in `.gitignore` and `AGENTS.md` §3: re-export, scrub,
leak-check, *then* commit.

---

## (f) The runner is adapters and projections, with an `unconsumed expect key` guard

**Decision.** `harness/run.js` never compares a scenario's `expect` to a unit's output
directly. Each scenario names an adapter in `harness/adapters.js`; the adapter runs the unit
(sometimes more than once — guard→verify pipelines, determinism re-runs, cross-scenario key
comparisons) and returns, for **every** top-level key of `expect`, either a check
`{key, expected, actual, ok}` or an explicit `informational` marking. Any key the adapter
did not consume is turned into a synthetic **failing** check named
`UNCONSUMED expect key "…"`.

**Why.** The scenarios were mined from ~30 different QA workflows written at different times
by different hands. Their `expect` vocabulary is the QA workflow's, not the unit's:
`reaches: "Halt - Data Integrity Conflict"` names a *node on a canvas*; `proposed_basis`
describes a matcher that was shadow-evaluated and never deployed. A generic field-by-field
comparator would have forced every scenario to be rewritten into the unit's vocabulary — a
mass edit of the oracles, which is the one thing you must not do. The projection keeps the
QA assertion intact and puts the translation in one reviewable place.

The guard exists because the obvious failure mode of a projection layer is silent
omission: an adapter that simply does not mention a key produces a green scenario that
asserts less than it claims. Making omission *fail* is what stops the suite decaying into
theatre. It is the same instinct as `oracles.js` — an expectation must never be resolved by
asking the code under test — and as "an unresolved target is better than a wrong one": a
scenario bound to the wrong unit reports a green result about code that never ran, so
unbound scenarios carry `target: null` and a written reason instead.

**Rejected.** (1) Deep-equality against the unit's output — impossible across mixed
vocabularies. (2) Rewriting all 137 `expect` blocks into unit vocabulary — destroys the
provenance that makes a disagreement adjudicable. (3) Letting adapters ignore keys they do
not understand — the silent-omission failure above.

**Consequence.** Adding a scenario in a new family means writing an adapter, which is more
work than dropping in a JSON file; the `no adapter` skip bucket exists so that forgetting is
loud rather than invisible. **Known weakness:** the runner also auto-consumes a key when a
check's name merely *starts with* it (`run.js`, `c.key.indexOf(k) === 0`), so a check named
`send_key_basis` would satisfy an `expect.send_key`. That prefix rule should become exact
matching plus an explicit alias list.

---

## Smaller decisions, recorded because they will look arbitrary later

| decision | why | rejected | consequence |
|---|---|---|---|
| A fourth scenario kind, `schema`, was kept | three mining agents independently used it; a tab's column order is a fact about the spreadsheet's *structure*, not its contents | forcing them into `invariant` | 5 scenarios that nothing executes; their headers are held against `fixtures/sheet-schema.json` by review, not by code |
| The runner freezes the **global** `Date`, not just `$now` | three units read `new Date()` / `Date.now()` directly (`Build Daily Digest`, `Distil Sources`, `Finalise Plan`) | editing production code to take an injected clock | those units' own clock reads are pinned but not themselves under test; noted in `AGENTS.md` §5 |
| `oracles.js` uses FNV-1a's *multiply* form where the units use *shift-add* | same function by definition of the FNV prime, so agreement cross-checks the basis string, field order, salting and pad width rather than restating the loop | copying the JavaScript's output into `expect` — the original Python oracles were computed over a real address that has since been replaced, so copying would have turned five assertions into tautologies | expectations carry the sentinel `REGENERATE`, resolved at run time |
| 142 mined scenarios were consolidated to 137, not deduplicated aggressively | two independent instantiations of one rule over different registers are worth more than one | merging every mechanical near-duplicate | 5 merges, each recorded in `fixtures/scenarios/_consolidation.md` with the unique content carried into the survivor as a `MERGED from …` assertion |
| Five mis-transcribed expectations were corrected in place, each stamped `_correction_2026-08-25` | they were paraphrases or prose where the source workflow asserted a value | leaving them to fail (they would have failed for the wrong reason) | the machine-checkable half was already correct and is still asserted; nothing was weakened |

---

## (g) All six exports are pretty-printed with two-space indent, not stored as n8n returned them

**Decision.** `exports/*.json` are serialised with `indent=2` and a trailing newline. Three
of them (WF1, WF3, WF9) arrived minified onto a single line from a different agent and were
reformatted on 2026-08-25.

**Why.** "Diffable" is the whole claim this directory makes. A 46 KB single-line JSON file
has exactly one line, so every change to it is a whole-file diff and the repo silently stops
being able to answer "what drifted". Uniformity also matters more than fidelity to n8n's
exact bytes, because n8n's export formatting is not itself stable or meaningful.

**Rejected.** Keeping the raw bytes from the API. That would be the purer position if all
six had been raw — but three were already reformatted, so there was no raw baseline to
preserve, only an inconsistency to pick a side of.

**Consequence.** A re-export must be run through the same serialisation before it is
diffed, or the first diff is 100% noise. Reformatting does not touch `sha256OfJsCode`: those
digests are over the `jsCode` string, and re-running the extractor after this change
produced a byte-identical `harness/units/index.json`.

---

## (h) The leak check greps for a 6-character prefix of the sheet id, not the full literal

**Decision.** `leak-check.sh` now matches the first six characters of the real spreadsheet
id rather than the whole 44-character string, and `scrub-map.json` carries the hand-written
abbreviated form as a key of its own. Neither is quoted here, for the obvious reason.

**Why.** A WF1 sticky note wrote the id by hand as `<first six chars>...<mistyped tail>`.
The full-string map never matched it and the full-string grep never saw it, so it survived
the first scrub, in two committed files, while both gates reported clean. Six characters is
not a usable secret; a gate that can be evaded by an ellipsis is the actual problem.

**Rejected.** Only adding the exact abbreviated string. It fixes this instance and not the
class — the next hand-written abbreviation will be truncated somewhere else.

**Consequence.** A shorter pattern is more likely to false-positive on unrelated text. It
has not yet, and `leak-check.sh` excludes itself and `scrub-map.json` by name. It also now
fires on prose *about* the id, which is why this entry describes the literal instead of
showing it. The general lesson is recorded because it will recur: **a scrubber keyed on
exact literals cannot see prose that paraphrases them**, and sticky notes are prose.
