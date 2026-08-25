# n8n-legal

The source of truth, and the offline test harness, for a live legal-practice automation
system running real matters in Western Australia.

**The workflows still execute in n8n.** This repo does not run them. It holds the scrubbed
canonical exports, human specs, the Code-node logic extracted so it runs in plain Node, and
137 scenarios mined out of ~30 retired one-shot QA workflows. Before it existed, testing a
change meant hand-building a throwaway workflow in the n8n UI against live credentials — a
twenty-minute loop. Now it is `node harness/run.js`, and it takes seconds.

Agents (and humans) must read **[AGENTS.md](AGENTS.md)** first: the three lines you do not
cross, the seven open safety issues, and the change procedure. This file is orientation
only and does not repeat it.

> **Private.** `.tooling/scrub-map.json` holds the real spreadsheet ids, Drive folder id,
> owner chat id, n8n credential ids and party addresses as its *keys* — deliberately, see
> `docs/decisions.md` (c). Everything else is scrubbed. Do not push this tree to a public
> remote.

## What the system does, end to end

```
Telegram (owner only)
  │
  ├─ WF1  Telegram Intake & Command Router ─ authorises the chat, normalises message and
  │       callback shapes, routes deterministically (LLM only for free text), owns session state
  │
  ├─▶ WF2 Matter Classification & Planning ─ picks a playbook, extracts and validates facts,
  │       asks for what is missing or emits a bounded action plan; writes Matters + Actions
  │
  ├─▶ WF3 Evidence Intake & Storage ─ files the Telegram upload into a per-matter Drive
  │       folder, extracts text (PDF layer, plain text, or vision for images), writes Evidence
  │
  └─▶ WF4 Research, Drafting, Approval & Dispatch ─ picks the next draftable action, loads
          evidence, fetches and *verifies* legal sources, drafts, records a PENDING approval,
          asks the owner. On a decision the pure-code Approval Gate runs; only if every check
          passes and dry_run is off does Gmail send.

WF5  Inbound Replies & Daily Supervisor ─ matches inbound email to a matter and a party,
     refuses when it cannot, sweeps overdue follow-ups, and posts the daily digest.
WF9  Error Handler ─ sanitised error sink for WF1–WF5; logs, marks the action FAILED, notifies.
```

The register is a single Google Sheet: ten tabs, exact ordered columns in
`fixtures/sheet-schema.json`. It is the system's whole database. **No agent writes to it.**

## Running the harness

```bash
node harness/run.js                          # everything
node harness/run.js --workflow wf4           # one workflow
node harness/run.js --filter delivery-key    # id substring
node harness/run.js --verbose                # every check, and every skip with its reason
```

Offline, deterministic (both clocks frozen), no n8n, no network, no credentials. Exit code
is 0 only when nothing failed.

**Baseline: 74 passed, 3 failed, 60 skipped — so it exits 1.** The three failures are real
(`harness/FINDINGS.md` §1 and §3), not flakes. Do not make them pass by weakening the
assertion. A skip is never a pass; the summary says why each one skipped.

Before any commit:

```bash
python3 .tooling/scrub.py && ./.tooling/leak-check.sh   # both must exit 0
```

## Layout

| path | what it is |
|---|---|
| `exports/wf{1,2,3,4,5,9}.active.json` | scrubbed canonical exports of the **published** version — what production runs. Diff these to see what changed. |
| `exports/wf{1,5}.draft.json` | unpublished drafts that are ahead of published. Not production; not extracted into units. See `docs/draft-vs-active.md`. |
| `workflows/*.md` | human specs: node graph, invariants, output contract, and the incident behind each guard |
| `harness/run.js` | the runner: selects, projects, compares, reports |
| `harness/units/` | 59 modules, one per Code node, extracted from `wfN.active.json`, byte-identical inside the `VERBATIM` markers. Generated — never hand-edit. |
| `harness/n8n-shim.js` | the fake `$input` / `$()` / `$now` that lets those run offline |
| `harness/adapters.js` | one projection per scenario family; `harness/oracles.js` re-implements the hashes independently |
| `harness/FINDINGS.md` | production defects the suite found and nobody has fixed |
| `harness/invariants.md` | generated: live-register properties that cannot be checked offline |
| `fixtures/scenarios/` | 137 scenarios + the mining and consolidation notes |
| `fixtures/sheet-schema.json` | the ten register tabs with exact ordered columns |
| `.tooling/` | scrub map, scrubber, leak-check, unit extractor, scenario normaliser |
| `docs/decisions.md` | why this is shaped the way it is |
| `docs/draft-vs-active.md` | draft vs published: the export naming, and the current divergences |
| `docs/roadmap.md` | what to do next, in order |

Deeper detail: `harness/README.md` (how the runner works, how to add a scenario),
`harness/units/README.md` (the shim contract).
