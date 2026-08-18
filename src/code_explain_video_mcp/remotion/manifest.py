"""The scaffold contract: which files the model may write, and to what shape.

(Named ``manifest`` rather than ``scaffold`` so it does not shadow the sibling
``scaffold/`` data directory that holds the actual Remotion project.)

The scaffold directory ships with the package and is copied per job. Only the
files declared as *slots* are ever overwritten; everything else — components,
composition shell, tsconfig, package.json — is fixed. That invariant is what
makes generation reliable, and it is enforced in code rather than trusted to the
prompt.

``ScaffoldManifest`` is also the source of the slot documentation embedded in
the codegen prompt, so the prompt and the enforcement cannot drift apart.

Not implemented: ``scaffold/`` is still an empty directory tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SlotSpec:
    """One file the model is allowed to produce."""

    name: str
    """Slot id used in prompts and in ``GeneratedCode.files``."""

    relative_path: str
    """Path within the scaffold, e.g. ``src/generated/scenes.tsx``."""

    description: str
    """What this file must export and why, injected into the codegen prompt."""

    required_exports: tuple[str, ...]
    """Symbols the file must export; checked before ``tsc`` even runs."""


@dataclass(frozen=True, slots=True)
class ScaffoldManifest:
    """Everything codegen needs to know about the scaffold."""

    root: Path
    composition_id: str
    slots: tuple[SlotSpec, ...]
    component_api_docs: str
    """Prop signatures of Scene/CodeBlock/Transition, quoted into the prompt."""

    node_modules_present: bool


def load_manifest(scaffold_root: Path) -> ScaffoldManifest:
    """Read ``scaffold.manifest.json`` and the component type declarations."""
    raise NotImplementedError


def materialize_scaffold(scaffold_root: Path, workspace: Path) -> Path:
    """Copy the scaffold into a job workspace and return the project root.

    ``node_modules`` is linked or shared rather than copied — a per-job npm
    install would dominate the runtime of every render.
    """
    raise NotImplementedError
