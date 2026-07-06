# vcs-ng

Generate contact sheets (thumbnail grids with metadata and timestamps) from video
files. A modern Python rewrite of [Video Contact Sheet *NIX](http://p.outlyer.net/vcs/)
(vcs 1.13.x, bash, unmaintained).

Why the rewrite:

- **Two dependencies, not five**: only `ffmpeg`/`ffprobe` are required. ImageMagick,
  mplayer, perl, and awk are gone — all image compositing happens in-process with Pillow.
- **Fast**: frames are captured by parallel ffmpeg processes piped straight into memory,
  instead of the original's strictly serial one-process-per-thumbnail pipeline.
- **Fonts that just work**: DejaVu Sans is bundled; any TTF/OTF path or installed family
  name can be used instead.

## Requirements

- Python ≥ 3.11
- `ffmpeg` and `ffprobe` on your `PATH` (e.g. `brew install ffmpeg`,
  `apt install ffmpeg`)

## Installation

Clone the repository and install it as a global tool with
[uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/adfaklsdjf/vcs-ng.git
cd vcs-ng
uv tool install .
```

This puts a `vcsng` command on your `PATH`. To upgrade later, `git pull` and
re-run `uv tool install .` (add `--force` to overwrite the existing install).

Prefer pip? From the cloned directory:

```sh
pip install .
```

## Usage

```sh
vcsng video.mkv                      # 16 evenly spaced captures, 4 columns, PNG
vcsng -i 20s -c 6 -H 330 video.mkv   # every 20s, 6 columns, 330px-tall thumbs
vcsng --profile black -f jpeg *.mkv  # white-on-black theme, JPEG output
vcsng --no-credit video.mkv          # omit the "Created with vcs-ng" footer line
```

Configuration lives at `~/.config/vcsng/config.toml`; named presets at
`~/.config/vcsng/profiles/NAME.toml` (built-ins: `black`, `white`, `compact`, `mosaic`).
Run `vcsng --help` for the full flag reference.

## Development

```sh
uv sync
uv run pytest
```
