# What the n8n public REST API can and cannot tell us about draft vs active

Researched 2026-08-25 against the upstream n8n OpenAPI specification. This
question had to be settled before `scripts/sync.py` was written, because the
owner asked for "active and draft versions captured separately" and a sync that
*pretends* to that distinction is worse than one that admits it cannot.

## Verdict

**The public REST API does express the distinction — on a current n8n — and it
also exposes version history. But the script must not assume it.**

Two things are true at once:

1. On an instance whose public API serves the current workflow schema, a single
   `GET /api/v1/workflows/{id}` carries *both* sides: a top-level `versionId`
   and a nested `activeVersion` object.
2. That `activeVersion` field is a recent addition tied to n8n's workflow
   publishing feature. An older instance, or one on an edition without it, will
   return a workflow object with no such field — and then **nothing in the
   response distinguishes published from draft.**

So the capability is a property of the *connected instance*, not of "the API"
in the abstract, and it can only be established at runtime. `sync.py` therefore
detects it per-run and records the answer, rather than baking in an assumption.
See `classify()` in `scripts/sync.py` and the `api_capability` field in
`exports/manifest.json`.

## Evidence

Source: the n8n public API OpenAPI specification, `packages/cli/src/public-api/v1/`
in the n8n repository (`openapi.yml` plus the `$ref`'d handler specs it points
at). The docs site's `/api/` pages 404 at time of writing; the spec is the
authoritative artefact and is what the running instance serves.

### Workflow paths defined in the public API

| path | what this repo does with it |
|---|---|
| `/workflows` | never called (collection listing) |
| `/workflows/{id}` | **read, and only read** — the sole endpoint this repo touches |
| `/workflows/{id}/{versionId}` | read-only version history: "Retrieves a specific version of a workflow from workflow history". Not currently called; available if per-version capture is ever wanted |
| `/workflows/{id}/activate`, `/deactivate`, `/archive`, `/unarchive`, `/transfer`, `/tags` | never called — these are state-changing endpoints and are out of scope for a read-only mirror |

The spec also defines state-changing operations on `/workflows` and
`/workflows/{id}`. They are not enumerated here by method, because this
repository's rule is that a mutating verb must never appear next to an n8n path
anywhere in the tree — not in code, not commented out, not as documentation.
They exist upstream; nothing here reaches them.

Authentication is the `X-N8N-API-KEY` header (a Bearer JWT is also accepted).

### Fields on the workflow object

From the workflow schema in the same spec:

| field | spec description |
|---|---|
| `id` | read-only identifier |
| `name`, `description`, `active`, `isArchived` | metadata |
| `versionId` | "Current version identifier used for optimistic locking" |
| `activeVersion` | reference to the *active version* object |
| `nodes`, `connections`, `settings`, `staticData`, `pinData`, `meta`, `tags`, `shared` | body |
| `createdAt`, `updatedAt`, `triggerCount` | read-only |

And the active-version object itself:

| field | spec description |
|---|---|
| `versionId` | "Unique identifier for this workflow version" |
| `workflowId` | "The workflow this version belongs to" |
| `nodes` | array of node objects |
| `connections` | node connection map |
| `nodeGroups` | "Visual groupings of nodes shown as frames on the canvas" |
| `authors` | "Comma-separated list of author IDs who contributed to this version" |
| `createdAt`, `updatedAt` | timestamps |

All of it read-only, and the whole object is nullable.

### Query parameters

`GET /workflows/{id}` takes `excludePinnedData` (boolean) and nothing else
version-related — there is no `?version=` selector on that path. Selecting a
specific historical version is what `GET /workflows/{id}/{versionId}` is for.
`GET /workflows` takes `active`, `tags`, `name`, `projectId`,
`excludePinnedData`, `limit`, `cursor`.

## How this repo reads that evidence

- **Published version:** `activeVersion.versionId`, with the published graph in
  `activeVersion.nodes` / `.connections` / `.nodeGroups`.
- **Draft version:** the top-level `versionId`, with the draft graph in the
  top-level `nodes` / `connections`.
- **Diverged?** `activeVersion.versionId != versionId`.

One inference is worth flagging as an inference. The spec does not state in
prose *which* graph the top-level `nodes` array holds when a draft is ahead of
published. The structure only makes sense one way — the published graph is the
one carried separately under `activeVersion`, so the top level is the draft —
and this matches what the authenticated MCP server was directly observed doing
in-session on 2026-08-25 (`get_workflow_details` hands back the draft, with the
published body nested alongside it; see `docs/DRAFT_VS_ACTIVE_KNOWN.md`). It is
nonetheless an inference until the first authenticated sync confirms it, and
`sync.py` records `draft_active_determination` in every capture so a wrong
inference is visible rather than silent.

There is also one field the MCP surface has that the public schema does not: a
`sameAsDraft` convenience boolean. Its absence costs nothing — comparing the two
`versionId` values gives the same answer.

## The honest fallback

When `activeVersion` is missing or null, `sync.py`:

- writes **one** file per workflow, to `exports/active/`, and
- stamps it `"draft_active_determination": "unavailable_via_public_api"` with
  `"kind": "unknown"`, and
- writes **nothing** to `exports/draft/`, and
- sets `api_capability` to the same string in `exports/manifest.json` and in
  `docs/drift-report.md`.

In that state the repo does not claim the captured body is the published
version. It claims only that this is what `GET /workflows/{id}` returned. That
is a weaker statement, and it is the true one.

## The one-way guarantee, mechanically

`scripts/sync.py` contains exactly one function that opens a network
connection, `_get()`. It asserts its method before it opens anything, and the
constant it asserts against is the only HTTP method named in the file. Every
state-changing endpoint the n8n API offers is unreachable from this codebase:
there is no code path to one, no disabled code path to one, and no worked
example of one. A read of the whole tree confirms no mutating HTTP verb appears
beside an n8n URL anywhere.
