# Group A — mining notes

Nine retired one-shot QA workflows, read-only, converted into 84 portable scenario files
in this directory. Every workflow was read with `get_workflow_details` at `detailLevel: full`;
nothing was executed and nothing was written back to n8n.

## Sanitisation applied across all 84 files

> **Read this table with care — it has since been scrubbed itself.**
> It was written by the mining agent *before* the repo-wide `.tooling/scrub.py` pass, and
> `scrub.py` targets `fixtures/scenarios/*.md` too. So the left-hand "real value" column
> has been rewritten with the same placeholders as everywhere else. Several rows therefore
> now read as an identity (`OWNER_CHAT_ID` → `OWNER_CHAT_ID`), and a few read as a
> contradiction, because this group's own mapping targets differ from the repo-wide map's.
> The authoritative mapping is `.tooling/scrub-map.json`; the "same length, unchanged"
> claims below are about the group's own substitution, not about the repo-wide one. The
> table is kept for the *reasoning* it records — which values are load-bearing for a hash,
> and which were deliberately left alone — not as a lookup.

| Real value | Replacement | Note |
|---|---|---|
| owner chat id `OWNER_CHAT_ID` | `OWNER_CHAT_ID` | |
| spreadsheet id `1L0q…Uknw` | `SHEET_ID_PLACEHOLDER` | |
| `MAT-20260101-901` | `MAT-20260101-001` | same format, same length |
| `MAT-20260101-001` (+ its `ACT-…`/`DRF-…` children) | `MAT-20260101-002` | same format, same length |
| `MAT-20260101-006` (+ children) | `MAT-20260101-003` | same format, same length |
| `MAT-20260801/2/3-00N` (reply policy) | `MAT-20260101-011/012/013` | same format, same length |
| `MAT-20260101-999` (deliberately off-register) | `MAT-20260101-999` | same format, same length |
| `Owner` / `owner (Owner)` | `Jo Neal` / `owner (Jo Neal)` | 7 / 15 chars, unchanged |
| `Riverside car park management` | `Riverside mall car park manager` | 31 chars, unchanged |
| `Riverside car park/centre management` | `Riverside mall car park/centre manager` | 38 chars, unchanged |
| `ACE WA` | `ACE WA` | 6 chars, unchanged |
| `insurerclaims01@example.com` | `insurerclaims01@example.com` | 27 chars, unchanged |
| `claimsotherins@example.com` | `claimsotherins@example.com` | 26 chars, unchanged |
| `Claims Team <InsurerClaims01@Example.COM>` | `Claims Team <InsurerClaims01@Example.COM>` | 41 chars, mixed case preserved |

Left as-is on purpose: all `legislation.wa.gov.au`, `legislation.gov.au`, `police.wa.gov.au`,
`fairwork.gov.au`, `icwa.wa.gov.au` and `magistratescourt.wa.gov.au` URLs (public government
sources, not secrets); `.test` and `.example` addresses (reserved, already synthetic);
`APR-A1B2C3D4E5F60718` (opaque, non-personal); `Sandbox Pty Ltd` and `Test Corp` (deliberately
chosen fake company names that are load-bearing for the predicate assertions).

**Hash regeneration.** Five scenarios carry `"needs_hash_regen": true`
(`wf4-delivery-key-first-send`, `-duplicate-approval-is-a-new-delivery`, `-edited-draft-new-approval`,
`-different-recipient`, `-different-channel`). Their original oracle values (`SND-d7ea6fb4`,
`SND-dc3dd0f9`, `SND-1d1361c3`, `SND-13902296`, `SND-7f2d6450`) were computed by a *separate
Python FNV-1a implementation* over the real recipient address. Because the address changed, the
expectations must be recomputed with an independent FNV-1a — **not** by copying whatever the
JavaScript under test emits, or the oracle degenerates into a restatement.

---

## What each QA workflow was really testing

### 1. `RtNgxMxS10ZOJPFG` — QA - WF5 Conflict Notice Digest Sections → 18 files
**Production code copied:** WF5 **Build Daily Digest**, verbatim, with one deviation — the seven
register-loader lines that call the `Load … (Digest)` nodes are replaced by reads from an injected
fixture object. The Assertions node also inlines a *second* verbatim copy of the digest's
`isTestMatter()` predicate, and a copy of the ingress `resolveTestFlag()` rule.

