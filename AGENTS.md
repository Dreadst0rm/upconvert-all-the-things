# UpConvert All The Things — agent notes

## Product

Repair broken video and lossy audio, then **selectively** upconvert audio and/or video into lossless formats, with an optional **perceptual enhance** stage. Built from SuperMap CD/FLAC (lossy repair + SBM expand) plus ffmpeg video repair/remux.

User docs: [README.md](README.md), science notes: [docs/README.md](docs/README.md).

## Formats

| Kind | Extensions |
|------|------------|
| Video / A+V | `.avi`, `.mp4`, `.mov`, `.mkv`, `.webm` |
| Audio | `.mp3`, `.flac`, `.ape`, `.aac`, `.wav` (also `.m4a` via ffmpeg) |
| Combined output | Default **`.mkv`** (FFV1 + FLAC). Optional **`.mp4`** (H.264 lossless-ish / PCM or AAC remux limits). |

## Pipeline order

1. Detect media (audio-only vs video/A+V)
2. **Repair** (optional, independent toggles): lossy audio DSP; video stream repair via ffmpeg
3. **Upconvert** (optional): audio → 20/24-bit with **SBM noise-shaped TPDF dither** (or flat TPDF / none); video → lossless FFV1 (mkv) or remux
4. **Enhance** (optional): perceptual EQ / stereo image / immersion / crossfeed; video sync tighten / light denoise
5. Remux / write outputs
6. Optional **delivery MP4** compress (ALAC audio + high-CRF H.264); keep master by default

## Honesty (do not weaken)

- Lossy repair and SBM expand **do not** recover a studio master.
- Video “repair” is best-effort (genpts / discard corrupt / re-encode fallback), not forensic recovery.
- Enhance is creative sweetening — **not** true WFS, not licensed Sonic Holography, not archival purity.
- Archival purity: disable repair, expand, and enhance; remux/copy only when possible (`archive-remux` preset).

## Stack

Python 3.11+, numpy/scipy/numba, soundfile, mutagen, PySide6, **ffmpeg/ffprobe on PATH**. Optional PyTorch via `.[ml]`.

## Cursor Cloud specific instructions

- Dependencies live in a virtualenv at `.venv` (the startup update script creates it and runs `pip install -e ".[dev]"`). Activate with `source .venv/bin/activate`, or call tools directly via `.venv/bin/...`. The system Python is PEP 668 externally-managed, so always use the venv rather than installing into system Python.
- **Test:** `python -m pytest` (config in `pyproject.toml`; adds `src` to `pythonpath`). All suites, including `tests/test_gui.py`, should pass in this environment.
- **Run CLI:** `upconvert-all process <file|dir> -o <outdir> --preset <id>` (see [README.md](README.md) for presets/flags). Outputs are gitignored (`output/`, `*.flac`, `*.mkv`, …); write to a temp/`output` dir. Sample fixtures live in `smoke_media/`.
- **Run GUI:** `upconvert-all-gui` (or `upconvert-all` / `python -m upconvert_all` with no args). Qt needs a display: use `DISPLAY=:1` for the interactive desktop (computer-use), or `QT_QPA_PLATFORM=offscreen` for headless/CI. `tests/test_gui.py` sets offscreen automatically and self-skips if Qt platform libs are missing.
- There is **no linter/formatter** configured (no ruff/flake8/black/mypy config or dep); "lint" is not a step here.
- Harmless GUI runtime noise: `pipewire`/`PulseAudioService`/`pa_context_connect() failed` warnings appear because there's no audio server — the GUI still runs fine.
