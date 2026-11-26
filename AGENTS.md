# New asks from Brian

(none pending)

When this section isn't empty, raise the items with Brian early in a session if Brian hasn't brought them up first, and work them in or ask how to handle them. Remove an item once it's done or dropped.

# Who this is for

vcs-ng is Brian's personal tool. The repo is public, but it has no known users, so optimize for Brian alone: backward compatibility, migration paths and other people's setups don't matter unless that changes and Brian says so. All else being equal, prefer the more professional approach — but all else is rarely equal, so weigh its cost (complexity, dependencies, ceremony) honestly against what it buys a one-person project.

# Code quality

Brian is vibe-coding this and mostly doesn't read the code, but it should stay well-architected and maintainable. The risk to watch for: nuanced or almost-conflicting requests piling up, met by an agreeable agent, until the code contorts to satisfy all of them. Some imperfection is normal, but when a request would make the code weird or kludgy, say so and propose options that keep it clean before building it.

# Where it runs

- macOS (personal and work machines), Linux VMs, and bare-metal Unraid.
- Unraid is Slackware with no package manager; new system software means hunting down a Slackware package for `installpkg`. Keep system dependencies to a minimum (today: `ffmpeg`/`ffprobe`, `git`, `uv`). Python dependencies must install through uv with prebuilt wheels — nothing that needs a compiler or system libraries.
- Every machine installs from a persistent clone: `git pull && uv tool install .`. Don't add any step that needs pip or a hand-managed venv.

# Versions and releases

- Versions exist so `--version` says unambiguously what code is installed. That's their whole job; they don't signal compatibility, and breaking changes are fine.
- The version comes from git tags (hatch-vcs). Never edit a version number by hand. Untagged builds show a dev version with the commit hash.
- Releases are fully automatic: every push to `main` (direct or PR merge) runs the tests and, if they pass, tags and publishes a release. A `feat:` commit since the last tag makes it a minor bump; everything else, including malformed messages, is a patch. Brian tags majors or other minors by hand when it matters.
- Releases are cheap and a bad one is acceptable; don't add gates that could block one.

# Git

- Work on a feature branch off `main` by default.
- Push the feature branch after every commit, so work done on one machine is reachable from any other. Pushing a feature branch is non-destructive; do it without asking.
- Merge to `main` when Brian asks (that releases it).
- Use Conventional Commit prefixes in subjects: `feat:` for user-visible features, `fix:` for bug fixes, and `docs:`, `refactor:`, `test:`, `build:`, `ci:` or `chore:` for the rest. The release pipeline tolerates mistakes, but the prefixes drive the version bump and release notes.
