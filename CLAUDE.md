# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

Pre-alpha. The three MCP tools, the async job store, and the full LangGraph pipeline are wired and working end to end — but **the pipeline runs in dry-run mode**: every stage executes, logs, and reports real progress, while the stage *bodies* are placeholders. No LLM is called, no `tsc` runs, no video is rendered.

What is real: `resolve_scope` (a genuine bounded, ranked repo walk), the job lifecycle, stage progression, polling, the storyboard schema, and the validate/fix retry cap.

What is a placeholder: `gather_context`, `build_storyboard`, `generate_remotion_code`, `validate_syntax`, `fix_errors`, `render_video`. Each raises `NotImplementedError` when `dry_run=False`, so a stage can never silently fake a result once the switch is off. Flip `Settings.dry_run` (or `CODE_EXPLAIN_VIDEO_DRY_RUN=0`) as each one lands.

Still missing entirely: the Remotion scaffold (`remotion/scaffold/`), `llm/client.py` implementations, and the `delivery` package.

[base-architecture.md](base-architecture.md) is the spec. Where the code and the doc disagree, the doc is the intent.

## Environment

`.venv/` is a **Python 3.12** virtualenv and is the only interpreter with the dependencies. Always run through it — the system `python3` is 3.14 and has none of them. Do not use the bare `python3` on PATH.

```bash
.venv/bin/python app.py          # never `python3 app.py`
.venv/bin/python -m pip install -r requirements.txt
```

Recreate from scratch:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependency rules ([requirements.txt](requirements.txt)):

- **`fastmcp==4.0.0b3` is a pre-release** and the exact pin is load-bearing. A bare `fastmcp` resolves to the 3.4.x stable line instead. Verified: this installs clean with no `--pre` flag.
- Only direct dependencies belong in `requirements.txt`; pip resolves the rest.
- `langgraph` constrains `websockets<16`, downgrading the 17.x FastMCP would otherwise take. This is verified compatible (`pip check` clean, both import fine at 15.0.1) — don't "fix" it.
- `pandas-plink`, `genoml2`, `tensorflow`, and `protobuf` are **not** dependencies of this project. FastMCP 4.0.0b3 depends only on `fastmcp-slim`. Those are genomics/ML packages that were pasted in from an unrelated project and deliberately excluded.

## Running it

The server defaults to **stdio**, which is what Claude Code and Codex spawn:

```bash
.venv/bin/python -m code_explain_video_mcp          # stdio (host-facing)
.venv/bin/python app.py                             # HTTP on 127.0.0.1:8000
```

End-to-end exercise of all three tools (starts an in-process server, polls a job
to completion, reads the storyboard mid-flight):

```bash
.venv/bin/python app_client.py
.venv/bin/python app_client.py --scope src/code_explain_video_mcp/graph
.venv/bin/python app_client.py --url http://127.0.0.1:8000/mcp   # against a running server
```

Tests:

```bash
.venv/bin/python -m pytest tests/ -q
```

Host registration: [.mcp.json](.mcp.json) for Claude Code; an
`[mcp_servers.code_explain_video]` block in `~/.codex/config.toml` for Codex.

## Settings

`Settings` describes **the server process** — caps, model names, timeouts, paths.
It is deliberately *not* per-codebase; the things that vary per repo (`root`,
`scope`, `goal`) are tool arguments.

Precedence, lowest to highest: `default_settings()` → an optional TOML file
passed via `--config` → `CODE_EXPLAIN_VIDEO_*` env vars. **Nothing ever searches
for a config file** — there is no `config.toml` convention and no directory scan.
Defaults are complete and self-sufficient; the only two `None` fields
(`jobs.sqlite_path`, `delivery.public_base_url`) gate features that are off.

`root` resolution is the one genuinely fragile input, because a stdio server
inherits its *host's* working directory. The ladder in `tools/elicitation.py`
is: explicit `root` → configured `default_root` → cwd if it has repo markers →
nearest enclosing repo root → **hard error**. It never falls back to "use cwd
anyway". Leave `default_root` unset on a general-purpose server: it outranks the
cwd rungs on every call, so pinning it would make "explain that other repo"
silently explain the pinned one.

Verified working end to end (client prints the stub explanation).

FastMCP 4 gotcha worth remembering: `run()` is `run(transport=None, show_banner=None, **transport_kwargs)`. It defaults to **stdio**, and because `host`/`port` land in `**transport_kwargs` they are silently ignored rather than raising — a server that looks correctly configured for HTTP will sit on stdio while clients fail to connect. Always pass `transport="http"` explicitly, and note `host` is a bind address (`127.0.0.1`), not a URL.

## Architecture (target, per base-architecture.md)

The design constraint that shapes everything: **only three tools are exposed to the MCP host** — `explain_codebase`, `get_render_status`, `get_storyboard`. Every other step (scope resolution, context gathering, storyboard building, code generation, validation, render) is an internal LangGraph node, not a host-callable tool. Resist adding tools when adding pipeline capability.

Pipeline: `resolve_scope → gather_context → build_storyboard → generate_remotion_code → validate_syntax ⇄ fix_errors (capped ~3 retries) → render_video`. A single LangGraph state object threads `scope`, `goal`, `context_chunks`, `storyboard`, `remotion_code`, `validation_errors`, `retry_count`, `job_id`, `status`.

Load-bearing decisions to preserve when implementing:

- `explain_codebase` returns a `job_id` immediately; work runs as a background asyncio task. Status comes from polling, not from a blocking tool call.
- The storyboard is **JSON with a fixed schema** (scenes with title, bullets, code snippet + line refs, narration, goal tie-in, duration) because `generate_remotion_code` consumes it programmatically.
- Remotion code is generated by **filling slots in a checked-in scaffold**, not freeform generation. Keep the scene/code-block/transition components in the repo.
- Elicitation is optional: it works in Claude Code CLI, not in Claude Desktop, unknown elsewhere. Every path that would elicit needs a non-elicitation fallback (use attached context, else whole repo while saying so explicitly).
- Scope resolution must cap files/tokens; hosts cannot render video inline, so final results are file paths or served URLs.

## Related skills

`remotion-best-practices` covers the Remotion side of `generate_remotion_code` and the render step.
