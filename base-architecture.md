# Code-Explanation Video MCP Server — v1 Architecture

## Goal
An open-source MCP server that generates a short explainer video for an attached file/folder (or whole repo), tied to a user-stated goal, rendered via Remotion.

## High-level flow

```
Host (Claude Code / Codex / Copilot)
        |
        v
[MCP Server]
        |
   +----+----------------------------------------------+
   |                                                    |
   v                                                    |
Entry tool: explain_codebase(scope?, goal)               |
        |                                                |
        v                                                |
   LangGraph pipeline (internal, not exposed as tools)    |
        |                                                |
   1. resolve_scope        -> figure out file/folder/repo |
   2. gather_context        -> grep/read relevant code     |
   3. build_storyboard      -> JSON: teaching points,      |
                               snippets, narration, beats   |
   4. synthesize_narration   -> two-voice TTS, measured     |
   5. generate_remotion_code -> storyboard -> props         |
   6. validate_syntax        -> tsc --noEmit on scaffold    |
   7. fix_errors (loop, capped retries) -> back to 6        |
   8. render_video           -> Remotion CLI -> MP4         |
        |
        v
   returns job_id immediately (async)
        |
        v
Poll tool: get_render_status(job_id) -> path/URL when done
```

## MCP surface (tools exposed to host)

Keep this minimal — 3 tools total for v1.

1. **`explain_codebase`**
   - Inputs: `scope` (optional path/glob), `goal` (free text, optional)
   - If `scope` not given and client supports elicitation: ask whole-repo vs specific path.
   - If client doesn't support elicitation: default to whatever's attached in context; if nothing attached, default to whole repo but say so explicitly in the response.
   - Kicks off the LangGraph pipeline async, returns `job_id` + estimated stage count.

2. **`get_render_status`**
   - Input: `job_id`
   - Returns: current stage, progress, or final result (video path/URL + storyboard MD) when done.

3. **`get_storyboard`** (optional but useful)
   - Input: `job_id`
   - Returns just the storyboard MD once stage 3 completes — lets the user/host review/edit before rendering finishes. Useful escape hatch if video generation is still flaky in v1.

Do NOT expose grep/validate/fix as separate host-callable tools. Those live inside the graph.

## LangGraph pipeline details

- **State object**: carries `scope`, `goal`, `context_chunks`, `storyboard`, `narration_audio`, `remotion_code`, `validation_errors`, `retry_count`, `job_id`, `status`. `remotion_code` now holds serialised props rather than generated source ([ADR-0001](docs/adr/0001-props-not-generated-tsx.md)).
- **resolve_scope**: if whole repo, walk directory tree, exclude common noise (node_modules, .git, build dirs, lockfiles). Cap total files/tokens pulled — decide a hard ceiling now (e.g. top N files by size/import-centrality) so "whole codebase" doesn't blow context.
- **gather_context**: **deterministic, no model call.** grep/read via ripgrep, pulling relevant functions/classes rather than whole files, then rank and cap into context chunks. Keeping this mechanical means the pipeline makes exactly one model call, so a bad Episode is unambiguously a prompt problem — and chunk selection stays unit-testable.
- **build_storyboard**: LLM call. Output a fixed schema (JSON, since later stages consume it programmatically) — list of scenes, each with: title, teaching points, teaching beat, code snippet (with line refs and a walkthrough), narration segments, tie-in to `goal`, target duration. [video-spec.md](video-spec.md) is the quality contract this stage must satisfy; its §9 is enforced in `storyboard/validation.py`, not in the prompt. Two addressing rules matter here: **snippets are line-addressed** and every one is verified against the file on disk at storyboard time (this is the anti-invention check), while **ledger entries are symbol-addressed** and only need to remain true, so a Series survives the code being reformatted or moved. `goal_tie_in` is required on code Scenes only — forcing one onto a `section` or `recap` Scene produces filler.
- **synthesize_narration**: two-voice TTS (Host + Learner) per narration segment, transcoded to WAV — macOS `say` emits AIFF that Remotion's bundled ffprobe cannot parse. Synthesize each segment twice and diff the durations to measure real silence, because `say` drops roughly a quarter of requested pauses. Cache on a hash of (text, voice, markup). **This runs before codegen: the audio is the clock** — see [ADR-0002](docs/adr/0002-narration-before-codegen.md).
- **generate_remotion_code**: no model call and no generated TSX. Serialise the storyboard into props and copy the checked-in scaffold, whose components (scene shell, code block with progressive line reveal, teaching-point list, caption bar) render it directly — see [ADR-0001](docs/adr/0001-props-not-generated-tsx.md).
- **validate_syntax**: run `tsc --noEmit` against the scaffold in a sandboxed temp dir. Since no code is generated per job, this is a guard against a broken scaffold or malformed props rather than the model's output, and a job is expected never to enter the repair loop.
- **fix_errors**: feed errors back to LLM, cap at ~3 retries, then fail the job with a clear error rather than looping forever.
- **Storyboard acceptance is two-tier.** The video spec's §9 checks split into per-Scene rules (point count, sentence length, a `mechanism` point present) and whole-Episode rules (≥ 3 of 4 distinct teaching beats; objectives, recap and summary scenes present). A per-Scene failure regenerates only that Scene; a whole-Episode failure regenerates the Storyboard. Regenerating twelve Scenes because one point ran long is waste, and regenerating one Scene can never fix a missing summary.
- **render_video**: shell out to Remotion CLI (`npx remotion render`), write MP4 to a job-scoped output dir. **`node_modules` is installed once into the shared scaffold dir**, not per job — dependencies are identical across jobs now that no code is generated, and a per-job `npm install` costs ~1 minute each. The first render also downloads headless Chrome (~150 MB) once. **The render stage takes its own lock** so only one render runs at a time; see [ADR-0006](docs/adr/0006-render-gets-its-own-lock.md).

