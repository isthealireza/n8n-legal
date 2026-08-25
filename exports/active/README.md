# exports/active/

**This directory ships empty on purpose.**

It fills on the **first authenticated sync** — that is, the first run of
`scripts/sync.py` with a real `N8N_BASE_URL` and `N8N_API_KEY` present, either
locally or via the `n8n-sync` GitHub Action.

Each file will be `<KEY>.json` (`WF1.json` … `WF9.json`, keys as defined in
`config/workflows.json`), holding the **scrubbed** body that the n8n public REST
API returned for that workflow's *published / active* version, plus a `_capture`
block recording where it came from, when, and how confident the active-vs-draft
determination is.

Nothing here is hand-written, and no placeholder or example export is committed:
an export file in this repo is always a real capture or it does not exist.
