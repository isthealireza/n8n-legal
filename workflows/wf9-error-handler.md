# WF9 — 9 - Error Handler

- **n8n workflow id:** `JfaCOxRq0FjZ5JWb`
- **Raw export:** `exports/wf9.json`
- **Active:** yes · **Nodes:** 7 · **Trigger count:** 0 (error trigger)
- **Created:** 2026-08-18T07:10:55.430Z · **Updated:** 2026-08-25T00:59:40.954Z
- **Draft versionId:** `a5b10619-31e4-4246-8988-90a08bd45ab1`
- **Published (active) versionId:** `df3579b2-6a7a-4d9b-a1e9-632afc78b702` — **draft ≠ published**
- **Settings:** `executionOrder: v1`, `saveManualExecutions: true`, `callerPolicy: workflowsFromSameOwner`, `binaryMode: separate`, `timeSavedMode: fixed`, `availableInMCP: true`. No `errorWorkflow` of its own, no timezone set.

> **Version drift (important).** The published version still runs **redaction v2** and the old sticky note ("any line mentioning a key, token, secret, password, authorization header, or cookie is dropped"). The draft carries **redaction v3 + toText v5 allowlist extraction + `telegram_text` HTML pre-escape + the conditional FAILED claim**. Everything described below as "v3/v5" is in the draft only until republished. The sticky itself states the new behaviour is *"unit-proven and statically verified (1213 assertions)"* but **not runtime-proven — no real error has yet flowed through the published code."*

## Purpose

Central, fail-safe error sink for the legal-matter automation suite. When any of workflows 1–5 throws, WF9 builds a **sanitised** error record, appends it to the Events register, conditionally marks the in-flight action FAILED so a retry cannot double-send, and notifies the owner on Telegram. Credentials and payload bodies are never copied out.

## Trigger / how it is invoked

- **Node:** `Error Trigger` (`n8n-nodes-base.errorTrigger`, v1).
- **Invocation:** n8n calls it automatically when a workflow that names it as its *Error Workflow* fails. WF1 does this via `settings.errorWorkflow = "JfaCOxRq0FjZ5JWb"`.
- The sticky instructs: *"Set this workflow as the Error Workflow on workflows 1 to 5 (Settings > Error Workflow inside each workflow)."*
- It **cannot** be executed via MCP (error triggers are not MCP-executable).

## Node graph

```
Error Trigger
  → Build Error Record            (Code v2)
    → Append Error Event          (Google Sheets append → Events)
      → Action Known?             (IF: has_action === true)
        ├─ true  → Mark Action Failed   (Sheets appendOrUpdate → Actions)
        │            → Telegram - Error
        └─ false → Telegram - Error
```

Plus one sticky note (`Note 33910`), not in the execution path.

### Step detail

1. **Error Trigger** — receives n8n's error payload: `{execution, workflow, trigger, data}`.
2. **Build Error Record** (Code, id `6e707592…`) — the whole safety layer; see Invariants.
3. **Append Error Event** — Google Sheets `append`, `authentication: oAuth2`, doc `SHEET_ID_PLACEHOLDER`, tab **Events**. `onError: continueRegularOutput`, `retryOnFail: true`, `maxTries: 3`, `waitBetweenTries: 2000`.
4. **Action Known?** — IF v2.2, condition `{{ $('Build Error Record').first().json.has_action }}` is boolean true; `looseTypeValidation: true`.
5. **Mark Action Failed** — Sheets `appendOrUpdate` on tab **Actions**, matching column `action_id`. Same retry/onError settings.
6. **Telegram - Error** — sends to hardcoded `chatId: OWNER_CHAT_ID`, text `{{ $('Build Error Record').first().json.telegram_text }}`, `parse_mode: HTML`, `appendAttribution: false`.

## Invariants, guards and fail-closed rules

### A. Redaction v3 — redact secret *values*, never delete lines

Six rules applied in order inside `safe(s, max)`:

| # | Constant | Pattern | Behaviour |
|---|---|---|---|
| 1 | `BOT_TOKEN` | `/\b\d{5,16}:[A-Za-z0-9_-]{20,}/g` | → `[redacted]` |
| 2 | `BOT_IN_URL` | `/\/bot[A-Za-z0-9_:-]{20,}/gi` | → `/bot[redacted]` |
| 3 | `HEADER_LABEL` | `authorization\|proxy-authorization\|www-authenticate\|set-cookie\|cookie\|x-api-key` + sep + `[^\n]+` | value redacted **to end of line** (whole header value is sensitive) |
| 4 | `SCHEME_VALUE` | `\b(bearer\|basic\|digest)\s+[A-Za-z0-9._~+/=-]{8,}` | `scheme [redacted]` |
| 5 | `ASSIGN_LABEL` | api key / apikey / access, refresh, auth, bot, id token / client secret / private key / secret / password / passwd / pwd / passphrase / session id / credentials / bearer / token, followed by `:` or `=` and a quoted or bare value | value → `[redacted]`, **sentence survives**. A bare value **shorter than 3 chars is left alone** so prose like `token = in` is not mangled |
| 6 | (unchanged from v1/v2) | `/[A-Za-z0-9_\-]{32,}/g` | any long opaque run → `[redacted]` |

