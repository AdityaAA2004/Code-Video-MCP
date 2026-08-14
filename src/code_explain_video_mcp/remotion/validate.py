"""Static validation of generated code, before a minutes-long render is attempted.

Runs ``tsc --noEmit`` (and optionally eslint) against the job's project copy.
Compiler diagnostics are parsed into structured :class:`ValidationIssue` objects
rather than passed around as a blob of stderr, because ``fix_errors`` feeds them
back to the model and structure makes that prompt far more effective.

Everything runs against the *job workspace copy*, never the checked-in scaffold.
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

    def format_for_model(self) -> str:
        """One-line rendering used in the repair prompt."""
        raise NotImplementedError


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
    repair loop.

    Raises:
        ExternalToolError: ``tsc`` is missing or the run times out.
    """
    raise NotImplementedError


def parse_tsc_output(output: str) -> list[ValidationIssue]:
    """Parse ``tsc --pretty false`` diagnostics into structured issues."""
    raise NotImplementedError


def parse_eslint_output(output: str) -> list[ValidationIssue]:
    """Parse ``eslint --format json`` output into structured issues."""
    raise NotImplementedError


def summarize_issues(issues: list[ValidationIssue], *, limit: int = 25) -> str:
    """Truncated digest for status responses and logs.

    Errors are capped so a cascade of hundreds of diagnostics cannot blow the
    repair prompt's budget.
    """
    raise NotImplementedError
