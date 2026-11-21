# vcs-ng

Generate contact sheets (thumbnail grids with metadata and timestamps) from video files. A modern Python rewrite of [Video Contact Sheet *NIX](http://p.outlyer.net/vcs/) (vcs 1.13.x, bash, unmaintained).

Why the rewrite:

- **Two dependencies, not five**: only `ffmpeg`/`ffprobe` are required. ImageMagick, mplayer, perl, and awk are gone — all image compositing happens in-process with Pillow.
- **Fast**: frames are captured by parallel ffmpeg processes piped straight into memory, instead of the original's strictly serial one-process-per-thumbnail pipeline.
- **Fonts that just work**: DejaVu Sans is bundled; any TTF/OTF path or installed family name can be used instead.

## Requirements

- Python ≥ 3.11
- `ffmpeg` and `ffprobe` on your `PATH` (e.g. `brew install ffmpeg`, `apt install ffmpeg`)

## Installation

Clone the repository and install it as a global tool with [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/adfaklsdjf/vcs-ng.git
cd vcs-ng
uv tool install .
```

This puts a `vcsng` command on your `PATH`. To upgrade later, `git pull` and re-run `uv tool install .` (add `--force` to overwrite the existing install).

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
vcsng -r                             # every video under the current directory
vcsng /media/tv                      # a directory argument is always scanned recursively
```

### Scanning directories

Given a directory (or `-r`, which defaults to the current directory), vcsng walks it recursively and makes a sheet **next to each video**: relative `-o` templates are resolved against the video's own directory rather than the CWD. It skips hidden files/directories, symlinks, `Sample`/`Samples` directories, and files with the word "sample" in their name. Videos are recognized by extension (`--extensions mkv,mp4,...` or `[scan] extensions`).

For each video, whatever already exists at the output path decides what happens:

| Existing output | Action |
|---|---|
| nothing | generate |
| valid image of the configured format | skip (up to date) |
| valid image of the configured format, narrower than `min_width` (only if `--min-width`/`min_width` is set) | regenerate |
| anything else (truncated/corrupt, wrong format, not an image) | rename to `NAME.bad`, then generate |

`--regenerate` regenerates every sheet, even up-to-date ones. Failures are logged and the run continues; a summary and the list of failed files are printed at the end. Sheets are written to a hidden temporary file and renamed into place, so an interrupted run never leaves a half-written sheet.

### Existing sheets are kept, not overwritten

Whenever a new sheet replaces an existing one (single files or scans), the old one is renamed rather than overwritten: `video-ss.jpg` becomes `video-ss-old.jpg`, then `video-ss-old1.jpg`, `video-ss-old2.jpg`, and so on. The rename only happens once the new sheet has been fully written. Pass `--overwrite` (or set `[output] overwrite = true`) to replace sheets in place instead. Corrupt/non-image files found while scanning are always renamed to `NAME.bad`, never overwritten.

Configuration lives at `~/.config/vcsng/config.toml`; named presets at `~/.config/vcsng/profiles/NAME.toml` (built-ins: `black`, `white`, `compact`, `mosaic`). Run `vcsng --help` for the full flag reference.

## Configuration file

`~/.config/vcsng/config.toml` (or `$XDG_CONFIG_HOME/vcsng/config.toml`) sets persistent defaults so you don't have to repeat flags on every run. Settings are layered in this order, later layers override earlier ones:

built-in defaults < `config.toml` < `--profile` file(s), in the order given < CLI flags

Use `--config PATH` to load a config file from a non-default location, or `--no-config` to ignore it entirely for one run. Unknown keys/sections in a config file are ignored with a warning, not a hard error.

Every key below corresponds to a CLI flag; where one exists it's noted in parentheses.

```toml
[capture]
mode = "numcaps"       # numcaps | interval | manual (inferred from numcaps/interval if omitted)
numcaps = 16            # -n/--numcaps
interval = "20s"        # -i/--interval (accepts timespecs like "1m30s")
from = "10s"             # --from
to = "5m"                 # --to
end_offset = "5%"         # --end-offset (percent or seconds; skip this much off the end)
skip_short = false         # --skip-short (skip videos too short for the interval;
                           # default falls back to a single centered capture)

[layout]
columns = 4              # -c/--columns
height = "100%"           # -H/--height (percent or pixels, e.g. 330)
padding = 2               # -p/--padding
aspect = "auto"            # -a/--aspect (auto | keep | explicit ratio like 16:9)
shadows = true             # --no-shadows sets this false
timestamps = true          # --no-timestamps sets this false

[style]
bg_heading = "#afcd7a"
fg_heading = "black"
bg_sign = "slategray"
fg_sign = "black"
bg_title = "white"
fg_title = "black"
bg_contact = "white"
bg_tstamps = "black"
fg_tstamps = "white"
font_heading = "DejaVuSans"
font_tstamps = "DejaVuSans"
font_sign = "DejaVuSans"
font_title = "DejaVuSans"
pts_heading = 14
pts_tstamps = 14
pts_sign = 10
pts_title = 33
tstamp_pad_x = 5          # --tstamp-pad-x; px between timestamp text and box edge
tstamp_pad_y = 5          # --tstamp-pad-y
# bg_all / fg_all / font_all set all bg_*, fg_*, or font_* keys at once
# (each individual key above still overrides its shorthand)

[output]
format = "png"            # -f/--format (png | jpeg/jpg)
quality = 92               # -q/--quality (JPEG only)
output = "{stem}.{ext}"     # -o/--output template ({stem} {name} {dir} {ext})
suffix = "-ss"               # --suffix, appended to {stem} before the extension
overwrite = false             # --overwrite; replace existing sheets instead of renaming them NAME-old.EXT

[scan]                    # used when scanning directories (-r or a directory argument)
min_width = 2000           # --min-width; existing sheets narrower than this are regenerated
                           # (off unless set; setting it here turns it on)
# extensions = ["3gp", "asf", "avi", "divx", "f4v", "flv", "m2ts", "m4v", "mkv", "mov",
#               "mp4", "mpeg", "mpg", "mts", "ogv", "rm", "rmvb", "webm", "wmv"]
#                          # --extensions (comma-separated); default shown

[general]
anonymous = false         # --anonymous
credit = true               # --no-credit sets this false
signature = "Preview created by"  # --signature
username = "yourname"       # --username
workers = 8                  # -j/--workers (parallel ffmpeg capture processes; default: CPU count)
```

A few flags are intentionally CLI-only and have no config equivalent because they're inherently per-run/per-file, not sensible defaults: `-S/--stamp` (one-off manual timestamps), `-T/--title` (the contact sheet heading), and `--regenerate` (redo every sheet in a scan).

## Development

```sh
uv sync
uv run pytest
```
