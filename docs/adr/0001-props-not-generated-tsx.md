---
status: accepted
---

# Scenes render from props, not from generated TSX

The Remotion components are checked into the scaffold and consume a Storyboard
directly as props. No model writes React or TypeScript at any point; the
`generate_remotion_code` stage serialises the Storyboard into props and copies
the scaffold.

## Considered options

The architecture doc originally specified that the model would fill slots in the
checked-in scaffold, writing real TSX into marked regions — chosen because
freeform generation of a whole Remotion project is unreliable.

Props-only takes the same argument one step further. Slot-filling exists to
limit how much code a model writes; if the Storyboard schema fully describes a
Scene, the right amount is none. Generated TSX would be a lossy re-encoding of
structured data we already hold.

This became possible only after the schema grew teaching points, teaching beats,
narration segments, and walkthroughs. When a Scene carried nothing but a title
and a list of strings, something had to invent the layout, and a model was the
obvious candidate.

## Consequences

- `validate_syntax` and `fix_errors` lose most of their purpose. The scaffold is
  type-checked once in CI rather than per job, so there is no per-job syntax
  error for a repair loop to repair. The stages and the retry cap stay in the
  graph for now, but a job is expected never to enter the loop.
- `PipelineState.remotion_code` changes meaning from "generated source" to
  "serialised props". The architecture doc names this field, so the name is kept
  even though it now carries data rather than code.
- Adding a genuinely new visual treatment now means writing a component in the
  scaffold and a schema field to drive it, not prompting for it. This is the
  intended trade: less expressive, far more predictable.
