---
status: accepted
---

# The narration audio is the clock

`synthesize_narration` runs *before* `generate_remotion_code`, not after it, so
that measured audio durations are inputs to the composition rather than
predictions made ahead of it.

## Considered options

Placing synthesis after codegen is the intuitive order — write the video, then
record over it — and it is what the pipeline was first sketched as.

It cannot work. A Remotion composition needs `durationInFrames` when it is
built, so codegen would have to estimate how long each Scene's narration takes.
The video spec measured macOS `say` dropping roughly a quarter of its requested
pauses (67 of 254 across one video), which means an estimate is not merely
imprecise, it is reliably wrong by tens of seconds.

Two alternatives preserved the original order: emitting a `timings.json` that
the composition reads through Remotion's `calculateMetadata`, or patching
durations into generated code after synthesis. Both split the truth about
duration across two artifacts, and both discover a mistimed video only after
rendering it.

## Consequences

- Scene duration is derived from measured audio, never authored. A duration in
  the Storyboard is a target the planner aims at, not a fact.
- The spec's words-per-second acceptance check can run before any frame is
  rendered, which matters when a 15-minute Episode is 27,000 frames.
- Editing a single narration segment invalidates the composition, not just the
  audio. The synthesis cache keyed on segment text is what keeps that cheap.
