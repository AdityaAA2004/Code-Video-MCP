"""The Remotion side: scaffold, slot filling, type-checking, rendering.

Two distinct things live under this package:

* ``scaffold/`` -- a checked-in Remotion project (React + TypeScript): scene
  shell, code block with highlighting, transitions. This is data shipped with
  the wheel, not Python source, and it does not exist yet.
* the Python modules here -- copy the scaffold into a job workspace, write the
  generated slot files into it, run ``tsc`` over it, and shell out to the
  Remotion CLI.

The split is the reliability decision from the architecture doc: the model fills
named slots in a project that already compiles, instead of generating a project.

Every function here is still a stub. Until they land, the dry-run bodies in
:mod:`code_explain_video_mcp.graph.nodes` stand in for stages 4-7.
"""

from __future__ import annotations

from code_explain_video_mcp.remotion.codegen import (
    GeneratedCode,
    apply_fix,
    generate_code,
    write_generated_code,
)
from code_explain_video_mcp.remotion.manifest import (
    ScaffoldManifest,
    SlotSpec,
    load_manifest,
    materialize_scaffold,
)
from code_explain_video_mcp.remotion.render import RenderResult, render_video
from code_explain_video_mcp.remotion.validate import (
    ValidationIssue,
    ValidationResult,
    validate_project,
)

__all__ = [
    "GeneratedCode",
    "RenderResult",
    "ScaffoldManifest",
    "SlotSpec",
    "ValidationIssue",
    "ValidationResult",
    "apply_fix",
    "generate_code",
    "load_manifest",
    "materialize_scaffold",
    "render_video",
    "validate_project",
    "write_generated_code",
]
