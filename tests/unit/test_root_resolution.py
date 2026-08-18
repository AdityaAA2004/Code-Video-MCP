"""The root ladder must never silently guess wrong.

A stdio server inherits its host's working directory, so an omitted ``root``
used to mean "explain whatever directory Claude Code or Codex launched from".
These tests pin the behaviour that replaced it: infer only from real repo
markers, say so in the notes when inferring, and raise rather than guess.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from code_explain_video_mcp.errors import RootResolutionError
from code_explain_video_mcp.tools.elicitation import (
    find_repo_root,
    looks_like_repo,
    resolve_root,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A directory that looks like a checked-out repository."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "deep").mkdir()
    return tmp_path


@pytest.fixture
def bare(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory with no repo markers anywhere above it inside the tmp tree."""
    return tmp_path_factory.mktemp("bare")


def test_explicit_root_wins(repo: Path) -> None:
    decision = resolve_root(str(repo))
    assert decision.mode == "explicit"
    assert decision.root == repo.resolve()
    assert decision.notes == []


def test_explicit_root_outranks_configured_default(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    decision = resolve_root(str(repo), other)
    assert decision.root == repo.resolve()


def test_configured_default_used_when_root_omitted(repo: Path) -> None:
    decision = resolve_root(None, repo)
    assert decision.mode == "configured"
    assert decision.root == repo.resolve()


def test_cwd_used_when_it_is_a_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    decision = resolve_root(None)
    assert decision.mode == "cwd"
    assert decision.root == repo.resolve()
    # The user must be told the server chose for them.
    assert decision.notes and "No `root` was given" in decision.notes[0]


def test_walks_up_to_enclosing_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo / "src" / "deep")
    decision = resolve_root(None)
    assert decision.mode == "cwd_ancestor"
    assert decision.root == repo.resolve()
    assert decision.notes and "nearest enclosing one" in decision.notes[0]


def test_raises_rather_than_guessing(bare: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: no repo anywhere means refuse, not 'use cwd anyway'."""
    monkeypatch.chdir(bare)
    with pytest.raises(RootResolutionError) as excinfo:
        resolve_root(None)
    # The message has to tell the calling model what to do next.
    assert "root" in str(excinfo.value)
    assert "absolute path" in str(excinfo.value)


def test_missing_explicit_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RootResolutionError, match="does not exist"):
        resolve_root(str(tmp_path / "nope"))


def test_file_as_root_is_rejected(repo: Path) -> None:
    with pytest.raises(RootResolutionError, match="is a file, not a directory"):
        resolve_root(str(repo / "pyproject.toml"))


def test_explicit_non_repo_dir_is_allowed_but_flagged(bare: Path) -> None:
    """Explicit beats inference — but the caller still gets told it looks odd."""
    decision = resolve_root(str(bare))
    assert decision.mode == "explicit"
    assert decision.notes and "may not" in decision.notes[0]


def test_home_directory_is_a_walk_boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A stray manifest above $HOME must not turn into 'walk the whole home dir'."""
    fake_home = tmp_path / "home"
    (fake_home / "work" / "nested").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    # No markers anywhere under fake_home.
    assert find_repo_root(fake_home / "work" / "nested") is None


def test_looks_like_repo_detects_markers(tmp_path: Path) -> None:
    assert not looks_like_repo(tmp_path)
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert looks_like_repo(tmp_path)


def test_root_is_resolved_absolute(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative roots are made absolute so nothing downstream depends on cwd."""
    monkeypatch.chdir(repo.parent)
    decision = resolve_root(repo.name)
    assert decision.root.is_absolute()
    assert decision.root == repo.resolve()
    assert os.path.isabs(str(decision.root))
