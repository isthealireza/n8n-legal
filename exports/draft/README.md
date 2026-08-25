# exports/draft/

A `<KEY>.json` file appears here **only** where a workflow's draft version id
differs from its published (active) version id — that is, where an unpublished
draft is genuinely ahead of what production is running.

**The absence of a draft file is itself a statement: draft == published.**

As at the 2026-08-25 MCP capture that is two of the six: `WF1.json` and
`WF5.json`. What differs between each draft and its published counterpart, node
by node, is in `docs/drift-report.md` and `docs/DRAFT_VS_ACTIVE_KNOWN.md`.

Like everything under `exports/`, these bodies are scrubbed and MCP-sourced —
each carries `"source": "mcp-session"` in its `_capture` block. The public REST
API was unreachable from the capture environment; see `docs/API_CAPABILITIES.md`.
