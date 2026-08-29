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
| WF1 | 1 - Telegram Intake and Command Router | ok | `938bc6f52c9b` | yes | `9ebbe0a3b91b` |
| WF2 | 2 - Matter Classification and Planning | ok | `bffc63875972` | yes | `e22a203d8545` |
| WF3 | 3 - Evidence Intake and Storage | ok | `4c3221a9fefb` | yes | `fd755d445499` |
| WF4 | 4 - Research Drafting Approval and Dispatch | ok | `7b17c62fd22a` | yes | `6d426e2cb221` |
| WF5 | 5 - Inbound Replies and Daily Supervisor | ok | `d01a86c60cec` | no | - |
| WF9 | 9 - Error Handler | ok | `457c0d6d893f` | yes | `91e829b646dd` |