**Note a provenance discrepancy in the source itself:** the workflow *description* says it re-runs
the Build Daily Digest code from "WF5 active version 983da561", but the node comment says it runs
"the FIXED Build Daily Digest code from the WF5 unpublished draft 811b746c". The code is the draft.

Two things under test:
- **Conflict-notice lifecycle** (10 register fixtures). Notices written by the WF5 conflict detector
  could be silently lost — one whose Telegram delivery failed or was abandoned never resurfaced
  anywhere the owner reads. Three new digest sections plus an unreported-count headline; the
  fixtures pin blank→PENDING, blank+`notified_at`→SENT, FAILED, EXHAUSTED, SENT-stays-silent,
  duplicate `conflict_key`→`DATA_INTEGRITY_CONFLICT`, and a mixture of all of them.
- **Budget omission visibility** (scenario 10). Before the fix, sections dropped to fit the
  3600-character Telegram ceiling vanished with no trace.
- **Fix 1, deterministic TEST ONLY isolation** (T1–T8, 8 files). Dated: on **2026-08-23** a
  synthetic matter was detected as TEST only because the model happened to emit a risk flag saying
  so; it titled the matter `Parked vehicle damage - Perth car park (hit and run) - 17 Aug 2026`
  with no test marker at all. The predicate now reads only raw ingress text and an explicit
  internal flag, and deliberately refuses to fire on "emissions test", "test period", "Sandbox Pty
  Ltd" or "Test Corp".

### 2. `BAKIml11QKedtH9d` — QA - WF5 Reply Policy v2 → 19 files
**Production code copied:** WF5 **Build Reply Context** `resolveReply`, described as
"byte-identical to the WF5 draft, minus the adapter".

Two suites. The **matching** suite (C1–C10) pins thread-first resolution, `THREAD_MISMATCH` on
disagreement, quoted-history tags ignored (`splitQuoted`), sender must be a recorded party,
`OUTBOUND_DRY_RUN` is not correspondence. The **replay** suite (X3, X5, X5b, R1–R6, X1–X4) pins the
ingress-fingerprint idempotency: identical replay is silently `ALREADY_RECORDED`, an edited body or
subject under the same message id is `IDEMPOTENCY_CONFLICT` requiring human review, whitespace
reflow is *not* a conflict, and a pre-fingerprint legacy row fails closed. The dated regression
X5/X5b is explicit in the fixture comment: the normaliser used to substitute a wall clock for a
missing date header, so an ordinary retry produced a new fingerprint and a **false**
`IDEMPOTENCY_CONFLICT`.

The suite is **stateful** — each ACCEPT appends an INBOUND row. Each scenario file therefore carries
the register as it stood when that case ran, plus a `sequence_note`.

### 3. `Rgw4AH2dwwatNfWS` — QA - WF4 Outbound Delivery Key → 9 files
**Production code copied:** the block between the `DERIVATION` markers is **verbatim from the
Approval Gate node of WF4 (`zKr24IThF30e6jXw`)**, copied at build time, with an out-of-n8n drift
check comparing the two texts.

Guards the `$now`-in-the-key-basis regression: a retry after an uncertain send result must resolve
to the same `send_key`/`communication_id`, while a duplicate approval, an edited draft, a different
recipient and a different channel must each produce a *new* key. Plus recipient normalisation
(display name / mixed case collapse to one delivery), a structural no-clock check, and dry-run/send
id separation over a shared hash.

### 4. `eIXXD90oV7dZkLM2` — QA - WF4 Source Alignment Regression → 10 files
**Production code copied:** WF4 **Distil Sources** verbatim, with only its three input lines
parameterised and the clock replaced by `'FIXED-STAMP'`.

Three dated live-execution defects:
- **execution 329** — every Sources row carried another Act's URL against its own title and excerpt.
  `j.url || (ctx.urls||[])[i]`; `fullResponse: true` never yields `j.url`, so the positional fallback
  always won, indexing into a legacy list ordered differently from the Source Registry. Four
  permutations (P1–P4) plus two negative controls (pairedItem stripped; wrong body under right URL).
