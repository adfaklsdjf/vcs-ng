"""Tests for .github/scripts/release_plan.py (the CI release planner)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "release_plan.py"
_spec = importlib.util.spec_from_file_location("release_plan", _PATH)
rp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rp  # dataclasses look the module up while it loads
_spec.loader.exec_module(rp)

C = rp.Commit


@pytest.mark.parametrize(
    "subject, kind, description",
    [
        ("feat: add color", "feat", "Add color"),
        ("feat(sheet)!: new layout", "feat", "New layout"),
        ("Fix: case doesn't matter", "fix", "Case doesn't matter"),
        ("docs: tweak README", None, "docs: tweak README"),
        ("Make it faster", None, "Make it faster"),
        ("feat:", "feat", "feat:"),
        ("feature: not a prefix we know", None, "feature: not a prefix we know"),
    ],
)
def test_commit_classification(subject, kind, description):
    c = C("abc1234def", subject)
    assert c.kind == kind
    assert c.description == description


def test_next_version_patch_by_default():
    commits = [C("a", "Sloppy message"), C("b", "fix: thing"), C("c", "docs: x")]
    assert rp.next_version((1, 0, 6), commits, set()) == (1, 0, 7)


def test_next_version_minor_on_feat():
    commits = [C("a", "fix: thing"), C("b", "feat: shiny")]
    assert rp.next_version((1, 0, 6), commits, set()) == (1, 1, 0)


def test_next_version_without_tags_and_skipping_taken():
    assert rp.next_version(None, [], set()) == (0, 0, 1)
    assert rp.next_version((1, 0, 6), [], {(1, 0, 7), (1, 0, 8)}) == (1, 0, 9)


def test_parse_tag():
    assert rp.parse_tag("v1.2.3") == (1, 2, 3)
    assert rp.parse_tag("v1.2") is None
    assert rp.parse_tag("v1.2.3-rc1") is None


def test_render_notes_groups_and_links():
    commits = [C("1111111aaa", "Tidy up"), C("2222222bbb", "fix: crash"), C("3333333ccc", "feat: color")]
    notes = rp.render_notes(commits, "v1.0.6", "v1.1.0", "https://github.com/o/r")
    assert notes.index("## Features") < notes.index("## Fixes") < notes.index("## Other changes")
    assert "- Color (3333333)" in notes
    assert "- Tidy up (1111111)" in notes
    assert notes.rstrip().endswith("https://github.com/o/r/compare/v1.0.6...v1.1.0")


# --- against a real git repo -----------------------------------------------------


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    monkeypatch.chdir(tmp_path)

    def commit(msg):
        run("commit", "-q", "--allow-empty", "-m", msg)

    def tag(name):
        run("tag", name)

    return commit, tag


def test_plan_untagged_repo(repo):
    commit, _ = repo
    commit("initial")
    tag, create, prev, commits = rp.plan()
    assert (tag, create, prev, len(commits)) == ("v0.0.1", True, None, 1)


def test_plan_bumps_from_latest_tag(repo):
    commit, tag = repo
    commit("one")
    tag("v1.0.5")
    tag("not-a-release")
    commit("two")
    tag("v1.0.6")
    commit("feat: three")
    commit("whatever")
    assert rp.plan()[:3] == ("v1.1.0", True, "v1.0.6")


def test_plan_respects_hand_pushed_tag(repo):
    commit, tag = repo
    commit("one")
    tag("v1.0.6")
    commit("two")
    tag("v2.0.0")
    tag_, create, prev, commits = rp.plan()
    assert (tag_, create, prev) == ("v2.0.0", False, "v1.0.6")
    assert [c.subject for c in commits] == ["two"]
