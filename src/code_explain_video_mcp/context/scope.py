"""Turning "this file" / "this folder" / "the whole repo" into a bounded file list.

The architecture doc is explicit that a hard ceiling must be decided up front,
so the cap is not optional or best-effort: the walk prunes known-noise
directories, ranks what survives, and truncates to ``ScopeSettings.max_files``
and ``max_total_bytes``. Truncation is recorded on the result so the tool layer
can tell the user their repo was sampled rather than covered.

Ranking exists because "top N by size" is a poor proxy for "N most explanatory
files" — import centrality (how many other selected files import this one) is
the better default for a repo-level overview.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from code_explain_video_mcp.config import ScopeSettings
from code_explain_video_mcp.errors import ScopeResolutionError
from code_explain_video_mcp.logging_conf import get_logger

logger = get_logger("context.scope")

LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "jsx", ".mjs": "javascript", ".cjs": "javascript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".swift": "swift",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".scala": "scala", ".sh": "bash", ".zsh": "bash",
    ".sql": "sql", ".md": "markdown", ".rst": "rst", ".toml": "toml", ".yaml": "yaml",
    ".yml": "yaml", ".json": "json", ".html": "html", ".css": "css", ".scss": "scss",
}

ENTRYPOINT_NAMES: frozenset[str] = frozenset(
    {
        "__main__.py", "main.py", "app.py", "cli.py", "server.py", "index.ts",
        "index.tsx", "index.js", "main.ts", "main.go", "main.rs", "lib.rs",
    }
)

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)|import\s+([.\w]+))", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""(?:from|import|require\()\s*['"]([^'"]+)['"]""")

VCS_MARKERS: frozenset[str] = frozenset({".git", ".hg", ".svn", ".jj"})
"""Directories that identify a checkout root unambiguously."""

PROJECT_MARKERS: frozenset[str] = frozenset(
    {
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "package.json", "deno.json", "Cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
        "CMakeLists.txt", "mix.exs", "Package.swift",
    }
)
"""Manifests that identify a project root when there is no VCS directory."""

MAX_ROOT_WALK_DEPTH = 25
"""Bound on the upward search, so a pathological path cannot spin."""


@dataclass(frozen=True, slots=True)
class SelectedFile:
    """One file that made the cut, with the score that got it there."""

    path: Path
    """Absolute path on disk."""

    relative_path: str
    """Repo-relative path; this is what appears in snippets and narration."""

    size_bytes: int
    language: str | None
    score: float
    """Ranking score; interpretation depends on ``ranking_strategy``."""


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    """The bounded answer to "what are we explaining?"."""

    root: Path
    requested: str | None
    """Raw scope string as given, or ``None`` for whole-repo."""

    is_whole_repo: bool
    files: list[SelectedFile]
    total_bytes: int
    truncated: bool
    """True when the caps dropped files that would otherwise have been included."""

    dropped_file_count: int
    summary: str
    """One-line human description, echoed in the tool response."""

    notes: list[str] = field(default_factory=list)


def repo_markers_at(path: Path) -> list[str]:
    """Return the VCS/manifest markers present directly in ``path``.

    Empty means "this directory does not look like the root of anything".
    """
    try:
        names = {entry.name for entry in path.iterdir()}
    except (OSError, PermissionError):
        return []
    return sorted((names & VCS_MARKERS) | (names & PROJECT_MARKERS))


def looks_like_repo(path: Path) -> bool:
    """Whether ``path`` is plausibly the root of a codebase."""
    return bool(repo_markers_at(path))


