# Roadmap

Ordered. Each item carries its reasoning in one line. Step 1 is done; the rest is not.

Nothing below authorises crossing the three lines in [`AGENTS.md`](../AGENTS.md) §1.

---

## Step 1 — done: the repo and the offline harness

This tree. 6 scrubbed exports, 6 specs, 59 extracted units, 137 scenarios, a deterministic
runner. Baseline 74 passed / 3 failed / 60 skipped (75/2/60 until the units were re-extracted
from the published version rather than the draft — see `docs/draft-vs-active.md`).

*Why it came first: nothing else is safe until a change can be tested without touching the
live register.*

---

## Step 2 — a dev n8n project, a dev spreadsheet, dev credentials

**The point:** give agents somewhere to *execute*. The harness covers Code nodes only — 19
`integration` and 9 `invariant` scenarios cannot run offline, and neither can a Sheets
mapping, an IF condition, a Gmail send or a sub-workflow dispatch. Today the only place any
of that can be exercised is production.

### What only the owner can do

These are gated on a human with the account, and they block everything after them:

1. **Create a separate n8n project** — not a folder in the existing one. Project-level
   separation is what makes "an agent may mutate anything here" a safe sentence. Give it a
   name nobody will mistake for live (`legal-dev`, not `legal copy`).
2. **Duplicate the register spreadsheet, empty.** Create a new Google Sheet with the ten
   tabs and the exact ordered columns in [`fixtures/sheet-schema.json`](../fixtures/sheet-schema.json)
   — `Matters` (14 cols, `unmapped_facts_json` at N), `Actions` (18), `Drafts` (13),
   `Approvals` (11), `Communications` (18, `ingress_fingerprint` at R), `Evidence` (16),
   `Sources` (11), `Events` (10), `Sessions` (6), `ConflictNotices` (15). Header row only.
   Column *order* matters: several nodes address ranges by A1 notation.
3. **Create dev credentials in that project** — a Google account for Sheets and Drive that
   has no access to the production sheet or the production Drive folder. That "no access" is
   the actual control; a shared credential with a different sheet id is one typo from a live
   write.
4. **A test Telegram bot and a test chat.** New bot via BotFather, new chat id, and set
   `Config.owner_chat_id` in the dev copies to *that* id. WF1 rejects any other chat, so the
   wrong id makes the dev system inert rather than dangerous — but the right one is what
   makes it usable.
5. **A test Gmail account** for WF4's send and WF5's inbound trigger, with a second address
   to play the counterparty. Never a real party's address, not even to "see what it looks
   like".
6. **Copy WF1–WF5 and WF9 into the dev project** and repoint every Sheets node's document
   id, the Drive folder id, and all six credentials. Leave `dry_run` = `"true"` until the
   dev Gmail account has sent one deliberate test message and you have watched it arrive.
7. **Record the dev ids** in `.tooling/scrub-map.json` as new keys with `DEV_*` placeholders,
   then re-run the scrubber — dev ids are not secrets, but they must not be confusable with
   production ids in a diff.

*Why in this order: the spreadsheet and credentials must exist before the workflows are
copied, or the copies come up pointing at production.*

### What an agent can then do

- Run the 19 `integration` scenarios for real, and the 9 `invariant` queries against the dev
  register instead of leaving them as prose in `harness/invariants.md`.
- Reproduce the two failing scenarios end to end, including what the owner actually sees in
  the halt notice.
- Prove a fix by execution before the owner is asked to publish anything.

---

## Step 3 — parallel agents via Orca: Claude Code implements, Codex refutes

Once step 2 exists, run the roles in [`AGENTS.md`](../AGENTS.md) §4 concurrently:

- **Claude Code as implementer** — has n8n MCP access against the *dev* project, edits units,
  proves with the harness, mutates dev drafts. One agent per workflow: two agents on one
  workflow clobber each other's `configHash`.
- **Codex as adversarial reviewer** — repo only, no credentials, defaults to "refuted". A
  second model reading the same diff is worth more than the same model reading it twice,
  because the failure modes are not the same failure modes.
- **Regression guard** — runs `harness/run.js`, reports, changes nothing.
- **Domain critic** — legal only: citation integrity, approval gating, whether anything
  could leave without a human saying yes.

Parallelise across independent workflows and independent defects. **Serialise anything that
touches shared register state** — worktree isolation protects the code, not the shared n8n
instance and not the shared spreadsheet.

