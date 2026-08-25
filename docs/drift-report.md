# Drift report

Written by `scripts/sync.py`. Everything below is derived from the
captured content, never from the clock — a run that sees no change
rewrites this file identically and produces no commit. Run times are
in `exports/last-run.json`, which is untracked.

## Changed since last sync

- Nothing. Every captured body hashes identically to the previous sync.

## Per-workflow state

| key | name | capture | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |
|---|---|---|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | ok | `ca8f4a4e99ca` | yes | `140b1ce6ad85` |
| WF2 | 2 - Matter Classification and Planning | ok | `bd590a64c962` | no | - |
| WF3 | 3 - Evidence Intake and Storage | ok | `2e1844d69a07` | no | - |
| WF4 | 4 - Research Drafting Approval and Dispatch | ok | `599914dc160b` | no | - |
| WF5 | 5 - Inbound Replies and Daily Supervisor | ok | `fef1afc9eecb` | yes | `553e0a6a0906` |
| WF9 | 9 - Error Handler | ok | `44ce03650373` | no | - |
