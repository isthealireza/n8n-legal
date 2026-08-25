# Group C notes — sheet-schema and administrative-guard workflows

Scope: the six named admin/probe workflows, the WF2 B1 boundary harness, and every
workflow in the estate that was not on the accounted-for list of 30.

All n8n access was read-only (`search_workflows`, `get_workflow_details`). Nothing was
executed, updated, activated or archived.

## 1. Full workflow inventory (40 workflows, `sortBy: name:asc`, limit 200)

| # | id | name | active | note |
|---|----|------|--------|------|
| 1 | xUcAXTgocHPsHy5Y | 1 - Telegram Intake and Command Router | yes | accounted for |
| 2 | OaVCEsrt2qpo28rB | 2 - Matter Classification and Planning | yes | accounted for |
| 3 | 1rhaSTTviUBanJIy | 3 - Evidence Intake and Storage | yes | accounted for |
| 4 | zKr24IThF30e6jXw | 4 - Research Drafting Approval and Dispatch | yes | accounted for |
| 5 | zDLoMgW42jUm25Q4 | 5 - Inbound Replies and Daily Supervisor | yes | accounted for |
| 6 | JfaCOxRq0FjZ5JWb | 9 - Error Handler | yes | accounted for |
| 7 | wZxVkmUtbGusTR39 | Admin - Create ConflictNotices Tab - 2026-08-25 | no | **Group C** |
| 8 | eZzW0ilVnZJX4aG5 | Legal AI System (Claude) | no | **UNACCOUNTED → Group C** |
| 9 | T6jGZRxNd9pVOfHi | QA - 2 Matter Classification and Planning | **yes** | **UNACCOUNTED → Group C** |
| 10 | kBcbUbZAwGifd9rZ | QA - Add Ingress Fingerprint Column | no | accounted for |
| 11 | zISJ9EDsxKUDA5U5 | QA - Add unmapped_facts_json Column | no | **Group C** |
| 12 | Z0phpkSNeLngQpl1 | QA - Approval Supersede Audit | no | accounted for |
| 13 | vrP4KZLwrsAbekc1 | QA - Communications Delivery Key Census | no | accounted for |
| 14 | ExgwKCZsekbzUBM4 | QA - Create B1 Harness Spreadsheet | no | **Group C** |
| 15 | t64Pc7BbZruFl57G | QA - Create ConflictNotices Tab | no | **Group C** |
| 16 | 3TVCLIVFGlBNSwK4 | QA - Daily Report State Census | no | accounted for |
| 17 | c6YPmuWf3cevjZ3r | QA - Guarded Replay Test | no | accounted for |
| 18 | 4pok4hCJGh60NbM2 | QA - Inbound Key Stability | no | **UNACCOUNTED → Group C** |
| 19 | XevQwFviJHUobw0U | QA - Ingress Round Trip | no | accounted for |
| 20 | bhP6014bnqWEgO1J | QA - Matters Header Probe | no | **Group C** |
| 21 | xb9hgu2rpMjw9CUt | QA - Replay Write Test | no | accounted for |
| 22 | SEzZkM8OTnQIPpwl | QA - Sheet Schema Probe | no | **Group C** |
| 23 | oClbmnidX0swK0oP | QA - Source Retrieval Fix | no | accounted for |
| 24 | hNw2SnG6NB5KO88z | QA - Source Retrieval Probe | no | **UNACCOUNTED → Group C** |
| 25 | rMxfriXtRP8nQGAb | QA - Source Verification Regression | no | accounted for |
| 26 | k0IFnNVRdtMOEmjP | QA - Sources Row Census | no | accounted for |
| 27 | TryzWP4S2VpL8OU0 | QA - Stage 2 Single TEST ONLY Matter | no | accounted for |
| 28 | nRcZrgLMDuBPjmEm | QA - URL Filter Probe | no | accounted for |
| 29 | olEuL3AIVr4ER0bT | QA - WF2 B1 Boundary Harness | no | **Group C** (named in brief) |
| 30 | hTz7VbLHENx8ZB1N | QA - WF4 Integrity Guard Runtime | no | accounted for |
| 31 | glrx1XJl0cXbmMKu | QA - WF4 Isolated Caller | no | accounted for |
| 32 | Rgw4AH2dwwatNfWS | QA - WF4 Outbound Delivery Key | no | accounted for |
| 33 | eIXXD90oV7dZkLM2 | QA - WF4 Source Alignment Regression | no | accounted for |
| 34 | RtNgxMxS10ZOJPFG | QA - WF5 Conflict Notice Digest Sections | no | accounted for |
| 35 | VelAeCU71KHELUJP | QA - WF5 Reply Matching Verification | no | **UNACCOUNTED → Group C** |
| 36 | BAKIml11QKedtH9d | QA - WF5 Reply Policy v2 | no | accounted for |
| 37 | aSygXnnfLDXRR3fK | QA - WF9 Error Handler Test | no | **UNACCOUNTED → Group C** |
| 38 | 9vnlGSbNFSkg0qnc | QA Autopilot — Legal AI | **yes** | **UNACCOUNTED → Group C** |
| 39 | Y62WStOAIC4m0VvP | ZZ BACKUP 2026-08-18 - Legal AI System (Claude) | no | **UNACCOUNTED → Group C** |
| 40 | NslQM7zGpacyCwTS | ZZ CORRUPT IMPORT - DO NOT USE | no | **UNACCOUNTED → Group C** |