- **execution 335** — the stored excerpt was `text.slice(0, 6000)`, i.e. the cover page and contents
  list of a consolidated Act. Four sources graded RETRIEVED, `research_status` COMPLETE, and the
  drafter received four contents listings. Cases E1–E4; **E2 reproduces the exact shape**.
- **execution 340** — the pinpoint was harvested from the excerpt window, so it named
  cross-references *inside* s 13 and was blank for the Road Traffic row whose window writes
  "Section 54" with a capital S.

Also references **QA - Source Retrieval Probe `hNw2SnG6NB5KO88z` execution 323** (score 14 on all
five registry URLs) as the origin of the scored-heading logic. That workflow was not in my
assignment and I did not read it.

### 5. `hTz7VbLHENx8ZB1N` — QA - WF4 Integrity Guard Runtime → 8 files
**Production code copied:** two nodes, both marked VERBATIM — WF4 draft `5a2a208f` **Integrity
Guard** (renamed in the harness to `Integrity Guard (production copy)` so a QA shim can occupy the
name that `Verify Selected Row` looks up) and the WF4 draft **Verify Selected Row**.
**Not** production: `Approval Gate` is a STUB emitting only the four fields Verify consumes;
`Mode (equivalent)` is explicitly "equivalent, not verbatim"; `Integrity Guard` (the shim) and
`Inject Verify Fault` are QA-only.

Fixtures are the **real `MAT-20260101-001` snapshot from QA execution 362**: two generations of
Actions rows written 39 minutes apart (17:15:07.880Z and 17:54:35.511Z), so six action ids each
resolve to two rows with different `action_type`, `recipient`, `channel` and `depends_on_json`.
Approval Gate re-queried by action_id and took `ahits[length-1]`. Cases C1/C2 halt on that; C3/C4 are
positive controls; C5A–C5D inject a tampered carried fingerprint, a changed recipient, a changed
channel and an ambiguous action id respectively. Executions **364–367** ran the guard under its
production name.

### 6. `glrx1XJl0cXbmMKu` — QA - WF4 Isolated Caller → 1 file (integration)
No production code copied. It seeds one `DRAFT_DOCUMENT` action into the real Actions sheet and
invokes WF4 (`zKr24IThF30e6jXw`) as a sub-workflow with `waitForSubWorkflow: true`.
Its real purpose was structural: two synthetic nodes (`QA Manual Start`, `QA Router Payload`) had
been wired into WF4's own `Config` node, putting a manual trigger directly on the production send
path. They were removed and replaced by this external caller. Its `Report Run` node is a **version
discriminator** — the draft's Distil Sources emits `heading_marker`, `text_chars` and
`rejection_reason`; the published version emits none of them, so a green sub-workflow result
without those keys proves nothing.

### 7. `rMxfriXtRP8nQGAb` — QA - Source Verification Regression → 8 files
**Production code copied:** WF4 **Distil Sources**, verbatim, with only its two input lines
parameterised. This is the *earlier* Distil Sources — before the registry-alignment and anchored-
excerpt work in #4 — and it still contains the positional fallback
`String(j.url || (ctx.urls || [])[i] || '')` and `excerpt: text.slice(0, 6000)`.
Eight fixtures grade the verification ladder: good WA statute, table of contents (execution 300),
Angular app shell, bare landing page, blocked page, transport failure, guidance-alone, and one
required source failing → PARTIAL.

### 8. `oClbmnidX0swK0oP` — QA - Source Retrieval Fix → 9 files (integration)
Not a copy of a production node — this is the *proposed* fix under test, run over **live GET
requests** against nine real playbook URLs with two negative controls. Referenced execution 284
(legislation.gov.au serving an Angular shell graded RETRIEVED).

### 9. `nRcZrgLMDuBPjmEm` — QA - URL Filter Probe → 2 files
**Production code copied:** WF4 **Build Draft Context** lines 482–489 (the domain allow-list filter),
verbatim, run beside a proposed regex replacement. Establishes that the n8n Code sandbox has no
global `URL` constructor (already recorded in execution 297 as "URL is not defined"), that the
production filter therefore silently discards every candidate inside a swallowing `try/catch`, and
that the regex filter keeps all four.

---

## Assertions I could not convert, and why

