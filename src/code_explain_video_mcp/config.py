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

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, get_args

from code_explain_video_mcp.errors import ConfigurationError

Transport = Literal["stdio", "http", "sse"]

ENV_PREFIX = "CODE_EXPLAIN_VIDEO_"
"""Prefix for the environment overrides applied last in :func:`load_settings`."""

PACKAGE_ROOT = Path(__file__).resolve().parent


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

    default_root: Path | None = None
    """Repo root to use when a caller omits ``root``.

    This exists because a stdio server inherits its *host's* working directory,
    which is not reliably the repo the user is asking about. Setting
    ``CODE_EXPLAIN_VIDEO_DEFAULT_ROOT`` pins it for a server dedicated to one
    repository.

    Leave it ``None`` for a general-purpose server. It outranks the cwd rungs of
    :func:`~code_explain_video_mcp.tools.elicitation.resolve_root` and applies to
    *every* call that omits ``root``, so pinning it on a shared server would make
    "explain this other repo" silently explain the pinned one instead. With
    ``None``, an unresolvable root is a loud error, which is the safer default.
    """

    dry_run: bool = True
    """Run the graph with placeholder stage bodies instead of real work.

    Every node still executes, logs, and advances the job store, so the whole
    async job lifecycle — tool call, ``job_id``, polling, storyboard, terminal
    status — is exercised end to end. What the nodes do *not* do is call an LLM,
    run ``tsc``, or invoke the Remotion CLI.

    It defaults to ``True`` because those stage bodies are not implemented yet;
    flip it to ``False`` (or set ``CODE_EXPLAIN_VIDEO_DRY_RUN=0``) as each one
    lands. A node with no real implementation raises ``NotImplementedError``
    rather than silently producing a fake result when this is off.
    """

    extra: dict[str, str] = field(default_factory=dict)


DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
        "dist", "build", "out", "target", "coverage", "htmlcov", ".next", ".nuxt",
        "site-packages", "vendor", ".terraform", "checkpoints", ".DS_Store",
    }
)

DEFAULT_EXCLUDED_GLOBS: tuple[str, ...] = (
    "*.lock", "*-lock.json", "*.min.js", "*.min.css", "*.map",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.ico", "*.pdf",
    "*.zip", "*.tar", "*.gz", "*.mp4", "*.wav", "*.bin", "*.so", "*.dylib",
    "*.pyc", "*.ckpt", "*.pt", "*.pth", "*.h5", "*.parquet",
)