**Ten workflows were unaccounted for**: eZzW0ilVnZJX4aG5, T6jGZRxNd9pVOfHi,
4pok4hCJGh60NbM2, hNw2SnG6NB5KO88z, VelAeCU71KHELUJP, aSygXnnfLDXRR3fK,
9vnlGSbNFSkg0qnc, Y62WStOAIC4m0VvP, NslQM7zGpacyCwTS — plus olEuL3AIVr4ER0bT, which the
brief named but the accounted-for list omitted.

## 2. What each Group C workflow did

**wZxVkmUtbGusTR39 — Admin - Create ConflictNotices Tab - 2026-08-25.** Despite the
name, contains no write node. Manual trigger plus two GETs: spreadsheet metadata, and
`values/ConflictNotices` with `UNFORMATTED_VALUE`, whose response length is the true
used-row count. Captured as `conflictnotices-admin-readonly-probe` (integration).

**t64Pc7BbZruFl57G — QA - Create ConflictNotices Tab.** The real migration. Inventory →
Decide → IF → addSheet → header PUT → re-inventory → read back → verify. Three guards,
three scenarios: refuse-if-exists, the 15-column schema, and the before/after
blast-radius fingerprint of every pre-existing tab.

**ExgwKCZsekbzUBM4 — QA - Create B1 Harness Spreadsheet.** Creates the isolated QA
spreadsheet, writes Matters/Actions headers and the `QA_MARKER!A2` token, reads all
three back. Two scenarios: the production-id refusal, and the schema + marker.

**zISJ9EDsxKUDA5U5 — QA - Add unmapped_facts_json Column.** Reads `Matters!N1:N1000`,
refuses unless entirely blank, writes `Matters!N1`, confirms 14 columns. Three
scenarios: the refusal, the already-done rerun, and the post-migration schema.

**bhP6014bnqWEgO1J — QA - Matters Header Probe.** Read-only. Reports live header, last
named column, next free column letter, and duplicate headers. One scenario.

**SEzZkM8OTnQIPpwl — QA - Sheet Schema Probe.** Seven Sheets reads with
`headerRow = firstDataRow = 1` (the trick that surfaces column names on an empty tab),
FNV-1a header hashes, plus the Communications outbound census that gates the WF4
delivery-key format change. One scenario (integration).

**olEuL3AIVr4ER0bT — QA - WF2 B1 Boundary Harness.** The richest source. Four production
nodes copied byte-for-byte behind a four-layer write gate. Eleven scenarios: three
guard scenarios, three fixture cases (C1 canonical / C2 miskeyed / C3 malformed), and
five Finalise Plan behaviours (required-vs-optional gating, contradiction control,
plan-stamped action ids, `/proceed`, question hygiene) plus the write column mapping.