## Storage / job handling

- Jobs run async — the job store is an in-memory dict and deliberately does not survive restarts.
- A **Series** of Episodes about one repo carries a **coverage ledger** — what earlier Episodes already taught — as a JSON file per repo in the server's cache dir. This is the one piece of state that outlives the process; see [ADR-0004](docs/adr/0004-series-ledger-outside-the-job-store.md).
- Each job gets its own temp working dir (scaffold copy, props, narration audio, output MP4) — clean up on completion or TTL. The storyboard is written into it as JSON so a failed job stays inspectable.
- **A failed job returns its error *and* its last storyboard.** A caller who can read the Scenes can usually tell immediately whether the problem is a vague `goal` or a bad `scope`; the validator's internal rule vocabulary deliberately does not leak into the tool surface.
- No need for a queue/worker system yet at open-source-hobby scale; a background asyncio task per job is enough for v1.

## Client compatibility notes (bake into code, not just docs)

- Elicitation: known to work in Claude Code CLI, known NOT to work in Claude Desktop, unconfirmed for Codex/Copilot — always have a non-elicitation fallback path.
- Credentials: the model key is read from the standard `ANTHROPIC_API_KEY` environment variable, directly, and is **never** stored in `Settings` — a key in a config dataclass is a key that ends up in a log line or a `repr()`. `Settings` describes the server process; a credential is not that.
- Sampling: do **not** build on it as the primary model path. FastMCP 4.0.0b3 has no `Context.sample()`; sampling is reachable only via the MCP session's `create_message`, which returns unstructured text. The server uses its own API key and keeps sampling as a second `LLMClient` implementation — see [ADR-0003](docs/adr/0003-api-key-primary-host-sampling-fallback.md).
- Don't assume the host can render video inline. **Return an absolute local file path by default**; every host that spawns this over stdio is on the same machine, so a path is immediately useful. Serve a URL only when `delivery.public_base_url` is configured — standing up an HTTP server by default would add a port, a lifetime, and a security surface for a problem nobody has yet.

## Repo structure to start with

```
/server
  /graph          - LangGraph nodes + graph definition
  /tools          - MCP tool definitions (thin wrappers calling graph)
  /remotion       - checked-in Remotion scaffold/template + components
  /jobs           - job store + async runner
  main.py         - FastMCP server entrypoint
/tests
  fixtures/       - sample repos for testing scope resolution
```

## Suggested build order

1. Vertical slice, no MCP yet: hand-write a storyboard JSON for one real file, hand-write matching Remotion code, confirm render pipeline (tsc validate -> remotion render) works end to end.
2. Build `build_storyboard` node (LLM call) against that same file, compare output quality to your hand-written version.
3. Build the scaffold components and the storyboard -> props serialisation; wire validate as a scaffold guard.
4. Wrap the whole thing in the LangGraph graph, add async job handling.
5. Add the three MCP tools, test against Claude Code CLI first (best elicitation + MCP support).
6. Test against Codex CLI and Copilot, add fallback paths where elicitation/sampling isn't there.
7. Only then tackle whole-repo scope resolution and hierarchical (overview + drill-down) videos.