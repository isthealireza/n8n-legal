# Drift report

Written by `scripts/sync.py`. Everything below is derived from the
captured content, never from the clock — a run that sees no change
rewrites this file identically and produces no commit. Run times are
in `exports/last-run.json`, which is untracked.

## Changed since last sync

- WF1: active body changed
- WF1: draft body changed
- WF2: active body changed
- WF2: draft body changed
- WF3: active body changed
- WF3: draft body changed
- WF5: active body changed
- WF5: draft body changed
- WF9: active body changed
- WF9: draft body changed

## Per-workflow state

| key | name | capture | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |
|---|---|---|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | ok | `37f3b6a86705` | yes | `065f0df5b968` |
| WF2 | 2 - Matter Classification and Planning | ok | `a48f5fa2b175` | yes | `4abc2ec49486` |
| WF3 | 3 - Evidence Intake and Storage | ok | `bb720857eb7d` | yes | `8abe5e8dab87` |
| WF4 | 4 - Research Drafting Approval and Dispatch | ok | `f501d6a7b2ec` | yes | `9715c6ae34e3` |
| WF5 | 5 - Inbound Replies and Daily Supervisor | ok | `391c9b612c11` | yes | `4e6d40d9c4b1` |
| WF9 | 9 - Error Handler | ok | `457c0d6d893f` | yes | `91e829b646dd` |
