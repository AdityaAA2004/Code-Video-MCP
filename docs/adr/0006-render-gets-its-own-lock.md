---
status: accepted
---

# The render stage takes a second lock of its own

Jobs run two at a time, but only one render runs at a time. `render_video`
acquires a dedicated lock in addition to the job semaphore, so a second job can
progress through every earlier stage while the first is rendering.

## Considered options

One semaphore is the obvious design, and a reader finding two will reasonably
ask why the first was not simply set to 1.

Because the stages are not alike. Everything before `render_video` is I/O-bound:
one model call, a few hundred `say` subprocesses, some file reads. Those overlap
well, and serialising them wastes wall-clock time for no benefit.

Rendering is the opposite. Remotion already parallelises across cores
internally, so a second concurrent render contends for the same eight cores
rather than adding throughput — and a 5-minute Episode is roughly 9,000 frames,
several minutes of saturated CPU. Two renders at once finish no sooner together
than one after the other, while making both slower and the machine unusable.

Dropping `max_concurrent_jobs` to 1 would fix the contention by giving up the
overlap that is actually valuable: building Episode 2's storyboard while Episode
1 renders.

## Consequences

- A job can sit waiting at `render_video` while holding a job slot. This is
  intended, but it means "2 concurrent jobs" describes admission, not
  parallelism at every stage.
- The render lock is the natural throttle if rendering ever moves off this
  machine — it is one place to change, not a rethink of job concurrency.
