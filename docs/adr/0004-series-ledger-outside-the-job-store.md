---
status: accepted
---

# The coverage ledger is a file, even though jobs are memory-only

A Series' coverage ledger is stored as a JSON file per repository under the
server's cache directory. This stands alongside a job store that is deliberately
in-memory and loses everything on restart.

## Considered options

The apparent inconsistency is the point worth recording: a reader who sees the
job store hold everything in a dict, and a SQLite option deleted outright, will
reasonably ask why this one piece of state is written to disk.

Job state and Series state have different lifetimes. A Job is one render, it is
observed by polling while the process lives, and nothing is lost by forgetting
it afterwards. A Series spans Episodes generated days apart, possibly across
server restarts — forgetting it means Episode 2 re-teaches Episode 1 and the
recap has nothing to recap.

Writing the ledger into the explained repository was rejected: it is the
server's record of what it taught, not an artifact of the user's project, and
creating files in someone's tree as a side effect of asking for a video is
presumptuous. Bringing back SQLite was rejected as far more machinery than one
JSON document per repo needs.

## Consequences

- Deleting the cache directory resets Series continuity but breaks nothing else.
- The ledger is keyed by repository, so two Series about the same repo would
  collide. That is acceptable while an Episode's scope is the only axis; a Series
  identifier would be needed before that stops being true.
