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
