# UpConvert All The Things

Repair broken video and lossy audio, then **selectively** upconvert to lossless formats — with an optional **perceptual enhance** stage for listening/viewing sweetening.

Built from the SuperMap CD/FLAC stack (lossy repair + SBM-style 20/24-bit expand) plus ffmpeg video repair/remux.

## Honesty

- Lossy repair / bit expand does **not** recover a studio master.
- Video repair is best-effort (rebuild timestamps, drop corrupt packets, re-encode fallback).
- **Enhance** (EQ, stereo image, immersion) is creative/perceptual — not archival recovery, not true wave-field synthesis, and not trademark “Sonic Holography.”
- For archival purity: use the **Archive remux** preset (or turn repair, upconvert, and enhance **off**).

Deeper technical background: [docs/](docs/README.md).

## Formats

| Role | Extensions |
|------|------------|
| Video / combined | `.avi` `.mp4` `.mov` `.mkv` `.webm` |
| Audio | `.mp3` `.flac` `.ape` `.aac` `.wav` (+ `.m4a` via ffmpeg) |
| Combined output | **MKV** (default: copy or FFV1 video + FLAC audio) or **MP4** |

## Install

Requires **ffmpeg** and **ffprobe** on `PATH`.

```powershell
cd C:\githubdesktop\upconvert-all-the-things
python -m pip install -e ".[dev]"
```

Optional ML residual upscaler (GUI checkbox enables only when PyTorch is available):

```powershell
python -m pip install -e ".[ml]"
```

## Pipeline

1. Detect audio vs video
2. Optional **repair** (audio DSP and/or video container)
3. Optional **upconvert** (audio 20/24-bit SBM path; video FFV1 / near-lossless)
4. Optional **enhance** (EQ / stereo image / immersion / video sync·denoise)
5. Write FLAC or remux MKV/MP4
6. Optional delivery MP4/M4A compress (master kept by default)

```text
Detect → Repair? → Upconvert? → Enhance? → Write → Compress?
```

## Quick start

```powershell
# GUI
upconvert-all
upconvert-all-gui

# Preset: listen better (repair + upconvert + mild enhance)
upconvert-all process .\media -o .\output --preset listen-better -r

# Archive: remux/copy only
upconvert-all process clip.mkv -o .\out --preset archive-remux

# Immersive headphone listen
upconvert-all process track.mp3 -o .\out --preset immersive-listen
```

Boolean flags use `--flag` / `--no-flag`. With `--preset`, an explicit flag still overrides that field.

---

## Presets

| Preset | Intent |
|--------|--------|
| `listen-better` (default) | Repair + upconvert audio; EQ auto-clarity + mild stereo image; immersion off |
| `rescue-video` | Repair A/V; light audio enhance; **A/V sync tighten** |
| `archive-remux` | All repair / upconvert / enhance **off** |
| `master-mkv` | Full repair + upconvert (incl. FFV1); enhance **off** (unsweetened master) |
| `immersive-listen` | Repair + upconvert; binaural immersion + crossfeed + mild EQ |

---

## Options reference

### Core repair / upconvert

