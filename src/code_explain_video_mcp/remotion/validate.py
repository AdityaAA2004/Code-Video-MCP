"""Static validation of generated code, before a minutes-long render is attempted.

Runs ``tsc --noEmit`` (and optionally eslint) against the job's project copy —
never against the checked-in scaffold. Compiler diagnostics are parsed into
structured :class:`ValidationIssue` objects rather than passed around as a blob
of stderr, because ``fix_errors`` feeds them back to the model and structure
makes that prompt far more effective.

Not implemented: ``graph.nodes`` stands in for this stage under ``dry_run``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IssueSource = Literal["tsc", "eslint", "scaffold"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One compiler or linter diagnostic."""

    source: IssueSource
    file: str
    """Path relative to the project root."""

    line: int
    column: int
    code: str
    """Diagnostic code, e.g. ``TS2322``."""

    message: str
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of one validation pass."""

    ok: bool
    issues: list[ValidationIssue]
    duration_seconds: float
    raw_output: str


async def validate_project(
    project_root: Path,
    *,
    run_eslint: bool = False,
    timeout_seconds: float = 120.0,
) -> ValidationResult:
    """Type-check (and optionally lint) the generated project.

    Only errors gate the pipeline; warnings are recorded but do not trigger the
    repair loop. Issues are capped before they reach a prompt, so a cascade of
    hundreds of diagnostics cannot blow the repair budget.

    Raises:
        ExternalToolError: ``tsc`` is missing or the run times out.
    """
    raise NotImplementedError