1. **`RtNgxMxS10ZOJPFG`, scenario 10, "priority 0 survived budgeting".** The assertion in the
   Assertions node is **vacuous**:
   `(...) || !(...) === false ? true : true` — the conditional's two branches are both `true`, so it
   passes unconditionally regardless of the digest's behaviour. I recorded the *intent* as a
   human-readable assertion in `wf5-digest-budget-pressure.json`, but there is no working oracle to
   port. It needs writing from scratch.
2. **`Rgw4AH2dwwatNfWS`, C7 "no clock in the derivation".** Asserts on the *source text* of three
   functions (`String(normEmail) + String(fnv1aHex) + String(deriveDelivery)` matched against
   `/Date|\$now|now\s*\(|Math\.random/g`). Preserved as an assertion string with a portability
   caveat: a runner must either keep those as stringifiable named declarations or replace it with a
   static lint rule over the production node body.
3. **`Rgw4AH2dwwatNfWS`, all five hash oracles.** Converted but neutered — see "Hash regeneration"
   above. The five files carry `needs_hash_regen: true`.
4. **`glrx1XJl0cXbmMKu` in its entirety.** It performs a real `appendOrUpdate` against a live Google
   Sheet and a real sub-workflow invocation whose downstream behaviour depends on live HTTP. Its
   version-discriminator assertion is meaningful *only* inside n8n, because it inspects which stored
   workflow version resolved. Marked `integration`; not portable.
5. **`oClbmnidX0swK0oP`, all nine URL expectations.** Genuinely `integration` — they assert on what
   third-party government sites currently serve. A failure is a prompt to re-inspect the page, not
   automatically a code regression. The *filter* half of that workflow duplicates
   `nRcZrgLMDuBPjmEm` and is captured there as a pure scenario instead.
6. **`nRcZrgLMDuBPjmEm`, the "production filter returns zero" half.** Marked `integration`, because
   it is only true in an environment lacking a global `URL`. On plain Node.js the production filter
   also returns all four and the verdict flips to `PRODUCTION_FILTER_WORKS_CAUSE_IS_ELSEWHERE`.
   Noted inline in `wf4-regex-host-filter-replaces-url-constructor.json`.
7. **`hTz7VbLHENx8ZB1N`, the `Mode (equivalent)` routing node.** Explicitly not verbatim — it
   re-implements the real Mode switch on `Config.route_group`. Routing behaviour itself is therefore
   untested by this harness and no scenario claims otherwise.
8. **`hTz7VbLHENx8ZB1N`, the Approval Gate's eleven checks.** The node is a stub; its comment says
   the eleven checks "are out of scope here and were tested separately". I did not find that
   separate suite in my nine workflows.
9. **`BAKIml11QKedtH9d`, assertion A1.** Its label is "Every replay outcome carries a deterministic
   audit event id", but the implementation exempts `BLOCKED` decisions
   (`if (r.event_id === '(none)' && r.decision !== 'BLOCKED') auditOk = false;`), so a BLOCKED
   outcome with no `provider_message_id` emits `event_id: ''` and A1 still passes. Converted with the
   gap recorded as an explicit CAVEAT assertion rather than silently preserved.
10. **Scenario 10 of the digest suite is clock-relative.** The original built timestamps from
    `Date.now()`. I froze them against `now = 2026-08-23T06:00:00.000Z` and recorded the offset
    recipe (`now-40d`, `now-(i+2)d`, `now-1h`, `now+3d`) in a `time_anchor` block, because the quiet-
    matter and overdue classifications are meaningless against a fixed wall clock.
11. **Reply-policy fingerprints.** `ingress_fingerprint` values on accumulated INBOUND rows are
    computed at run time by `ingressFingerprint()`. They are recorded as
    `"RUNTIME:ingressFingerprint(event of <case>)"` rather than frozen, so the sanitised addresses do
    not invalidate them. No `needs_hash_regen` is required for this suite.

---

## Things that look like unfixed production bugs

Ranked by how much I would want a human to look at them.

