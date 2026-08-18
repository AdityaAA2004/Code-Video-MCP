"""Turning "this file" / "this folder" / "the whole repo" into a bounded file list.

The cap is not best-effort: the walk prunes known-noise directories, ranks what
survives, and truncates to ``ScopeSettings.max_files`` and ``max_total_bytes``.
Truncation is recorded on the result so the tool layer can tell the user their
repo was sampled rather than covered.

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

RANKING_WEIGHTS: dict[str, tuple[float, float, float]] = {
    # strategy -> (centrality weight, size weight, entrypoint bonus)
    "size": (0.0, 1.0, 0.0),
    "import_centrality": (1.0, 0.0, 0.25),
    "hybrid": (0.7, 0.3, 0.25),
}
"""``hybrid`` — the default — is centrality-dominant with a small size term, so
a widely-imported 40-line core module outranks a 900-line generated file."""

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)|import\s+([.\w]+))", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""(?:from|import|require\()\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True, slots=True)
class SelectedFile:
    """One file that made the cut, with the score that got it there.

    ``relative_path`` is repo-relative and is what appears in snippets and
    narration; ``score`` is only comparable within one resolution.
    """

    path: Path
    relative_path: str
    size_bytes: int
    language: str | None
    score: float


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    """The bounded answer to "what are we explaining?".

    ``requested`` is the raw scope string as given, ``None`` for whole-repo.
    ``summary`` is the one-line description echoed back in the tool response.
    """

    root: Path
    requested: str | None
    files: list[SelectedFile]
    total_bytes: int
    dropped_file_count: int
    summary: str
    notes: list[str] = field(default_factory=list)

    @property
    def is_whole_repo(self) -> bool:
        return self.requested is None

    @property
    def truncated(self) -> bool:
        """True when the caps dropped files that would otherwise be included."""
        return self.dropped_file_count > 0


def resolve_scope(
    root: Path,
    requested: str | None,
    settings: ScopeSettings,
) -> ResolvedScope:
    """Resolve a file, directory, or glob (``None`` = whole repo) into a capped list.

    Raises:
        ScopeResolutionError: ``requested`` matches nothing, or matches only
            files excluded by the noise filters.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ScopeResolutionError(f"Repo root is not a directory: {root}")

    if requested is None:
        candidates = walk_repo(root, settings)
    else:
        candidates = _resolve_requested(root, str(requested), settings)

    if not candidates:
        target = "the repository" if requested is None else repr(requested)
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
        if selected and total_bytes + candidate.size_bytes > settings.max_total_bytes:
            break
        selected.append(candidate)
        total_bytes += candidate.size_bytes

    dropped = len(ranked) - len(selected)
    notes: list[str] = []
    if dropped:
        notes.append(
            f"Scope was capped: {len(selected)} of {len(ranked)} matching files were "
            f"used ({dropped} dropped by the {settings.max_files}-file / "
            f"{settings.max_total_bytes // 1024} KiB ceiling). The video samples the "
            "codebase rather than covering it exhaustively."
        )

    where = "the whole repository" if requested is None else str(requested)
    summary = (
        f"{len(selected)} file(s), {total_bytes / 1024:.0f} KiB, from {where}"
        + (f" (capped from {len(ranked)})" if dropped else "")
    )

    logger.info("resolved scope: %s", summary)
    return ResolvedScope(
        root=root,
        requested=requested,
        files=selected,
        total_bytes=total_bytes,
        dropped_file_count=dropped,
        summary=summary,
        notes=notes,
    )


def _resolve_requested(root: Path, requested: str, settings: ScopeSettings) -> list[Path]:
    """Expand an explicit scope string — a file, a directory, or a glob."""
    raw = Path(requested).expanduser()
    target = raw if raw.is_absolute() else (root / raw)

    if target.is_file():
        return [] if is_excluded(target, root, settings) else [target]
    if target.is_dir():
        return walk_repo(target, settings)

    matches = sorted(root.glob(requested))
    if not matches:
        raise ScopeResolutionError(
            f"Scope {requested!r} does not exist under {root} and matches no files."
        )

    files: list[Path] = []
    for match in matches:
        if match.is_dir():
            files.extend(walk_repo(match, settings))
        elif match.is_file() and not is_excluded(match, root, settings):
            files.append(match)
    return files


def walk_repo(root: Path, settings: ScopeSettings) -> list[Path]:
    """Walk ``root``, pruning excluded and dot directories during traversal.

    Pruning happens while descending, not after, so ``node_modules`` is never
    entered in the first place.
    """
    found: list[Path] = []
    stack = [Path(root)]
    while stack:
        try:
            entries = sorted(stack.pop().iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not entry.name.startswith(".") and entry.name not in settings.excluded_dir_names:
                    stack.append(entry)
            elif entry.is_file() and not is_excluded(entry, root, settings):
                found.append(entry)
    return sorted(found)


def is_excluded(path: Path, root: Path, settings: ScopeSettings) -> bool:
    """Whether a path is noise: vendored deps, VCS, build output, lockfiles, binaries.

    Only the part of the path *below* ``root`` is inspected, so a repo that
    happens to live under a dotted directory is not excluded wholesale.
    """
    inside = path.relative_to(root) if path.is_relative_to(root) else path
    if any(
        part.startswith(".") or part in settings.excluded_dir_names for part in inside.parts
    ):
        return True
    if any(fnmatch.fnmatch(path.name, pattern) for pattern in settings.excluded_glob_patterns):
        return True
    return detect_language(path) is None or _safe_size(path) == 0


def rank_files(paths: list[Path], root: Path, settings: ScopeSettings) -> list[SelectedFile]:
    """Score and sort candidates by the configured ranking strategy."""
    centrality_weight, size_weight, entrypoint_bonus = RANKING_WEIGHTS[settings.ranking_strategy]
    centrality = import_centrality(paths, root) if centrality_weight else {}
    sizes = {path: _safe_size(path) for path in paths}
    max_size = max(sizes.values(), default=1) or 1
    max_centrality = max(centrality.values(), default=1.0) or 1.0

    ranked: list[SelectedFile] = []
    for path in paths:
        score = (
            centrality_weight * (centrality.get(path, 0.0) / max_centrality)
            + size_weight * (sizes[path] / max_size)
            + (entrypoint_bonus if path.name in ENTRYPOINT_NAMES else 0.0)
        )
        ranked.append(
            SelectedFile(
                path=path,
                relative_path=str(path.relative_to(root))
                if path.is_relative_to(root)
                else str(path),
                size_bytes=sizes[path],
                language=detect_language(path),
                score=round(score, 6),
            )
        )
    ranked.sort(key=lambda f: (-f.score, f.relative_path))
    return ranked


def import_centrality(paths: list[Path], root: Path) -> dict[Path, float]:
    """Score each file by how many other candidates import it.

    A cheap regex pass, not a real dependency graph — enough to float
    entrypoints and core modules to the top. Matching is by module *stem*, which
    over-counts common names like ``utils`` but costs one read per file.
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
    """Highlighter language id for a file extension.

    ``None`` means "not source we can usefully show on screen", which is also
    how :func:`is_excluded` filters binaries and data files.
    """
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def _safe_size(path: Path) -> int:
    """File size in bytes, or 0 if it is unreadable or vanished mid-walk."""
    try:
        return path.stat().st_size
    except OSError:
        return 0
