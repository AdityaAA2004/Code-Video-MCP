"""The validate/fix loop must terminate — the one path the dry run never takes.

``validate_syntax`` reports a clean compile under ``dry_run``, so the happy path
is the only one the end-to-end harness exercises. The retry cap is exactly the
kind of thing that silently becomes an infinite loop, so it is tested here
directly against the router rather than through the graph.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from code_explain_video_mcp.config import load_settings
from code_explain_video_mcp.graph.deps import PipelineDeps
from code_explain_video_mcp.graph.nodes import make_give_up, make_should_fix
from code_explain_video_mcp.graph.pipeline import build_graph, recursion_limit_for
from code_explain_video_mcp.jobs.store import InMemoryJobStore
from code_explain_video_mcp.jobs.workspace import WorkspaceManager


@pytest.fixture
def deps(tmp_path) -> PipelineDeps:
    base = load_settings()
    settings = replace(
        base,
        render=replace(base.render, max_fix_retries=3, workspace_root=tmp_path),
    )
    return PipelineDeps(
        settings=settings,
        store=InMemoryJobStore(),
        workspaces=WorkspaceManager(settings.render),
    )


def test_clean_compile_goes_to_render(deps: PipelineDeps) -> None:
    router = make_should_fix(deps)
    assert router({"job_id": "j", "validation_errors": [], "retry_count": 0}) == "render"


def test_errors_below_the_cap_go_to_fix(deps: PipelineDeps) -> None:
    router = make_should_fix(deps)
    for retry in range(deps.settings.render.max_fix_retries):
        state = {"job_id": "j", "validation_errors": ["TS2322: nope"], "retry_count": retry}
        assert router(state) == "fix", f"retry {retry} should still attempt a repair"


def test_at_the_cap_it_gives_up_instead_of_looping(deps: PipelineDeps) -> None:
    """The failure mode this guards against is an unbounded LLM repair loop."""
    router = make_should_fix(deps)
    cap = deps.settings.render.max_fix_retries
    state = {"job_id": "j", "validation_errors": ["TS2322: nope"], "retry_count": cap}
    assert router(state) == "give_up"


def test_past_the_cap_still_gives_up(deps: PipelineDeps) -> None:
    router = make_should_fix(deps)
    cap = deps.settings.render.max_fix_retries
    state = {"job_id": "j", "validation_errors": ["e"], "retry_count": cap + 5}
    assert router(state) == "give_up"


def test_zero_retries_configured_means_no_repair_attempt(tmp_path) -> None:
    base = load_settings()
    settings = replace(
        base, render=replace(base.render, max_fix_retries=0, workspace_root=tmp_path)
    )
    deps = PipelineDeps(
        settings=settings,
        store=InMemoryJobStore(),
        workspaces=WorkspaceManager(settings.render),
    )
    router = make_should_fix(deps)
    assert router({"job_id": "j", "validation_errors": ["e"], "retry_count": 0}) == "give_up"


async def test_give_up_node_fails_the_job_with_a_readable_message(deps: PipelineDeps) -> None:
    node = make_give_up(deps)
    result = await node(
        {"job_id": "j", "validation_errors": ["TS2322: Type 'x' is not assignable"], "retry_count": 3}
    )
    assert result["status"] == "failed"
    assert "TS2322" in result["error"]
    assert str(deps.settings.render.max_fix_retries) in result["error"]


def test_recursion_limit_exceeds_the_longest_legal_path(deps: PipelineDeps) -> None:
    """LangGraph's own guard must not fire before the pipeline's designed cap.

    Otherwise hitting the retry cap surfaces as a GraphRecursionError instead of
    the clear "still failed type-checking after N attempts" job failure.
    """
    laps = deps.settings.render.max_fix_retries
    longest_legal_path = 4 + 2 * laps + 2
    assert recursion_limit_for(deps) > longest_legal_path


def test_graph_topology_wires_all_three_branches(deps: PipelineDeps) -> None:
    graph = build_graph(deps)
    compiled = graph.compile()
    nodes = set(compiled.get_graph().nodes)
    for expected in (
        "resolve_scope",
        "gather_context",
        "build_storyboard",
        "generate_remotion_code",
        "validate_syntax",
        "fix_errors",
        "give_up",
        "render_video",
    ):
        assert expected in nodes
