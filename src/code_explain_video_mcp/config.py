"""Runtime settings for the server process.

Every hard ceiling the architecture calls for lives here as a named field rather
than as a magic number buried in a node. Settings are built once at startup and
threaded through explicitly (``create_server`` -> job runner -> graph nodes)
instead of read from a module-level global, so tests can build a ``Settings``
with tiny caps.

Precedence, lowest to highest: :func:`default_settings`, an optional TOML file
passed to :func:`load_settings`, then ``CODE_EXPLAIN_VIDEO_*`` env vars. Nothing
ever searches for a config file.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from code_explain_video_mcp.errors import ConfigurationError

Transport = Literal["stdio", "http", "sse"]

ENV_PREFIX = "CODE_EXPLAIN_VIDEO_"

PACKAGE_ROOT = Path(__file__).resolve().parent

SECTIONS = ("scope", "llm", "render", "jobs", "delivery")
"""Nested settings groups; also the table names in a TOML config file."""


@dataclass(frozen=True, slots=True)
class ScopeSettings:
    """Ceilings and exclusions applied by ``resolve_scope``."""

    max_files: int
    max_total_bytes: int
    excluded_dir_names: frozenset[str]
    excluded_glob_patterns: tuple[str, ...]
    ranking_strategy: Literal["size", "import_centrality", "hybrid"]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Model selection for the generative nodes."""

    storyboard_model: str
    codegen_model: str


@dataclass(frozen=True, slots=True)
class RenderSettings:
    """Everything about turning generated TSX into an MP4."""

    scaffold_dir: Path
    """The checked-in Remotion project, copied into each job's workspace."""

    workspace_root: Path
    output_root: Path
    composition_id: str
    """Composition passed to ``npx remotion render``."""

    max_fix_retries: int
    """Cap for the validate_syntax <-> fix_errors loop before failing the job."""


@dataclass(frozen=True, slots=True)
class JobSettings:
    """Async job store and lifecycle policy."""

    store_backend: Literal["memory", "sqlite"]
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

    Leave it ``None`` on a general-purpose server: it outranks the cwd rungs of
    :func:`~code_explain_video_mcp.tools.elicitation.resolve_root` on *every*
    call, so pinning it would make "explain that other repo" silently explain
    the pinned one. With ``None``, an unresolvable root is a loud error.
    """

    dry_run: bool = True
    """Run the graph with placeholder stage bodies instead of real work.

    Every node still executes, logs, and advances the job store, so the whole
    async job lifecycle is exercised end to end — but no LLM is called, no
    ``tsc`` runs, and no video is rendered. Defaults to ``True`` because those
    stage bodies are not implemented yet; flip it to ``False`` (or set
    ``CODE_EXPLAIN_VIDEO_DRY_RUN=0``) as each one lands. A node with no real
    implementation raises ``NotImplementedError`` rather than faking a result.
    """


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


def default_settings() -> Settings:
    """Return the built-in defaults used when no config file or env var is set.

    The caps are deliberately concrete: ``resolve_scope`` refuses to be
    best-effort, so "whole repo" is bounded here at 60 files / 2 MiB rather than
    at the call site.
    """
    # Under the user's cache dir, not the repo, so generated artifacts never end
    # up staged into a git index by accident.
    state = Path.home() / ".cache" / "code-explain-video-mcp"
    return Settings(
        transport="stdio",
        host="127.0.0.1",
        port=8000,
        scope=ScopeSettings(
            max_files=60,
            max_total_bytes=2 * 1024 * 1024,
            excluded_dir_names=DEFAULT_EXCLUDED_DIRS,
            excluded_glob_patterns=DEFAULT_EXCLUDED_GLOBS,
            ranking_strategy="hybrid",
        ),
        llm=LLMSettings(
            storyboard_model="claude-opus-5",
            codegen_model="claude-opus-5",
        ),
        render=RenderSettings(
            scaffold_dir=PACKAGE_ROOT / "remotion" / "scaffold",
            workspace_root=state / "workspaces",
            output_root=state / "output",
            composition_id="Explainer",
            max_fix_retries=3,
        ),
        jobs=JobSettings(
            store_backend="memory",
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


_SCALARS = (str, int, float, bool, Path)
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _base_type(annotation: Any) -> Any:
    """Unwrap ``X | None`` to ``X``; anything else is returned unchanged."""
    if get_origin(annotation) in (Union, UnionType):
        return next(arg for arg in get_args(annotation) if arg is not type(None))
    return annotation


def _overridable_fields(cls: type) -> Iterator[tuple[str, Any]]:
    """Yield ``(name, type)`` for the fields a TOML key or env var may set.

    Only scalars are overridable. The exclusion collections are settable in code
    alone, which is why they are filtered out here.
    """
    hints = get_type_hints(cls)
    for dataclass_field in fields(cls):
        annotation = hints[dataclass_field.name]
        if get_origin(annotation) is Literal or _base_type(annotation) in _SCALARS:
            yield dataclass_field.name, annotation


def _convert(raw: object, annotation: Any, where: str) -> Any:
    """Turn a TOML value or env string into what the field's type declares."""
    text = str(raw).strip()

    if get_origin(annotation) is Literal:
        allowed = get_args(annotation)
        if text.lower() not in allowed:
            raise ConfigurationError(f"{where} must be one of {allowed}, got {raw!r}")
        return text.lower()

    target = _base_type(annotation)
    if target is bool:
        return text.lower() in _TRUTHY
    if target is Path:
        return Path(text).expanduser()
    try:
        return target(text)
    except ValueError as exc:
        raise ConfigurationError(f"{where}: cannot read {raw!r} as {target.__name__}") from exc


def _env_var(section: str | None, name: str) -> str:
    """Return the env var that overrides one field (``..._RENDER_MAX_FIX_RETRIES``)."""
    parts = (name,) if section is None else (section, name)
    return ENV_PREFIX + "_".join(parts).upper()


def _read_toml(path: Path) -> dict[str, Any]:
    """Parse a config file, turning every failure into a ``ConfigurationError``."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ConfigurationError(f"Config file not found: {path}")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Could not read config {path}: {exc}") from exc


def load_settings(config_path: Path | None = None) -> Settings:
    """Build ``Settings`` from defaults, an optional TOML file, and env vars.

    The TOML file mirrors the dataclass layout: one table per section
    (``[scope]``, ``[llm]``, ``[render]``, ``[jobs]``, ``[delivery]``) plus bare
    top-level keys for ``transport``/``host``/``port``.

    Raises:
        ConfigurationError: ``config_path`` is missing or unparseable, or a
            value cannot be read as its field's type.
    """
    settings = default_settings()
    data = _read_toml(config_path) if config_path is not None else {}

    for section in (None, *SECTIONS):
        group = settings if section is None else getattr(settings, section)
        from_file = data if section is None else data.get(section)
        table = from_file if isinstance(from_file, dict) else {}
        updates: dict[str, Any] = {}

        for name, annotation in _overridable_fields(type(group)):
            env_var = _env_var(section, name)
            raw = os.environ.get(env_var)
            if raw:
                updates[name] = _convert(raw, annotation, env_var)
            elif name in table:
                where = name if section is None else f"{section}.{name}"
                updates[name] = _convert(table[name], annotation, where)

        if updates:
            updated = replace(group, **updates)
            settings = updated if section is None else replace(settings, **{section: updated})

    if settings.render.max_fix_retries < 0:
        raise ConfigurationError("render.max_fix_retries must be >= 0")
    if settings.jobs.max_concurrent_jobs < 1:
        raise ConfigurationError("jobs.max_concurrent_jobs must be >= 1")
    return settings