1. **`Verify Selected Row` treats a gate channel of `NONE` as a free pass.** The check is
   `if (U(gate.channel) !== U(row.channel) && U(gate.channel) !== 'NONE')`. So if the Approval Gate
   resolves `channel: NONE` while the register row says `GMAIL`, the mismatch is *not* caught and the
   branch proceeds to the writers. Case C5C injects `MANUAL` and passes; `NONE` is never injected.
   Given the whole point of the node is that recipient and channel "decide where an external message
   would go", this is a live hole. Recorded as a KNOWN GAP assertion in
   `wf4-verify-channel-changed-after-the-gate.json`.
2. **The row fingerprint omits `status` and `updated_at`.** `FP_FIELDS` is
   `action_id, matter_id, action_type, priority, depends_on_json, recipient, channel,
   requires_approval, idempotency_key, created_at`. A row whose `status` flips between the guard and
   the writer (e.g. `AWAITING_APPROVAL` → `CANCELLED`, or a second concurrent run marking it `SENT`)
   produces an identical fingerprint and passes verification. The node's own comment claims it
   detects "if the register changes between the two reads"; for status changes it does not.
3. **The published WF4 may still carry the execution-329 positional fallback.**
   `rMxfriXtRP8nQGAb` copies Distil Sources *verbatim from production* and that copy still contains
   `String(j.url || (ctx.urls || [])[i] || '')` and `excerpt: text.slice(0, 6000)`. The fix lives in
   `eIXXD90oV7dZkLM2`, which copies from a **draft**. `glrx1XJl0cXbmMKu`'s version discriminator
   exists precisely because a sub-workflow call can resolve to the published version. Worth
   confirming that WF4 `zKr24IThF30e6jXw` has actually been published with the alignment fix — if it
   has not, executions 329/335/340 are all still reachable in production.
4. **Integrity Guard reports the *first* conflict as though it were the worst.**
   `const worst = conflicts[0];` then halts with `worst.code`. Conflicts are pushed in the order
   blank-id → blank-idempotency-key → duplicate-idempotency-key → per-action duplicates, so the
   halt code is an artefact of push order, not severity. The full list is in `integrity_detail`, so
   nothing is lost, but the headline code can mislead.
5. **Integrity Guard's blank-field scan uses a wider scope than the approval route intends.**
   `actions.filter(a => S(a.matter_id) === S(cfg.matter_id) || scopeIds.indexOf(S(a.action_id)) !== -1)`
   — on the APPROVAL route, if `cfg.matter_id` happens to be populated (it is, in case C2), the
   blank-id/blank-key scan silently widens to the whole matter even though the declared scope is one
   approval. Benign here because the guard is fail-closed, but the scope label will then name an
   approval while the conflicts come from elsewhere.
6. **Two different FNV-1a implementations coexist in the same codebase.** `Approval Gate` /
   `resolveReply` use the shift-add form (`h + (h<<1) + (h<<4) + (h<<7) + (h<<8) + (h<<24)`, 8 hex
   digits, `.slice(-8)` off a 7-zero pad); `Integrity Guard` / `Verify Selected Row` use
   `Math.imul(h, 0x01000193)` with an 8-zero pad. They produce different digests. Neither is wrong,
   but a future reader comparing an `FP-` value against a `SND-` value will get a surprise, and the
   7-zero pad in the first form means a hash with fewer than 8 significant hex digits is silently
   truncated to 7 characters plus the pad.
7. **Comment/identifier mismatch in Distil Sources.** The fixed version's comment says
   "`PINPOINT_NOT_FOUND` is still returned by verify()", but the status `verify()` actually returns
   is `NO_PINPOINT_FOUND`. Cosmetic, but it is the kind of thing that makes a future grep miss.
8. **`Inject Verify Fault` sits at canvas position `[6000, 1600]`** — several screens away from the
   rest of the harness. Purely cosmetic, but it makes the QA-only fault injector easy to miss when
   eyeballing the graph, which matters for a node whose entire job is to perturb a safety gate.

---

## Filename collision note

`wf5-reply-dry-run-is-not-correspondence.json` collided with a scenario of the same id written
from a different QA workflow (`VelAeCU71KHELUJP`, "QA - WF5 Reply Matching Verification"), which
overwrote mine. The Group A version is therefore filed as
**`wf5-replypolicy-dry-run-is-not-correspondence.json`**. The two are not duplicates — they test
the same rule from two different harnesses — but whoever consolidates should compare them.
