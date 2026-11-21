"""Tests for up-front planning: which videos get a sheet, decided before rendering."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PIL import Image

from vcsng.config import Settings
from vcsng.errors import UsageError
from vcsng.plan import Action, Input, build_plan, collect_inputs


def _settings(**kw) -> Settings:
    return Settings(format="jpeg", suffix="-ss", **kw)


@pytest.fixture
def tree(tmp_path) -> Path:
    """missing.mkv: no sheet; wide.mkv: 2100px; narrow.mkv: 300px; junk.mkv: not an image;
    dir.mkv: a directory where its sheet should be."""
    for name in ("missing", "wide", "narrow", "junk", "dir"):
        (tmp_path / f"{name}.mkv").write_bytes(b"")
    Image.new("RGB", (2100, 10)).save(tmp_path / "wide-ss.jpg", format="JPEG")
    Image.new("RGB", (300, 10)).save(tmp_path / "narrow-ss.jpg", format="JPEG")
    (tmp_path / "junk-ss.jpg").write_text("??")
    (tmp_path / "dir-ss.jpg").mkdir()
    return tmp_path


def _actions(plan) -> dict[str, Action]:
    return {job.video.stem: job.action for job in plan.jobs}


def test_collect_inputs_scans_dirs_and_passes_files(tree, caplog):
    single = tree / "elsewhere.mp4"
    with caplog.at_level(logging.INFO, logger="vcsng"):
        inputs = collect_inputs([single, tree], _settings(), recursive=True)
    assert inputs[0] == Input(single, scanned=False)
    assert {i.video.stem for i in inputs[1:]} == {"missing", "wide", "narrow", "junk", "dir"}
    assert all(i.scanned for i in inputs[1:])
    assert "found 5 videos" in caplog.text


def test_plan_default_keeps_any_valid_sheet(tree):
    s = _settings()
    plan = build_plan(collect_inputs([tree], s, recursive=True), s)
    assert _actions(plan) == {"missing": Action.NEW, "junk": Action.REPLACE_BAD}
    assert plan.up_to_date == 2  # wide + narrow
    assert [p.stem for p, _ in plan.failed] == ["dir"]
    assert all(job.out.parent == tree for job in plan.jobs)


def test_plan_min_width_regenerates_narrow(tree):
    s = _settings(min_width=2000)
    plan = build_plan(collect_inputs([tree], s, recursive=True), s)
    assert _actions(plan)["narrow"] is Action.REGENERATE
    assert "wide" not in _actions(plan)
    assert plan.up_to_date == 1


def test_plan_regenerate_includes_up_to_date(tree):
    s = _settings(regenerate=True)
    plan = build_plan(collect_inputs([tree], s, recursive=True), s)
    actions = _actions(plan)
    assert actions["wide"] is Action.REGENERATE
    assert actions["narrow"] is Action.REGENERATE
    assert plan.up_to_date == 0


def test_plan_named_file_always_generates_into_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video = tmp_path / "videos" / "a.mkv"
    s = _settings()
    plan = build_plan([Input(video, scanned=False)], s)
    assert [(j.video, j.out, j.action) for j in plan.jobs] == [
        (video, tmp_path / "a-ss.jpg", Action.NEW)
    ]


def test_plan_bad_template_is_a_usage_error(tree):
    s = _settings(output="{nope}.{ext}")
    with pytest.raises(UsageError):
        build_plan(collect_inputs([tree], s, recursive=True), s)