def find_repo_root(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for a repo root; ``None`` if there is none.

    Two boundaries stop the walk, and both exist to prevent a catastrophic
    over-reach: the user's home directory and the filesystem root. A stray
    ``package.json`` in ``$HOME`` must never turn "explain the whole repo" into
    "walk the user's entire home directory".
    """
    try:
        current = Path(start).expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    home = Path.home().resolve()
    for _ in range(MAX_ROOT_WALK_DEPTH):
        if current == current.parent:  # filesystem root
            return None
        if current == home:
            # Check home itself but never above it.
            return current if looks_like_repo(current) else None
        if looks_like_repo(current):
            return current
        current = current.parent
    return None


def resolve_scope(
    root: Path,
    requested: str | None,
    settings: ScopeSettings,
) -> ResolvedScope:
    """Resolve a path/glob (or whole repo) into a capped, ranked file list.

    Three shapes of ``requested`` are accepted: a single file, a directory
    (walked recursively), and a glob. ``None`` means the whole repo.

    Raises:
        ScopeResolutionError: ``requested`` matches nothing, or matches only
            files excluded by the noise filters.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ScopeResolutionError(f"Repo root is not a directory: {root}")

    is_whole_repo = requested is None
    if is_whole_repo:
        candidates = walk_repo(root, settings)
    else:
        candidates = _resolve_requested(root, str(requested), settings)

    if not candidates:
        target = "the repository" if is_whole_repo else f"{requested!r}"
        raise ScopeResolutionError(
            f"Nothing to explain in {target}: no files matched, or every match "
            "was excluded as build output, vendored code, or a binary."
        )

    ranked = rank_files(candidates, root, settings)

    selected: list[SelectedFile] = []
    total_bytes = 0
    for candidate in ranked:
        if len(selected) >= settings.max_files:
            break
        if total_bytes + candidate.size_bytes > settings.max_total_bytes and selected:
            break
        selected.append(candidate)
        total_bytes += candidate.size_bytes

    dropped = len(ranked) - len(selected)
    truncated = dropped > 0

    notes: list[str] = []
    if truncated:
        notes.append(
            f"Scope was capped: {len(selected)} of {len(ranked)} matching files were "
            f"used ({dropped} dropped by the {settings.max_files}-file / "
            f"{settings.max_total_bytes // 1024} KiB ceiling). The video samples the "
            "codebase rather than covering it exhaustively."
        )

    where = "the whole repository" if is_whole_repo else str(requested)
    summary = (
        f"{len(selected)} file(s), {total_bytes / 1024:.0f} KiB, from {where}"
        + (f" (capped from {len(ranked)})" if truncated else "")
    )

    logger.info("resolved scope: %s", summary)
    return ResolvedScope(
        root=root,
        requested=requested,
        is_whole_repo=is_whole_repo,
        files=selected,
        total_bytes=total_bytes,
        truncated=truncated,
        dropped_file_count=dropped,
        summary=summary,
        notes=notes,
    )


def _resolve_requested(root: Path, requested: str, settings: ScopeSettings) -> list[Path]:
    """Expand an explicit scope string into candidate files."""
    raw = Path(requested).expanduser()
    target = raw if raw.is_absolute() else (root / raw)

    if target.is_file():
        return [] if is_excluded(target, root, settings) else [target]
    if target.is_dir():
        return walk_repo(target, settings)

    matches = sorted(root.glob(requested))
    files: list[Path] = []
    for match in matches:
        if match.is_dir():
            files.extend(walk_repo(match, settings))
        elif match.is_file() and not is_excluded(match, root, settings):
            files.append(match)
    if not files and not matches:
        raise ScopeResolutionError(
            f"Scope {requested!r} does not exist under {root} and matches no files."
        )
    return files


def walk_repo(root: Path, settings: ScopeSettings) -> list[Path]:
    """Walk ``root``, pruning excluded directories and glob patterns as it goes.

    Pruning happens during traversal, not after, so ``node_modules`` is never
    descended into.
    """
    found: list[Path] = []
    stack = [Path(root)]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in settings.excluded_dir_names and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.is_file() and not is_excluded(entry, root, settings):
                found.append(entry)
    return sorted(found)


def is_excluded(path: Path, root: Path, settings: ScopeSettings) -> bool:
    """Whether a path is noise: vendored deps, VCS, build output, lockfiles, binaries."""
    if any(part in settings.excluded_dir_names for part in path.parts):
        return True
    if any(part.startswith(".") for part in path.parts[:-1] if part not in (".", "..")):
        return True
    name = path.name
    if name.startswith("."):
        return True
    if any(fnmatch.fnmatch(name, pattern) for pattern in settings.excluded_glob_patterns):
        return True
    if detect_language(path) is None:
        return True
    try:
        if path.stat().st_size == 0:
            return True
    except OSError:
        return True
    return False


def rank_files(paths: list[Path], root: Path, settings: ScopeSettings) -> list[SelectedFile]:
    """Score and sort candidates by the configured ranking strategy.

    ``hybrid`` — the default — is centrality-dominant with a small size term, so
    a widely-imported 40-line core module outranks a 900-line generated file.
    """
    centrality = (
        import_centrality(paths, root)
        if settings.ranking_strategy in ("import_centrality", "hybrid")
        else {}
    )
    sizes = {p: _safe_size(p) for p in paths}
    max_size = max(sizes.values(), default=1) or 1
    max_central = max(centrality.values(), default=1.0) or 1.0

    selected: list[SelectedFile] = []
    for path in paths:
        size_score = sizes[path] / max_size
        central_score = centrality.get(path, 0.0) / max_central
        entry_bonus = 0.25 if path.name in ENTRYPOINT_NAMES else 0.0

        if settings.ranking_strategy == "size":
            score = size_score
        elif settings.ranking_strategy == "import_centrality":
            score = central_score + entry_bonus
        else:
            score = 0.7 * central_score + 0.3 * size_score + entry_bonus

        selected.append(
            SelectedFile(
                path=path,
                relative_path=_relative(path, root),
                size_bytes=sizes[path],
                language=detect_language(path),
                score=round(score, 6),
            )
        )
    selected.sort(key=lambda f: (-f.score, f.relative_path))
    return selected


def import_centrality(paths: list[Path], root: Path) -> dict[Path, float]:
    """Score each file by how many other candidates import it.

    A cheap static pass (regex over import statements), not a real dependency
    graph — enough to float entrypoints and core modules to the top. Matching is
    by module *stem*, which over-counts common names like ``utils`` but is
    stable and costs one read per file.
    """
    by_stem: dict[str, list[Path]] = {}
    for path in paths:
        by_stem.setdefault(path.stem, []).append(path)

    scores: dict[Path, float] = dict.fromkeys(paths, 0.0)
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        referenced: set[str] = set()
        for match in _PY_IMPORT_RE.finditer(source):
            module = match.group(1) or match.group(2) or ""
            referenced.update(part for part in module.split(".") if part)
        for match in _JS_IMPORT_RE.finditer(source):
            referenced.add(Path(match.group(1)).stem)

        for stem in referenced:
            for target in by_stem.get(stem, ()):
                if target != path:
                    scores[target] += 1.0
    return scores


def detect_language(path: Path) -> str | None:
    """Map a file extension to a syntax-highlighter language id.

    ``None`` means "not source we can usefully show on screen", which is also
    how :func:`is_excluded` filters binaries and data files.
    """
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def _safe_size(path: Path) -> int:
    """File size in bytes, or 0 if it vanished mid-walk."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _relative(path: Path, root: Path) -> str:
    """Repo-relative path string, falling back to the absolute path."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