def _state_root() -> Path:
    """Base directory for workspaces and rendered output.

    Defaults under the user's cache dir rather than the repo so that generated
    artifacts never end up staged into a user's git index by accident.
    """
    override = os.environ.get(f"{ENV_PREFIX}STATE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".cache" / "code-explain-video-mcp"


def default_settings() -> Settings:
    """Return the built-in defaults used when no config file/env is present.

    The caps are deliberately concrete: ``resolve_scope`` refuses to be
    best-effort, so "whole repo" is bounded here at 60 files / 2 MiB / ~120k
    tokens rather than at the call site.
    """
    state = _state_root()
    return Settings(
        transport="stdio",
        host="127.0.0.1",
        port=8000,
        scope=ScopeSettings(
            max_files=60,
            max_total_bytes=2 * 1024 * 1024,
            max_context_tokens=120_000,
            excluded_dir_names=DEFAULT_EXCLUDED_DIRS,
            excluded_glob_patterns=DEFAULT_EXCLUDED_GLOBS,
            ranking_strategy="hybrid",
        ),
        llm=LLMSettings(
            storyboard_model="claude-opus-5",
            codegen_model="claude-opus-5",
            fix_model="claude-sonnet-5",
            max_output_tokens=16_000,
            temperature=0.2,
        ),
        render=RenderSettings(
            scaffold_dir=PACKAGE_ROOT / "remotion" / "scaffold",
            workspace_root=state / "workspaces",
            output_root=state / "output",
            composition_id="Explainer",
            node_binary="node",
            package_manager="npm",
            typecheck_timeout_seconds=180.0,
            render_timeout_seconds=1800.0,
            max_fix_retries=3,
        ),
        jobs=JobSettings(
            store_backend="memory",
            sqlite_path=None,
            max_concurrent_jobs=2,
            workspace_ttl_seconds=24 * 3600.0,
        ),
        delivery=DeliverySettings(
            serve_over_http=False,
            static_host="127.0.0.1",
            static_port=8801,
            public_base_url=None,
        ),
    )


# Env var name -> (settings section or None for top level, field name, coercion).
_ENV_FIELDS: dict[str, tuple[str | None, str, str]] = {
    "TRANSPORT": (None, "transport", "transport"),
    "HOST": (None, "host", "str"),
    "PORT": (None, "port", "int"),
    "ALLOW_ELICITATION": (None, "allow_elicitation", "bool"),
    "DRY_RUN": (None, "dry_run", "bool"),
    "DEFAULT_ROOT": (None, "default_root", "path"),
    "SCOPE_MAX_FILES": ("scope", "max_files", "int"),
    "SCOPE_MAX_TOTAL_BYTES": ("scope", "max_total_bytes", "int"),
    "SCOPE_MAX_CONTEXT_TOKENS": ("scope", "max_context_tokens", "int"),
    "LLM_STORYBOARD_MODEL": ("llm", "storyboard_model", "str"),
    "LLM_CODEGEN_MODEL": ("llm", "codegen_model", "str"),
    "LLM_FIX_MODEL": ("llm", "fix_model", "str"),
    "RENDER_SCAFFOLD_DIR": ("render", "scaffold_dir", "path"),
    "RENDER_WORKSPACE_ROOT": ("render", "workspace_root", "path"),
    "RENDER_OUTPUT_ROOT": ("render", "output_root", "path"),
    "RENDER_COMPOSITION_ID": ("render", "composition_id", "str"),
    "RENDER_MAX_FIX_RETRIES": ("render", "max_fix_retries", "int"),
    "RENDER_TIMEOUT_SECONDS": ("render", "render_timeout_seconds", "float"),
    "JOBS_MAX_CONCURRENT": ("jobs", "max_concurrent_jobs", "int"),
    "JOBS_WORKSPACE_TTL_SECONDS": ("jobs", "workspace_ttl_seconds", "float"),
    "DELIVERY_SERVE_OVER_HTTP": ("delivery", "serve_over_http", "bool"),
    "DELIVERY_STATIC_PORT": ("delivery", "static_port", "int"),
    "DELIVERY_PUBLIC_BASE_URL": ("delivery", "public_base_url", "str"),
}


def _coerce(raw: object, kind: str, where: str) -> Any:
    """Convert a TOML/env scalar into the type the dataclass field expects."""
    try:
        if kind == "str":
            return str(raw)
        if kind == "int":
            return int(raw)  # type: ignore[arg-type]
        if kind == "float":
            return float(raw)  # type: ignore[arg-type]
        if kind == "path":
            return Path(str(raw)).expanduser()
        if kind == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}
        if kind == "transport":
            value = str(raw).strip().lower()
            if value not in get_args(Transport):
                raise ValueError(f"must be one of {get_args(Transport)}")
            return value
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid value for {where}: {raw!r} ({exc})") from exc
    raise ConfigurationError(f"Unknown coercion {kind!r} for {where}")


def _apply(settings: Settings, section: str | None, name: str, value: Any) -> Settings:
    """Return a copy of ``settings`` with one (possibly nested) field replaced."""
    if section is None:
        return replace(settings, **{name: value})
    nested = replace(getattr(settings, section), **{name: value})
    return replace(settings, **{section: nested})


def load_settings(config_path: Path | None = None) -> Settings:
    """Build ``Settings`` from defaults, an optional TOML file, and env vars.

    Precedence (lowest to highest): ``default_settings()``, ``config_path``,
    ``CODE_EXPLAIN_VIDEO_*`` environment variables.

    The TOML file mirrors the dataclass layout — a top-level table per section
    (``[scope]``, ``[llm]``, ``[render]``, ``[jobs]``, ``[delivery]``) plus bare
    top-level keys for ``transport``/``host``/``port``.

    Raises:
        ConfigurationError: ``config_path`` is missing/unparseable, or a value
            cannot be coerced to its field's type.
    """
    settings = default_settings()

    if config_path is not None:
        path = Path(config_path).expanduser()
        if not path.is_file():
            raise ConfigurationError(f"Config file not found: {path}")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(f"Could not read config {path}: {exc}") from exc
        for _env_name, (section, name, kind) in _ENV_FIELDS.items():
            table = data if section is None else data.get(section, {})
            if isinstance(table, dict) and name in table:
                where = name if section is None else f"{section}.{name}"
                settings = _apply(settings, section, name, _coerce(table[name], kind, where))

    for env_name, (section, name, kind) in _ENV_FIELDS.items():
        raw = os.environ.get(f"{ENV_PREFIX}{env_name}")
        if raw is not None and raw != "":
            settings = _apply(settings, section, name, _coerce(raw, kind, ENV_PREFIX + env_name))

    if settings.render.max_fix_retries < 0:
        raise ConfigurationError("render.max_fix_retries must be >= 0")
    if settings.jobs.max_concurrent_jobs < 1:
        raise ConfigurationError("jobs.max_concurrent_jobs must be >= 1")
    return settings
