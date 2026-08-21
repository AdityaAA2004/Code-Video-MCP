---
status: accepted
---

# Episode boundaries come from the caller, not from a planner

Each call to `explain_codebase` produces one Episode over the scope the caller
named. Nothing plans a Series in advance; the coverage ledger only records what
has already been taught so a later Episode can recap instead of repeat.

## Considered options

The tempting alternative is a syllabus: analyse the whole repository, decide it
needs six Episodes, and cut them at sensible boundaries. It is the more
impressive feature and it is what "continue from where the last video left off"
sounds like it requires.

It requires far more than it appears to. Cutting a repo into Episodes means
ranking every concept by teaching value, ordering them by dependency, and
predicting durations before any narration exists — a planning subsystem standing
between the caller and their first video, and one that has to be good before any
Episode is good.

Caller-driven boundaries keep `explain_codebase`'s signature unchanged and make
a Series an emergent property of repeated requests. The ledger does the part
that actually matters to a viewer: Episode 2 knows what Episode 1 said.

Note that this is not a rejection of hierarchical, overview-then-drill-down
videos, which remain a stated goal. It says only that the *caller* chooses the
drill-down, by naming a narrower scope.

## Consequences

- Two Episodes can overlap if the caller asks for overlapping scopes. The ledger
  makes that visible and recappable, but nothing prevents it — the caller is
  assumed to know what they want covered.
- There is no answer to "how many Episodes does this repo need?" and no progress
  bar across a Series. If that becomes desirable, it is a planner, and it should
  arrive as its own decision rather than by accretion.
