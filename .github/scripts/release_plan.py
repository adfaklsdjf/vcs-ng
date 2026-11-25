"""Decide what release (if any) the current commit gets, and write its notes.

Run by .github/workflows/release.yml on every push to main or of a v* tag:

- If HEAD already carries a vX.Y.Z tag (pushed by hand, or a re-run), that tag
  is the release; only the GitHub release may still need creating.
- Otherwise the next version is the highest vX.Y.Z tag in HEAD's history,
  bumped minor if any commit since then is a Conventional Commits `feat:`, and
  patch for everything else, including messages that follow no convention.

Never refuses: odd commit messages, missing tags and the like all still produce
a release. Writes `tag` and `create_tag` to $GITHUB_OUTPUT (or stdout) and the
release notes to the path given with --notes.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
TYPE_RE = re.compile(r"^\s*(\w+)(?:\([^)]*\))?!?\s*:\s*(.*)$")

SECTIONS = [("feat", "Features"), ("fix", "Fixes"), (None, "Other changes")]

Version = tuple[int, int, int]


@dataclass
class Commit:
    sha: str
    subject: str

    @property
    def kind(self) -> str | None:
        """'feat' or 'fix' if the subject says so (any case), else None."""
        m = TYPE_RE.match(self.subject)
        kind = m.group(1).lower() if m else None
        return kind if kind in ("feat", "fix") else None

    @property
    def description(self) -> str:
        """Subject without a feat/fix prefix, first letter capitalized."""
        text = TYPE_RE.match(self.subject).group(2).strip() if self.kind else ""
        return text[:1].upper() + text[1:] if text else self.subject.strip()


def parse_tag(tag: str) -> Version | None:
    m = TAG_RE.match(tag.strip())
    return tuple(int(g) for g in m.groups()) if m else None


def format_tag(v: Version) -> str:
    return "v{}.{}.{}".format(*v)


def next_version(last: Version | None, commits: list[Commit], taken: set[Version]) -> Version:
    """Minor bump if any commit is a feat, else patch; skip versions already tagged."""
    major, minor, patch = last or (0, 0, 0)
    if any(c.kind == "feat" for c in commits):
        candidate = (major, minor + 1, 0)
    else:
        candidate = (major, minor, patch + 1)
    while candidate in taken:  # e.g. a tag on another branch, or a raced run
        candidate = (candidate[0], candidate[1], candidate[2] + 1)
    return candidate


def render_notes(commits: list[Commit], prev_tag: str | None, tag: str, repo_url: str | None) -> str:
    lines: list[str] = []
    for kind, title in SECTIONS:
        group = [c for c in commits if c.kind == kind]
        if not group:
            continue
        lines.append(f"## {title}\n")
        lines += [f"- {c.description} ({c.sha[:7]})" for c in group]
        lines.append("")
    if not commits:
        lines.append("No changes since the previous release.\n")
    if repo_url and prev_tag:
        lines.append(f"**Full changelog**: {repo_url}/compare/{prev_tag}...{tag}")
    return "\n".join(lines).rstrip() + "\n"


# --- git ----------------------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def release_tags(*args: str) -> dict[str, Version]:
    """vX.Y.Z tags selected by `git tag <args>`, mapped to their versions."""
    out = {}
    for line in git("tag", "--list", "v*", *args).splitlines():
        v = parse_tag(line)
        if v is not None:
            out[line.strip()] = v
    return out


def commits_between(prev_tag: str | None, head: str = "HEAD") -> list[Commit]:
    rev = f"{prev_tag}..{head}" if prev_tag else head
    out = git("log", "--no-merges", "--format=%H%x1f%s", rev)
    return [Commit(*line.split("\x1f", 1)) for line in out.splitlines() if "\x1f" in line]


def latest(tags: dict[str, Version]) -> str | None:
    return max(tags, key=tags.get) if tags else None


def plan() -> tuple[str, bool, str | None, list[Commit]]:
    """(tag, create_tag, previous tag, commits since it) for HEAD."""
    on_head = release_tags("--points-at", "HEAD")
    reachable = release_tags("--merged", "HEAD")
    if on_head:
        tag = latest(on_head)
        prev = latest({t: v for t, v in reachable.items() if t not in on_head})
        return tag, False, prev, commits_between(prev)
    prev = latest(reachable)
    commits = commits_between(prev)
    taken = set(release_tags().values())
    tag = format_tag(next_version(reachable.get(prev), commits, taken))
    return tag, True, prev, commits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notes", required=True, help="where to write the release notes")
    args = ap.parse_args()

    tag, create, prev, commits = plan()
    repo_url = None
    if os.environ.get("GITHUB_REPOSITORY"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo_url = f"{server}/{os.environ['GITHUB_REPOSITORY']}"
    with open(args.notes, "w") as f:
        f.write(render_notes(commits, prev, tag, repo_url))

    outputs = f"tag={tag}\ncreate_tag={'true' if create else 'false'}\n"
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(outputs)
    sys.stdout.write(outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
