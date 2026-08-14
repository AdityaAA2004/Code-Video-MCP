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
   3. build_storyboard      -> MD/JSON: bullets, snippets, |
                               goal-tie-ins, timing         |
   4. generate_remotion_code -> LLM writes React/Remotion   |
   5. validate_syntax        -> tsc/eslint check            |
   6. fix_errors (loop, capped retries) -> back to 5        |
   7. render_video           -> Remotion CLI -> MP4         |
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

- **State object**: carries `scope`, `goal`, `context_chunks`, `storyboard`, `remotion_code`, `validation_errors`, `retry_count`, `job_id`, `status`.
- **resolve_scope**: if whole repo, walk directory tree, exclude common noise (node_modules, .git, build dirs, lockfiles). Cap total files/tokens pulled — decide a hard ceiling now (e.g. top N files by size/import-centrality) so "whole codebase" doesn't blow context.
- **gather_context**: grep/read via ripgrep or similar, not full file dumps where possible — pull relevant functions/classes, not entire files, for large repos.
- **build_storyboard**: LLM call. Output a fixed schema (JSON is safer than MD here since step 4 consumes it programmatically) — list of scenes, each with: title, bullet points, code snippet (with line refs), narration text, tie-in to `goal`, estimated duration.
- **generate_remotion_code**: LLM call, storyboard JSON -> Remotion composition (React + TS). Keep a template/scaffold checked into your repo (scene component, code-block component with syntax highlighting, transition helpers) and have the LLM fill slots rather than generate a whole project from scratch. Much higher reliability than freeform generation.
- **validate_syntax**: run `tsc --noEmit` and/or eslint against generated code in a sandboxed temp dir.
- **fix_errors**: feed errors back to LLM, cap at ~3 retries, then fail the job with a clear error rather than looping forever.
- **render_video**: shell out to Remotion CLI (`npx remotion render`), write MP4 to a job-scoped output dir.

## Storage / job handling

- Jobs run async — use a simple job store (SQLite or even in-memory dict for v1, file-backed if you want restarts to survive).
- Each job gets its own temp working dir (scaffold copy, generated code, output MP4) — clean up on completion or TTL.
- No need for a queue/worker system yet at open-source-hobby scale; a background asyncio task per job is enough for v1.

## Client compatibility notes (bake into code, not just docs)

- Elicitation: known to work in Claude Code CLI, known NOT to work in Claude Desktop, unconfirmed for Codex/Copilot — always have a non-elicitation fallback path.
- Don't assume the host can render video inline. Final tool response should be a file path (if local) or a served URL — plan for a tiny local HTTP server or static file serving from the MCP server's host machine.

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
3. Build `generate_remotion_code` node using the scaffold-slot-filling approach, wire to validate/fix loop.
4. Wrap the whole thing in the LangGraph graph, add async job handling.
5. Add the three MCP tools, test against Claude Code CLI first (best elicitation + MCP support).
6. Test against Codex CLI and Copilot, add fallback paths where elicitation/sampling isn't there.
7. Only then tackle whole-repo scope resolution and hierarchical (overview + drill-down) videos.