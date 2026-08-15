"""Exception hierarchy shared across every layer.

Two rules this file exists to enforce:

* Business-logic layers raise these, never MCP-specific errors — they must stay
  usable outside a server process.
* The tool layer is the single place that translates these into a host-facing
  error message, so failure text is consistent across all three tools.

``PipelineError`` subclasses carry the pipeline stage they failed in, which is
what ``get_render_status`` reports back to the host.
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
        self.job_id = job_id


class StageNotReachedError(CodeExplainVideoError):
    """A result was requested before the stage that produces it has run.

    Raised by ``get_storyboard`` when the pipeline has not yet finished
    ``build_storyboard``.
    """

    def __init__(self, job_id: str, stage: str) -> None:
        super().__init__(f"Job {job_id!r} has not reached stage {stage!r} yet")
        self.job_id = job_id
        self.stage = stage


class RootResolutionError(CodeExplainVideoError):
    """No usable repo root could be determined for a job.

    Deliberately *not* a ``PipelineError``. This is caught at the tool boundary
    before a job is created, so the caller gets an immediate, actionable error
    telling it to pass ``root`` — rather than a ``job_id`` that fails a few
    seconds later and only surfaces on the next poll.
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


class SyntaxValidationError(PipelineError):
    """``tsc``/eslint reported errors that survived the capped repair loop."""

    stage = "validate_syntax"

    def __init__(self, message: str, retry_count: int) -> None:
        super().__init__(message)
        self.retry_count = retry_count


class RenderError(PipelineError):
    """The Remotion CLI failed or produced no output file."""

    stage = "render_video"


class ExternalToolError(CodeExplainVideoError):
    """A required external binary (rg, node, npx, tsc) is missing or failed."""

    def __init__(self, tool: str, message: str, exit_code: int | None = None) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.exit_code = exit_code
