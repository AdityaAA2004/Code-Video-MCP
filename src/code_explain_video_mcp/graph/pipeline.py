"""Graph topology: the wiring, and nothing else.

The shape is the one in the architecture doc::

    resolve_scope -> gather_context -> build_storyboard -> generate_remotion_code
        -> validate_syntax -+-(clean)------> render_video -> END
                            +-(errors)-----> fix_errors --> validate_syntax
                            +-(cap hit)----> give_up -----> END

The only interesting edge is the three-way branch out of ``validate_syntax``.
Making "gave up" a *node* rather than an exception is deliberate: the retry cap
is a designed outcome of the pipeline, so it should be visible in the topology
where someone reading the graph will find it.

Compilation happens once per server, not once per job — the graph is stateless
and every job supplies its own state object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from code_explain_video_mcp.graph.nodes import (
    make_build_storyboard,
    make_fix_errors,
    make_gather_context,
    make_generate_remotion_code,
    make_give_up,
    make_render_video,
    make_resolve_scope,
    make_should_fix,
    make_validate_syntax,
)
from code_explain_video_mcp.graph.state import PipelineState
from code_explain_video_mcp.logging_conf import get_logger

if TYPE_CHECKING:
    from code_explain_video_mcp.graph.deps import PipelineDeps

logger = get_logger("graph.pipeline")

NODE_RESOLVE_SCOPE = "resolve_scope"
NODE_GATHER_CONTEXT = "gather_context"
NODE_BUILD_STORYBOARD = "build_storyboard"
NODE_GENERATE_CODE = "generate_remotion_code"
NODE_VALIDATE = "validate_syntax"
NODE_FIX = "fix_errors"
NODE_GIVE_UP = "give_up"
NODE_RENDER = "render_video"


def build_graph(deps: "PipelineDeps") -> StateGraph:
    """Assemble the uncompiled graph over ``deps``."""
    graph: StateGraph = StateGraph(PipelineState)

    graph.add_node(NODE_RESOLVE_SCOPE, make_resolve_scope(deps))
    graph.add_node(NODE_GATHER_CONTEXT, make_gather_context(deps))
    graph.add_node(NODE_BUILD_STORYBOARD, make_build_storyboard(deps))
    graph.add_node(NODE_GENERATE_CODE, make_generate_remotion_code(deps))
    graph.add_node(NODE_VALIDATE, make_validate_syntax(deps))
    graph.add_node(NODE_FIX, make_fix_errors(deps))
    graph.add_node(NODE_GIVE_UP, make_give_up(deps))
    graph.add_node(NODE_RENDER, make_render_video(deps))

    graph.add_edge(START, NODE_RESOLVE_SCOPE)
    graph.add_edge(NODE_RESOLVE_SCOPE, NODE_GATHER_CONTEXT)
    graph.add_edge(NODE_GATHER_CONTEXT, NODE_BUILD_STORYBOARD)
    graph.add_edge(NODE_BUILD_STORYBOARD, NODE_GENERATE_CODE)
    graph.add_edge(NODE_GENERATE_CODE, NODE_VALIDATE)

    graph.add_conditional_edges(
        NODE_VALIDATE,
        make_should_fix(deps),
        {
            "fix": NODE_FIX,
            "render": NODE_RENDER,
            "give_up": NODE_GIVE_UP,
        },
    )

    graph.add_edge(NODE_FIX, NODE_VALIDATE)
    graph.add_edge(NODE_GIVE_UP, END)
    graph.add_edge(NODE_RENDER, END)
    return graph


def compile_pipeline(deps: "PipelineDeps") -> Any:
    """Build and compile the graph once for the lifetime of the server.

    ``recursion_limit`` is left to the caller's invocation config; the retry cap
    in :func:`~code_explain_video_mcp.graph.nodes.make_should_fix` is what
    actually bounds the fix loop, and it must be the binding constraint so that
    hitting it produces a clear job failure rather than a LangGraph
    ``GraphRecursionError``.
    """
    compiled = build_graph(deps).compile()
    logger.debug(
        "compiled pipeline (dry_run=%s, max_fix_retries=%d)",
        deps.settings.dry_run,
        deps.settings.render.max_fix_retries,
    )
    return compiled


def recursion_limit_for(deps: "PipelineDeps") -> int:
    """A ``recursion_limit`` comfortably above the worst legal path length.

    Worst case is: 4 linear stages, then ``max_fix_retries`` laps of
    (validate → fix), then a final validate, then give_up/render. Doubling that
    and adding slack keeps LangGraph's own guard from firing before the
    pipeline's designed cap does.
    """
    laps = deps.settings.render.max_fix_retries
    return 2 * (4 + 2 * laps + 2) + 10