| Option (CLI) | GUI | What it does |
|--------------|-----|----------------|
| `--repair-audio` / `--no-…` | Repair audio | Spectral cleanup + bandwidth extension + mild M/S widen on lossy encodes. Does not restore discarded master data. |
| `--repair-video` / `--no-…` | Repair video | ffmpeg best-effort: genpts, drop corrupt packets, remux; re-encode fallback. Cannot restore deleted frames. |
| `--upconvert-audio` / `--no-…` | Upconvert audio (20/24-bit) | Expand toward 20/24-bit with SBM-style synthesis + dither. Approximate detail only. |
| `--upconvert-video` / `--no-…` | Re-encode video losslessly | Re-encode video as lossless FFV1 (MKV) or near-lossless H.264 CRF 0 (MP4). Off = stream-copy when possible. |
| `--repair-strength` `light\|medium\|strong` | Strength (advanced) | How aggressive lossy-audio repair is (artifact suppress, BWE, widen). |
| `--bits` `20\|24` | Bit depth (advanced) | Target bit depth for upconverted audio (packed in FLAC/WAV). |
| `--ml-upscaler` / `--no-…` | Richer detail (optional ML) | Spectral/ML preference prior during expand. Needs PyTorch (`pip install -e ".[ml]"`); GUI disables the box if missing. Falls back to analytic expand. |
| `--upconvert-iterations` / `--expand-iterations` | Expand iterations (advanced) | Projection iterations for expand (higher = smoother / more refined, slower). |
| `--dither` `sbm\|tpdf\|none` | Dither (advanced) | Final quantize dither: SBM noise-shaped TPDF (default), flat TPDF, or none. |
| `--native-sample-rate` / `--no-…` | Keep source sample rate (advanced) | Keep source rate (e.g. 48 kHz). `--no-native-sample-rate` forces 44.1 kHz. |
| `--container` `mkv\|mp4\|flac` | Container | Output container for video jobs (MKV recommended for FFV1+FLAC). |
| `--flac-level` `0–8` | FLAC compression (advanced) | Compression only; does not change sound. |
| `--ffmpeg` | — | Force ffmpeg decode for audio. |
| `--compress-mp4` / `--no-…` | Also write a smaller delivery MP4 | After master, write delivery MP4/M4A. |
| `--compress-quality` | Delivery quality (advanced) | See [Post-compress](#post-compress-mp4). |
| `--keep-master` / `--no-…` | — | Keep lossless/master beside delivery (default on). |

### Enhance (perceptual)

Enhance runs **after** repair/upconvert. Off entirely when `enhance_audio` / `enhance_video` are false (Archive / Master defaults).

| Option (CLI) | GUI | What it does |
|--------------|-----|----------------|
| `--enhance-audio` / `--no-…` | Enhance audio (listening) | Enable the listening enhance chain (EQ → image → immersion → crossfeed → true-peak ceiling). |
| `--eq-mode` `none\|auto-clarity\|target-curve` | EQ (advanced) | `auto-clarity`: mild mid scoop / presence from band energy. `target-curve`: gentle shelves. |
| `--eq-curve` `flat\|harman\|diffuse-field\|equal-loudness\|warm\|analytical\|vocal-presence\|small-speaker` | EQ curve (advanced) | Multi-band inspired targets when `eq-mode=target-curve` (not calibrated lab curves). |
| `--stereo-image` `0–100` | Stereo width (advanced) | M/S reshape + ambience; speaker mode adds mild crosstalk cancel (XTC). 0 = off. |
| `--stereo-image-mode` `speaker\|headphone` | Playback (advanced) | Speakers = mild XTC; headphones = width + light presence shelf (no XTC). |
| `--immersion` `off\|binaural\|speaker-wide` | Immersion (advanced) | WFS-**inspired** stage (ITD/ILD + early reflections / widen). Stereo/binaural only — **not** true WFS. |
| `--immersion-depth` `0–1` | Stage depth (advanced) | How deep the virtual stage / reflections feel (GUI uses 0–100%). |
| `--crossfeed` / `--no-…` | Headphone crossfeed (advanced) | Bauer-style lowpassed headphone crossfeed. |
| `--enhance-video` / `--no-…` | Enhance video | Gate for video enhance filters below. |
| `--video-sync-tighten` / `--no-…` | Tighten A/V sync (advanced) | `aresample=async` to reduce A/V drift (requires enhance video). |
| `--video-denoise` / `--no-…` | Light video denoise (advanced) | Light `hqdn3d` (requires enhance video; forces video re-encode if copy was planned). |

When enhance audio is active, a **true-peak style ceiling** (~−0.5 dBTP via 4× peak estimate) is applied so masters are less likely to clip after processing.

### Post-compress MP4

| Quality | Video | Audio |
|---------|-------|-------|
| `transparent` (default) | H.264 CRF 15, slow | **ALAC** |
| `high` | H.264 CRF 18, medium | **ALAC** |
| `balanced` | H.264 CRF 20, medium | AAC 320k |

Delivery names: `*.delivery.mp4` (video) or `*.m4a` (audio-only).

---

## CLI examples

```powershell
upconvert-all process track.mp3 --repair-audio --upconvert-audio --bits 24 --repair-strength strong
upconvert-all process clip.avi --repair-video --upconvert-audio --no-upconvert-video --container mkv
upconvert-all process clip.mkv --upconvert-video --container mkv
upconvert-all process clip.mp4 -o .\output --compress-mp4 --compress-quality transparent

# Enhance explicitly
upconvert-all process album\ -o .\out -r --preset listen-better --stereo-image 40
upconvert-all process track.flac -o .\out --no-repair-audio --no-upconvert-audio --enhance-audio --immersion binaural --crossfeed
```

## GUI

- **Presets** combo with a one-line intent description; switches to Custom when you tweak anything
- **What will happen** recap of the current pipeline (repair → upconvert → enhance → write)
- Simple by default: stage checkboxes + container. **Show advanced settings** reveals nested knobs
- Checkboxes and spin/combo controls match the tables above (plain-language labels; tooltips on hover)
- **A/B Preview** — ~15s mid clip with current audio repair/upconvert/**enhance** settings; Source ↔ Processed
- **Richer detail (optional ML)** — unchecked and disabled if PyTorch is not installed
- Window reflows for narrow/short sizes

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/README.md](docs/README.md) | Index of deep-dive notes |
| [docs/audio-repair.md](docs/audio-repair.md) | Lossy spectral repair & bandwidth extension |
| [docs/audio-upconvert.md](docs/audio-upconvert.md) | SBM-style expand, dither, ML prior |
| [docs/audio-enhance.md](docs/audio-enhance.md) | EQ, stereo image/XTC, immersion, crossfeed |
| [docs/video-repair-enhance.md](docs/video-repair-enhance.md) | Container repair, FFV1, sync, denoise |

## License / provenance

DSP ideas draw on SuperMap CD/FLAC (lossy repair + SBM-oriented expand) and standard ffmpeg practices. Enhance processors are original stereo approximations for listening comfort — they do not implement licensed Carver holography or laboratory WFS.
