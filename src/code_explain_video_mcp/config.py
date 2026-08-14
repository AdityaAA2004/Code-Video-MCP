"""Runtime settings for the server.

Every hard ceiling the architecture doc calls for lives here as a named field
rather than as a magic number buried in a node: the scope file/token caps that
stop "whole repo" from blowing context, the capped retry count for the
validate/fix loop, model names for the two LLM calls, and the filesystem roots
for job workspaces and rendered output.

Settings are read once at server startup and threaded through explicitly
(``create_server`` -> job runner -> graph state config) rather than read from a
module-level global, so tests can construct a ``Settings`` with tiny caps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Transport = Literal["stdio", "http", "sse"]


@dataclass(frozen=True, slots=True)
class ScopeSettings:
    """Ceilings applied by ``resolve_scope`` and ``gather_context``."""

    max_files: int
    """Hard cap on files considered after ranking, for whole-repo scopes."""

    max_total_bytes: int
    """Hard cap on bytes read across all selected files."""

    max_context_tokens: int
    """Approximate token budget for ``context_chunks`` handed to the LLM."""

    excluded_dir_names: frozenset[str]
    """Directory names pruned during the walk (node_modules, .git, dist, ...)."""

    excluded_glob_patterns: tuple[str, ...]
    """Path globs pruned during the walk (lockfiles, minified bundles, ...)."""

    ranking_strategy: Literal["size", "import_centrality", "hybrid"]
    """How the top-N files are chosen when a repo exceeds ``max_files``."""


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Model selection for the two generative nodes and the repair node."""

    storyboard_model: str
    codegen_model: str
    fix_model: str
    max_output_tokens: int
    temperature: float


@dataclass(frozen=True, slots=True)
class RenderSettings:
    """Everything about turning generated TSX into an MP4."""

    scaffold_dir: Path
    """Source of the checked-in Remotion project copied per job."""

    workspace_root: Path
    """Parent dir under which each job gets its own working directory."""

    output_root: Path
    """Where finished MP4s land (may be served over HTTP)."""

    composition_id: str
    """Remotion composition id passed to ``npx remotion render``."""

    node_binary: str
    package_manager: Literal["npm", "pnpm", "yarn", "bun"]
    typecheck_timeout_seconds: float
    render_timeout_seconds: float
    max_fix_retries: int
    """Cap for the validate_syntax <-> fix_errors loop before failing the job."""


@dataclass(frozen=True, slots=True)
class JobSettings:
    """Async job store and lifecycle policy."""

    store_backend: Literal["memory", "sqlite"]
    sqlite_path: Path | None
    max_concurrent_jobs: int
    workspace_ttl_seconds: float
    """How long a completed job's workspace survives before cleanup."""


@dataclass(frozen=True, slots=True)
class DeliverySettings:
    """How the finished video is handed back to a host that cannot inline it."""

    serve_over_http: bool
    static_host: str
    static_port: int
    public_base_url: str | None


@dataclass(frozen=True, slots=True)
class Settings:
    """Top-level settings object passed to ``create_server``."""

    transport: Transport
    host: str
    port: int
    scope: ScopeSettings
    llm: LLMSettings
    render: RenderSettings
    jobs: JobSettings
    delivery: DeliverySettings
    allow_elicitation: bool = True
    """Master switch; per-call support is still probed, never assumed."""

    extra: dict[str, str] = field(default_factory=dict)


def default_settings() -> Settings:
    """Return the built-in defaults used when no config file/env is present.

    Concrete default values are a product decision, not scaffolding — they are
    filled in when the caps in the architecture doc are pinned down.
    """
    raise NotImplementedError


def load_settings(config_path: Path | None = None) -> Settings:
    """Build ``Settings`` from defaults, an optional TOML file, and env vars.

    Precedence (lowest to highest): ``default_settings()``, ``config_path``,
    ``CODE_EXPLAIN_VIDEO_*`` environment variables.
    """
    raise NotImplementedError
