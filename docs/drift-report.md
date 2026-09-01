# Drift report

Written by `scripts/sync.py`. Everything below is derived from the
captured content, never from the clock — a run that sees no change
rewrites this file identically and produces no commit. Run times are
in `exports/last-run.json`, which is untracked.

## Changed since last sync

- WF3: active body changed
- WF3: draft body disappeared (draft caught up to published?)

## Per-workflow state

| key | name | capture | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |
|---|---|---|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | ok | `16f1d37eb044` | no | - |
| WF2 | 2 - Matter Classification and Planning | ok | `6596d22ccb99` | no | - |
| WF3 | 3 - Evidence Intake and Storage | ok | `cb025d80aec4` | no | - |
| WF4 | 4 - Research Drafting Approval and Dispatch | ok | `5d67272ea61d` | no | - |
| WF5 | 5 - Inbound Replies and Daily Supervisor | ok | `d01a86c60cec` | no | - |
| WF9 | 9 - Error Handler | ok | `457c0d6d893f` | yes | `91e829b646dd` |