Output is truncated to `max` (500 for the error message; default 600).

**The defect v3 replaces (quoted from the code):** v2 *"dropped any line matching the word token, secret, password, authorization, bearer, cookie or api key. That is a keyword test, not a secret test, so it deleted ordinary technical errors: `Unexpected token '<' ... is not valid JSON` — one of the most common JavaScript errors there is — was blanked entirely, and the owner received "Error:" with nothing after it. A one-line message mentioning any of those words vanished completely."* It also *"protected less than it appeared to. The line drop only fires when a LABEL is present; a bare secret with no label was never covered by it, and was only ever caught by the 32-character run rule."*

Rules 5's label list deliberately includes bare `token` and `bearer`, but *"only ever fire with a colon or equals after them, so `Unexpected token '<'` and `missing token in expression` are untouched while `token=abc123` is not."*

### B. toText v5 (FU-3) — allowlist extraction, **not** a serialiser

**The defect:** *"`safe()` began with `String(s)`, so a non-string message became `[object Object]` in the Events register and the daily digest showed the owner `workflow / node: [object Object]`. Every fact was lost."*

**Why flattening was rejected (built, tested and REJECTED):** *"An n8n error payload can carry a whole node definition, and that object contains `credentials: {id, name}`, request and response bodies, headers and internal configuration. Flattening turns a field that leaked nothing into one that writes all of it to a spreadsheet. Redaction would have caught the obvious secrets, but 'the redactor will probably catch it' is not a boundary."*

Rules:
- **ALLOWED scalar fields:** `message`, `description`, `name`, `code`, `status`, `statusCode`, `httpCode`, `type`. **Scalars only** — an allowlisted field holding an object is ignored, not stringified and not descended into (*"that is how a `name` or `type` key nested inside a credentials blob stays unreachable"*).
- **CONTAINERS descended into:** `error`, `cause`, `details` — and only if they are objects. *"A container that is a STRING is not read. In execution 244 `cause` held a raw n8n expression full of markup; that is not an error message."*
- **EVERYTHING ELSE is unreachable** — `node`, `credentials`, `context`, `headers`, `request`, `response`, `config`, `body`, `data`, `token`, `secret`, `password`, `authorization`, `cookies` and every unknown key — *"because they are not on the allowlist, not because they are on a denylist. A denylist would need to predict the next key name; this cannot be widened by a payload it has not seen."*
- **Arrays are never flattened.** Only a directly allowlisted error **object** inside one may contribute; loose strings and numbers do not. Scan bounded by `TOTEXT_MAX_ARRAY_SCAN = 5`. Depth bounded by `TOTEXT_MAX_DEPTH = 3`.
- **Cycle guard:** a `seen` array; on revisit it returns null — *"cycle: stop, do not throw"*.
- **Realm safety:** `typeTag()` uses `Object.prototype.toString.call` because *"a Code node runs inside a vm, so instanceof fails on anything built in another realm."*
- **Getter safety:** every key read goes through `readKey()` wrapped in try/catch — *"A getter can throw. Reading a key must never take the workflow down."*
- Strings pass through untouched (*"so string messages stay byte-identical"*). `Date` → ISO (or `[non-string error payload omitted; type=Date, invalid]`). `Error` → `name: message`. Symbol/Function/unmatched → `[non-string error payload omitted; type=…]`; arrays add `, length=N`.

### C. Telegram parse-mode invariant

`esc()` escapes `&` first, then `<`, then `>` — *"Ampersand first, or the escapes escape each other."* Only `telegram_text` is escaped; the twelve Events fields stay unescaped.

**Incidents proving a parse mode is applied when `parse_mode` is absent:**
- **Execution 263** — a message containing six backticks *"came back from Telegram with the backticks stripped and three `code` entities at the matching offsets."*
- **Execution 233** — the same mode *"silently ate a `[line 1]` — it was delivered as `line 1`."*

Conclusion in the code: *"That is legacy Markdown. It means a single unpaired `_ * ` in an n8n error message returns HTTP 400 'can't parse entities', and this node is the last line of defence."* And critically: *"the `[redacted]` marker this very node inserts is being eaten before the owner sees it, so a redacted credential currently reads as though nothing was redacted."* House convention cited: *"all eleven Telegram nodes in workflow 4 set parse_mode HTML explicitly."*

