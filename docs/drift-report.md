# Drift report

Written by `scripts/sync.py`. Everything below is derived from the
captured content, never from the clock — a run that sees no change
rewrites this file identically and produces no commit. Run times are
in `exports/last-run.json`, which is untracked.

## Changed since last sync

- WF1: active body changed
- WF1: draft body changed
- WF2: active body changed
- WF2: draft body appeared
- WF3: active body changed
- WF3: draft body appeared
- WF4: active body changed
- WF4: draft body appeared
- WF5: active body changed
- WF5: draft body changed
- WF9: active body changed
- WF9: draft body appeared

## Per-workflow state

| key | name | capture | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |
|---|---|---|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | ok | `d79d89ab473a` | yes | `25434d3b094b` |
| WF2 | 2 - Matter Classification and Planning | ok | `1bebac331dce` | yes | `e38cb65dca82` |
| WF3 | 3 - Evidence Intake and Storage | ok | `d811d9915968` | yes | `94e14b3dbdd5` |
| WF4 | 4 - Research Drafting Approval and Dispatch | ok | `f501d6a7b2ec` | yes | `9715c6ae34e3` |
| WF5 | 5 - Inbound Replies and Daily Supervisor | ok | `c8d7185c248a` | yes | `2828ebba6388` |
| WF9 | 9 - Error Handler | ok | `71f3b358ab9b` | yes | `56754f08a4c3` |
