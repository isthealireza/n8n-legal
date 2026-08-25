# exports/draft/

**This directory ships empty on purpose.**

A `<KEY>.json` file appears here on a sync **only when both** of the following
hold:

1. the n8n public REST API genuinely exposed a published-version object
   (`activeVersion`) alongside the workflow's current `versionId`, **and**
2. those two version identifiers differed — i.e. an unpublished draft is
   genuinely ahead of what production is running.

If the API on the connected instance does not expose that distinction, no file
is written here at all and every export in `exports/active/` is marked
`unavailable_via_public_api`. See `docs/API_CAPABILITIES.md`.

**The absence of a draft file is itself a statement: draft == published.**
