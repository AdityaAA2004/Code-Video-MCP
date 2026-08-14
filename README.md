# Code-Explanation Video MCP

An open-source [MCP](https://modelcontextprotocol.io) server that turns **a piece of your codebase + a goal you state in plain English** into a short explainer video, rendered with [Remotion](https://www.remotion.dev).

Point it at a file, a folder, or a whole repo, say what you're trying to understand — *"I'm onboarding, show me how auth flows through this service"* — and get back a narrated, syntax-highlighted walkthrough video instead of a wall of text.

> **Status: pre-alpha.** The architecture and module scaffold are in place; the pipeline nodes are placeholders that raise `NotImplementedError`. The working spike today is a single stub tool. See [Roadmap](#roadmap).

---

## Why

Code explanations from an LLM arrive as text you skim once and lose. A short video is a different artifact: it has pacing, it shows code in the order a human should read it, and it ties every scene back to the goal you actually asked about. This project treats "explain this codebase" as a **rendering** problem, not a chat problem.

Because it speaks MCP, it plugs into whatever agent you already use — Claude Code, Codex, Copilot — with no bespoke integration.

---

## How it works

You call one tool. Everything else is internal.

```
Host (Claude Code / Codex / Copilot)
          │
          ▼
   explain_codebase(scope?, goal)  ──▶  returns job_id immediately
          │
          ▼
   ┌──────────────── LangGraph pipeline (not exposed as tools) ───────────────┐
   │                                                                          │
   │  1. resolve_scope          file / folder / whole repo, with a token cap  │
   │  2. gather_context         ripgrep for relevant symbols, not file dumps  │
   │  3. build_storyboard       LLM ─▶ scenes as fixed-schema JSON            │
   │  4. generate_remotion_code LLM fills slots in a checked-in scaffold      │
   │  5. validate_syntax        tsc --noEmit / eslint in a temp workspace     │
   │  6. fix_errors             feed errors back, capped at ~3 retries ─▶ 5   │
   │  7. render_video           npx remotion render ─▶ MP4                    │
   │                                                                          │
   └──────────────────────────────────────────────────────────────────────────┘
          │
          ▼
   get_render_status(job_id)  ──▶  progress, then video path / URL
```

Three design decisions carry most of the weight:

- **Async by default.** `explain_codebase` returns a `job_id` right away and the work runs in the background. Rendering video is far too slow to block a tool call.
- **The storyboard is structured JSON, not prose.** Stage 4 consumes it programmatically, so it's a fixed schema — scenes with titles, bullets, code snippets with line refs, narration, and durations.
- **Generated code fills slots in a scaffold.** A checked-in Remotion project with real scene, code-block, and transition components is far more reliable than asking an LLM to emit a whole project from scratch.

---

## MCP surface

Exactly three tools. Everything else is a graph node.

| Tool | Input | Returns |
|---|---|---|
| `explain_codebase` | `scope` (optional path/glob), `goal` (free text) | `job_id` + estimated stage count, immediately |
| `get_render_status` | `job_id` | Current stage and progress; final video path/URL when done |
| `get_storyboard` | `job_id` | The scene plan as soon as stage 3 lands — reviewable before the render finishes |

`get_storyboard` is the escape hatch: if video generation is flaky, you still get a useful artifact.

**Adding a fourth tool is almost always the wrong move.** Grep, validate, and fix are pipeline internals; exposing them turns a clean one-call interface into a toolkit the host has to orchestrate.

---

## Quickstart

Requires **Python 3.12** and Node (for the Remotion render step).

```bash
git clone https://github.com/AdityaAA2004/Code-Video-MCP.git
cd Code-Video-MCP

python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

Run the current spike end to end:

```bash
.venv/bin/python app.py          # terminal 1 — HTTP server on 127.0.0.1:8000
.venv/bin/python app_client.py   # terminal 2 — calls explain_code once
```

> Always invoke through `.venv/bin/python`. A bare `python3` will pick up a different interpreter without these dependencies.

### Connecting it to a host

Once the server module is implemented, [`fastmcp.json`](fastmcp.json) declares the entrypoint, so MCP hosts can launch it directly:

```bash
fastmcp run fastmcp.json
```

---

## Dependencies

Direct dependencies live in [`requirements.txt`](requirements.txt); `pyproject.toml` intentionally keeps its dependency list empty and exists for packaging the `src/` layout.

| Package | Role |
|---|---|
| `fastmcp==4.0.0b3` | MCP server + client |
| `langgraph==1.2.11` | The internal pipeline graph |
| `anthropic==0.122.0` | LLM calls for storyboard, codegen, and error fixing |

Two notes worth knowing before you touch the pins:

- **The exact `fastmcp` pin matters.** `4.0.0b3` is a pre-release; a bare `fastmcp` resolves to the 3.4.x stable line instead.
- **`websockets` sits at 15.0.1, not 17.x.** LangGraph constrains it below 16. This is verified compatible (`pip check` is clean, both packages import fine) — it isn't a bug to fix.

---

## Layout

```
src/code_explain_video_mcp/
  server.py        FastMCP app factory — the only module aware of transport
  __main__.py      console-script entrypoint
  config.py        settings
  tools/           the three MCP tools; thin wrappers over the graph
  context/         scope resolution, ripgrep search, chunking
  storyboard/      the JSON scene schema + validation
  llm/             LLM client and prompts
  remotion/        codegen, tsc/eslint validation, and the checked-in scaffold
tests/
  fixtures/        sample repos for exercising scope resolution
```

Modules are placeholders with real signatures and full type hints, bodies raising `NotImplementedError`.

---

## Client compatibility

Bake these into code, not just docs:

- **Elicitation is optional.** It works in Claude Code CLI, does *not* work in Claude Desktop, and is unconfirmed elsewhere. Every path that would prompt needs a fallback: use whatever's attached to the context, and if nothing is, default to the whole repo *and say so explicitly* in the response.
- **No host renders video inline.** Final responses are a file path or a served URL.

---

## Roadmap

Build order, deliberately vertical-slice first:

- [ ] Hand-write a storyboard JSON + matching Remotion code for one real file; confirm `tsc` → `remotion render` works end to end
- [ ] `build_storyboard` node, compared against that hand-written baseline
- [ ] `generate_remotion_code` via scaffold slot-filling, wired to the validate/fix loop
- [ ] Wrap in LangGraph; add async job handling
- [ ] The three MCP tools, tested against Claude Code CLI first
- [ ] Codex and Copilot support, with elicitation fallbacks
- [ ] Whole-repo scope resolution and hierarchical overview → drill-down videos

Full design rationale lives in [`base-architecture.md`](base-architecture.md).

---

## License

MIT
