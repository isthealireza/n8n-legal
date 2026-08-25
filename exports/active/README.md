# exports/active/

One `<KEY>.json` per workflow (`WF1` … `WF9`, keys as defined in
`config/workflows.json`), holding the **scrubbed published body** — the version
n8n is actually running — plus a `_capture` block recording where the bytes came
from, when, and how the published-vs-draft call was made.

**These were captured through the authenticated read-only n8n MCP server on
2026-08-25, not through the public REST API**, which is unreachable from the
environment this repository was populated in. Every file here says so in its own
`_capture.source` (`"mcp-session"`). See `README.md` and
`docs/API_CAPABILITIES.md`.

Where a workflow's draft and published version ids agreed, the single graph
`get_workflow_details` returned *is* the published one. Where they differed, the
published graph came from `get_workflow_version(activeVersionId)` and was swapped
into the workflow envelope by the same function `scripts/sync.py` uses.

Nothing here is hand-written, and no placeholder or example export is committed:
an export file in this repository is always a real capture or it does not exist.