**4pok4hCJGh60NbM2 — QA - Inbound Key Stability.** Evaluates the two production key
expressions through a real Set node against a genuine replay. One scenario.

**VelAeCU71KHELUJP — QA - WF5 Reply Matching Verification.** Nine fixtures through the
verbatim production matcher, with a shadow evaluation of a thread-first replacement.
Five scenarios.

**hNw2SnG6NB5KO88z — QA - Source Retrieval Probe.** GET-only probe of seven official
legal URLs with the scored pinpoint anchoring. One scenario (integration; needs network).

**aSygXnnfLDXRR3fK — QA - WF9 Error Handler Test.** Two nodes: a webhook and a
deliberate throw, with `settings.errorWorkflow = JfaCOxRq0FjZ5JWb`. One scenario.

**T6jGZRxNd9pVOfHi — QA - 2 Matter Classification and Planning.** The QA clone of WF2
that the autopilot patches. Every Sheets write is a pass-through no-op and every
Telegram send is suppressed. Preserves the pre-fix positional action-id scheme; captured
as a regression fixture.

**9vnlGSbNFSkg0qnc — QA Autopilot.** 18 hardcoded scenarios, deterministic assertions,
a semantic judge, then an RCA → fixer → patch-guard → retest → accept/rollback loop.
Two scenarios: the Patch Guard allowlist and the deterministic assertion set.

**NslQM7zGpacyCwTS / Y62WStOAIC4m0VvP / eZzW0ilVnZJX4aG5 — legacy imports.** The corrupt
import is a 193-node merge of WF1-WF5 and WF9 at 2026-08-18 and is the only artefact in
the estate holding the ordered column mapping for every tab at once. That is where
`sheet-schema.json` comes from. `eZzW0ilVnZJX4aG5` is an older generation entirely
(tabs like "Complaints"/"Contracts", `sheetName` bound to index 0) and contributes no
usable schema.

## 3. Sanitisation applied

| real | replacement |
|---|---|
| `SHEET_ID_PLACEHOLDER` | `SHEET_ID_PLACEHOLDER` |
| `QA_SHEET_ID_PLACEHOLDER` (QA harness sheet) | `QA_SHEET_ID_PLACEHOLDER` |
| `DRIVE_FOLDER_PLACEHOLDER` (Drive root) | `DRIVE_FOLDER_PLACEHOLDER` |
| `OWNER_CHAT_ID` | `OWNER_CHAT_ID` |
| `MAT-20260101-001` / `-002` / `-003`, `MAT-20260101-006`, `MAT-20260101-001` | `MAT-20260101-001` / `-002` / `-003`, `MAT-20260102-006`, `MAT-20260102-001` (format and length preserved) |
| `*.test` addresses | `example.com` equivalents (`owner@`, `claims@`, `hr@`, `unknown@`) |
| n8n cloud host in the WF9 webhook URL | omitted; only the path is recorded |

Google credential ids, `www.legislation.wa.gov.au` and `www.legislation.gov.au` URLs,
and the synthetic registration `9XYZ876` are left as-is.

## 4. Assertions that could not be converted

- **`plan_stamp` exact value.** `'P' + Math.floor(Date.now()/1000).toString(36).toUpperCase()`
  is clock-derived, so the scenario asserts the pattern and the *relationships*
  (one stamp per plan, shared by all its actions, `parseInt(s,36)`-sortable) rather than
  a literal. A runner must inject a fixed clock to assert an exact id.
- **FNV-1a header hashes** from the Sheet Schema Probe are computed at run time from the
  live headers; only the algorithm is recorded, not expected digests.