### D. Conditional FAILED claim

`has_action = !!actionId`. From the code: *"Mark Action Failed only runs when `has_action` is true, and **in all seven recorded WF9 executions it never ran** — yet every delivered message still claimed the action had been set to FAILED."*

Closing line is now conditional:
- has action → `"I set the action to FAILED. A retry will not duplicate a send."`
- no action → `"No action id was identified, so no action status was changed."`

The retry-safety rationale (sticky): marking FAILED *"is what makes a retry safe: the approval gate in workflow 4 will not send twice for the same action."*

### E. Matter / action id extraction

`JSON.stringify(ex.error) + ' ' + JSON.stringify(j.data)` is regex-scanned for `\b(MAT-[A-Za-z0-9-]+)\b` and `\b(ACT-[A-Za-z0-9-]+)\b`, whole thing wrapped in try/catch (silently yields empty strings on failure).

### F. Backward-compatibility invariant

*"EVERY EXISTING FIELD IS UNCHANGED. The Events register mapping reads event_id, event_type, severity, matter_id, action_id, workflow_name, workflow_id, node, message, execution_id, execution_url and created_at. All twelve are produced exactly as before, from the same inputs, unescaped. Only the new `telegram_text` field is escaped, and only the Telegram node reads it."*

### G. Never-block invariants on the writes

Both Sheets nodes: `onError: continueRegularOutput`, `retryOnFail: true`, `maxTries: 3`, `waitBetweenTries: 2000` — a Sheets outage must not swallow the Telegram alert.

## Output contract

`Build Error Record` emits exactly one item:

| Field | Value |
|---|---|
| `event_id` | `'EVT-' + ISO timestamp digits, first 14` |
| `event_type` | `WORKFLOW_FAILED` (constant) |
| `severity` | `ERROR` (constant) |
| `matter_id` | extracted `MAT-…` or `''` |
| `action_id` | extracted `ACT-…` or `''` |
| `workflow_name` | `wfd.name` or `unknown` |
| `workflow_id` | `wfd.id` or `''` |
| `node` | `ex.lastNodeExecuted` → `tr.error.node` → `'unknown'` |
| `message` | sanitised, max 500 chars |
| `execution_id` | `ex.id` |
| `execution_url` | `ex.url` |
| `mode` | `ex.mode` |
| `created_at` | ISO now |
| `has_action` | boolean |
| `telegram_text` | HTML-escaped multi-line message |

## Google Sheets surface

Spreadsheet: **`SHEET_ID_PLACEHOLDER`** (both nodes, hardcoded).

**Tab `Events`** — append. Columns written:

| Column | Expression |
|---|---|
| `event_id` | `{{ $json.event_id }}` |
| `event_type` | `{{ $json.event_type }}` |
| `severity` | `{{ $json.severity }}` |
| `matter_id` | `{{ $json.matter_id }}` |
| `action_id` | `{{ $json.action_id }}` |
| `workflow` | `{{ $json.workflow_name + ' (' + $json.workflow_id + ')' }}` |
| `node` | `{{ $json.node }}` |
| `message` | `{{ $json.message + ' \|\| exec ' + $json.execution_id + ' ' + $json.execution_url }}` |
| `chat_id` | `""` (always blank here) |
| `created_at` | `{{ $json.created_at }}` |

**Tab `Actions`** — appendOrUpdate, match on `action_id`. Written: `action_id`, `status` = `FAILED` (literal), `blocked_reason` = `{{ 'Run failed at ' + …node }}`, `updated_at` = `{{ $now.toISO() }}`.
Full declared Actions schema (read by the node, not all written): `action_id, matter_id, action_type, description, status, priority, depends_on_json, recipient, channel, requires_approval, draft_id, approval_id, due_at, deadline_basis, blocked_reason, idempotency_key, created_at, updated_at`.

## Telegram side effects

Exactly one: **Telegram - Error** → chat `OWNER_CHAT_ID`, `parse_mode: HTML`, `appendAttribution: false`, webhookId `7b560a9b-12ee-4b8b-a23a-b44928ff4cf2`, credential `CRED_TELEGRAM` ("Telegram account").

Message body:

```
A workflow run failed.

Workflow: <name>
Node: <lastNode>
Matter: <MAT-… | not identified>
Action: <ACT-… | not identified>
Error: <sanitised message>
Execution: <id>

The failed run sent nothing outside this chat.
<conditional closing line>
```

No other outbound channel. Nothing is emailed, no Drive write, no sub-workflow call.
