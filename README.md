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

## Usage

```sh
vcsng video.mkv                      # 16 evenly spaced captures, 4 columns, PNG
vcsng -i 20s -c 6 -H 330 video.mkv   # every 20s, 6 columns, 330px-tall thumbs
vcsng --profile black -f jpeg *.mkv  # white-on-black theme, JPEG output
```

Configuration lives at `~/.config/vcsng/config.toml`; named presets at
`~/.config/vcsng/profiles/NAME.toml` (built-ins: `black`, `white`, `compact`, `mosaic`).
Run `vcsng --help` for the full flag reference.

## Development

```sh
uv sync
uv run pytest
```