- **Source Retrieval Probe verdicts** depend on live government HTML and on whether the
  site is currently blocking. It is recorded as `integration`; the deterministic half of
  that logic already lives in `QA - Source Verification Regression` (rMxfriXtRP8nQGAb,
  another group's assignment) which runs the same code against eight offline fixtures.
- **Sheet Schema Probe / outbound census counts** are facts about the live register, not
  fixed expectations. The scenario records the *invariant* (`key_format_migration_safe`
  is true only when zero OUTBOUND-like rows exist), not a row count.
- **QA Autopilot scenario payloads.** Only the 18 scenario ids, severities and
  `preserved_behaviour` labels are captured, plus the assertion contract. The payload
  texts are model-prompt fixtures whose expected outputs depend on a DeepSeek call, so
  they are not portable as `pure` scenarios.
- **`QA - WF9 Error Handler Test`** cannot be made pure: the thing under test is n8n's
  own `settings.errorWorkflow` dispatch.

## 5. Things that look like unfixed production bugs

1. **`T6jGZRxNd9pVOfHi` ("QA - 2 Matter Classification and Planning") is ACTIVE.** A QA
   clone left active in the estate. It is only reachable via an Execute Workflow trigger
   so it will not self-fire, but it is also the workflow the autopilot's fixer loop is
   allowed to patch automatically — an active workflow under automated model edit.
2. **`9vnlGSbNFSkg0qnc` (QA Autopilot) is ACTIVE**, and it contains an
   RCA → fixer → apply-patch loop. The Apply Patch and Rollback nodes are named
   "Apply Patch **Stub**" / "Rollback **Stub**", so today it cannot actually write; the
   moment those stubs are implemented, a model-authored patch reaches a live workflow
   with only `Patch Guard` between them.
3. **`wZxVkmUtbGusTR39` is named "Admin - Create ConflictNotices Tab" but creates
   nothing.** Two GETs only. Any agent that trusts the name over the nodes will believe
   a tab was created when nothing was written. Rename or restore the create path.
4. **`NslQM7zGpacyCwTS` ("ZZ CORRUPT IMPORT - DO NOT USE") holds two live schedule
   triggers** (`Daily 08:15 Sweep`, `Daily 09:00 Follow-up Sweep`) and 52 Google Sheets
   nodes pointed at the production register. It is inactive today; activating it by
   accident would run a second, stale copy of the daily sweep against live data. Archive
   it rather than leaving it as a normal inactive workflow.
5. **`aSygXnnfLDXRR3fK` exposes an unauthenticated public GET webhook**
   (`/webhook/qa-wf9-proof3-v9n4h2k8`) whose only purpose is to throw. Anyone holding the
   path can fire a synthetic error alert at the owner's Telegram indefinitely.
6. **Build Reply Context seeds "known parties" from the `recipient` of Actions rows.**
   Noted in the harness itself as a production gap: an action that was never sent still
   contributes its intended recipient to the sender allowlist, which is precisely what
   the `OUTBOUND_DRY_RUN` fixture was written to expose. The proposed replacement
   (real OUTBOUND correspondence only) is shadow-evaluated but was not deployed.
7. **Match Reply to Matter takes the FIRST `[MAT-...]` in subject + body.** Quoted
   history routinely names other matters, and the same counterparty commonly appears on
   two matters, so a reply can be filed against the wrong matter. Thread-first resolution
   is shadow-evaluated in the same harness and was not deployed.
8. **Production Build Reply Context does not set `unverified_kind` on the no-matter
   path**, so `NOT_ON_REGISTER` and `UNMATCHED` are indistinguishable downstream. The
   harness adds the label only for itself and explicitly reports this as a gap.
9. **`Add unmapped_facts_json Column` reads only `Matters!N1:N1000`.** If the Matters tab
   ever exceeds 1000 rows, a non-empty cell below row 1000 is invisible to the guard and
   the emptiness proof is incomplete. Same bound in the ConflictNotices verify
   (`A2:O1000`).
10. **Both ConflictNotices workflows still hardcode the production spreadsheet id** in
    six HTTP node URLs each, with no `QA_MARKER`-style positive proof of target — unlike
    the B1 harness, which refuses to write without one. The only protection is the
    read-before-mutate refusal.