*Why after step 2: an adversarial reviewer whose objections can only be settled by argument
converges slowly; one whose objections can be settled by execution converges.*

---

## The seven open safety issues

From [`AGENTS.md`](../AGENTS.md) §6. Each needs **its own change, its own scenario, and the
owner's eyes** — do not fix these opportunistically inside another task. Ordered by how bad
the worst case is.

| # | issue | why it is first / not first |
|---|---|---|
| 1 | `9vnlGSbNFSkg0qnc` **QA Autopilot is active**, with an RCA → fixer → apply-patch → rollback loop. Apply and Rollback are stubs, so it cannot write — today. | A model-authored patch one guard away from a live workflow. The guard is an unimplemented stub, i.e. an accident, not a control. **Deactivate it.** |
| 2 | `T6jGZRxNd9pVOfHi` **a QA clone of WF2 is active** — and is exactly what the autopilot's fixer is authorised to patch. | Same blast radius as 1, and the two compose. Deactivate with 1, in the same change. |
| 3 | `NslQM7zGpacyCwTS` **"ZZ CORRUPT IMPORT — DO NOT USE"** holds two live schedule triggers and 52 Sheets nodes aimed at the production register. Inactive, but not archived. | One accidental activation writes 52 ways into live matters. Archive it — but first confirm nothing else reads it: it is the provenance for `fixtures/sheet-schema.json`. |
| 4 | `aSygXnnfLDXRR3fK` exposes an **unauthenticated public webhook** whose only job is to throw an error at the owner's Telegram. | Anyone with the URL can page the owner indefinitely. Low damage, trivial to close, no reason to keep it. |
| 5 | **WF4 `Verify Selected Row` passes a gate channel of `NONE`** against a register row saying `GMAIL` — demonstrated by execution (`harness/FINDINGS.md` §3). | The last check before a Gmail node fails *open* on an unresolved channel. Needs a scenario asserting fail-closed, which no scenario does today. |
| 6 | **The row fingerprint omits `status`** (`harness/FINDINGS.md` §4), so a row flipped to `CANCELLED` — or `SENT` by a concurrent run — between the guard and the writer still verifies. | Adding `status` to `FP_FIELDS` changes every stored fingerprint; that is a migration, not a one-line fix, which is why it is its own change. |
| 7 | **`resolveTestFlag` does not exist** (`harness/FINDINGS.md` §2). The digest's comment calls `facts.test_data_only` a deterministic signal stamped at ingress; nothing stamps it, so test/live separation falls back to a model-generated title. | The exact 2026-08-23 incident it was written for. Needs the predicate written *and* stamped at ingress in WF2, plus the eight `wf5-testonly-*` scenarios bound to it. |

Plus the standing one, not from §6: **the `Integrity Guard` headline defect** that keeps the
two scenarios red (`harness/FINDINGS.md` §1). Rank conflicts by declared severity before
taking the headline, and count distinct in-scope `action_id`s rather than conflict entries.
Confirm the live node version first — the caveat in §1 explains why.

---

## Smaller repo debts worth clearing on the way

- Several Sheets nodes carry a **stale cached column schema** predating the 2026-08-21
  migrations — `Matters` at 13 columns (no `unmapped_facts_json`) in WF3, WF4 and WF5, and
  `Communications` at 17 (no `ingress_fingerprint`) in WF4. Harmless while writes map by
  header name; refresh them so a future positional read is not surprised.
- `fixtures/sheet-schema.json` and `Append Draft` **disagree on the `Drafts` column order**
  (`draft_type` and `cover_note` at the end vs at positions 5 and 7). One of them is wrong
  about the real sheet. Settle it by reading the live header row — this is a one-line
  read-only check and belongs in step 2's first session.
- Make the `unconsumed expect key` guard use exact matching plus an alias list rather than a
  prefix test (`docs/decisions.md` (f), Known weakness).
- `harness/run.js --workflow wf7` exits 0 having selected nothing. An empty selection should
  be an error, or a filter typo silently reports success.
- `.tooling/leak-check.sh --staged` was silently broken until 2026-08-25: its allowance for
  n8n's numeric condition ids was anchored on the `./` that only working-tree mode produces,
  so the gate fired on 20 structural ids in exactly the mode you run before committing.
  Fixed. Worth a test — a gate nobody can run clean is a gate people learn to skip.
