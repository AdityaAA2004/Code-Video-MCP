"""Exception hierarchy shared across every layer.

Two rules this file exists to enforce:

* Business-logic layers raise these, never MCP-specific errors — they must stay
  usable outside a server process.
* The tool layer is the single place that turns them into host-facing text, so
  failure messages read the same from all three tools.

``PipelineError`` subclasses carry the stage they failed in; the job runner puts
that stage into the failure message ``get_render_status`` reports.
"""

from __future__ import annotations


class CodeExplainVideoError(Exception):
    """Base class for every error this package raises deliberately."""


class ConfigurationError(CodeExplainVideoError):
    """Settings are missing, malformed, or mutually inconsistent."""


class JobNotFoundError(CodeExplainVideoError):
    """A ``job_id`` supplied by the host does not exist (or has been reaped)."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"No job with id {job_id!r}")


class StageNotReachedError(CodeExplainVideoError):
    """A result was requested before the stage that produces it has run."""

    def __init__(self, job_id: str, stage: str) -> None:
        super().__init__(f"Job {job_id!r} has not reached stage {stage!r} yet")


class RootResolutionError(CodeExplainVideoError):
    """No usable repo root could be determined for a job.

    Deliberately *not* a ``PipelineError``: this is caught at the tool boundary
    before a job exists, so the caller is told to pass ``root`` immediately
    rather than getting a ``job_id`` that fails on the next poll.
    """


class PipelineError(CodeExplainVideoError):
    """Base for failures inside a graph node."""

    stage: str = "unknown"


class ScopeResolutionError(PipelineError):
    """The requested path/glob does not exist or resolves to nothing usable."""

    stage = "resolve_scope"


class ContextBudgetExceededError(PipelineError):
    """Selected context cannot be reduced under the configured token ceiling."""

    stage = "gather_context"


class StoryboardValidationError(PipelineError):
    """The LLM's storyboard did not conform to the fixed JSON schema."""

    stage = "build_storyboard"


class CodeGenerationError(PipelineError):
    """Slot filling failed: missing slots, unparseable output, or bad refs."""

    stage = "generate_remotion_code"


class RenderError(PipelineError):
    """The Remotion CLI failed or produced no output file."""

    stage = "render_video"


class ExternalToolError(CodeExplainVideoError):
    """A required external binary (rg, node, npx, tsc) is missing or failed."""

    def __init__(self, tool: str, message: str) -> None:
        super().__init__(f"{tool}: {message}")
