# Audio repair — science and design

**Module:** `src/upconvert_all/lossy_repair.py`  
**Stage:** optional, before upconvert  
**Controls:** `--repair-audio`, `--repair-strength` (`light` | `medium` | `strong`)

## Problem

Lossy codecs (MP3, AAC, …) discard information below a psychoacoustic mask and often **hard-limit bandwidth** (e.g. brick-wall near 15–16 kHz). Joint stereo can collapse side energy. The result can sound dull, “swishy,” or spatially flat — but the discarded samples are **gone**.

This stage aims at a *cleaner listen*, not forensic restoration of a studio master.

## What we do

### 1. Detect likely lossy sources

Suffix heuristics (`.mp3`, `.m4a`, `.aac`, `.opus`, …). Video audio is often treated as lossy when repair is forced from the video path.

### 2. Spectral artifact softening

Per channel, work in an STFT domain:

- Estimate a **bandwidth cutoff** from the magnitude envelope (scan high→low for energy still within ~−40 dB of the peak, clamped to a plausible codec range).
- Soften unstable HF / residual structure above the usable band (strength scales with `light` / `medium` / `strong`).

This is related to classic **spectral subtraction / temporal smoothing** ideas: reduce erratic HF that codecs leave as quantization noise, without claiming to invert the encoder.

### 3. Bandwidth extension (BWE)

Above the estimated cutoff, synthesize a **plausible** high band by mirroring / decaying mid-high energy into missing bins and blending with a tilted envelope (`bwe_gain`, `hf_tilt` in `STRENGTH_PARAMS`).

Related literature (conceptual, not a clone of any one paper):

- Bandwidth extension / spectral band replication in codecs (SBR, HE-AAC)
- Blind BWE for enhancement (mirror/fold + envelope matching)

**Important:** synthesized HF is *statistically plausible*, not the original partials.

### 4. Optional Torch HF refine

If PyTorch is installed and ML is preferred, a light residual refine (shared with the ML upscaler path) can polish HF. Backend string becomes `spectral+torch-refine`; otherwise `spectral-bwe`.

### 5. Mild stereo widen (M/S)

Joint-stereo encodes often under-represent the **side** channel. A small Mid/Side widen (`stereo_widen` amount by strength) restores a bit of width, with a soft peak guard.

## Strength table (intent)

| Strength | Artifact suppress | BWE | Widen | Character |
|----------|-------------------|-----|-------|-----------|
| light | lower | gentler | mild | Safer on already-decent encodes |
| medium | balanced | moderate | moderate | Default middle ground |
| strong | aggressive | stronger HF fill | more width | Max “opened up” casual listen |

Exact coefficients live in `STRENGTH_PARAMS` / `_BLEND` in code.

## What we deliberately do not claim

- Recovery of bits discarded by the encoder
- Perfect mono compatibility after widen
- Replacement for a true lossless archive of the same performance

## Further reading (background)

- Painter & Spanias, *Perceptual Coding of Digital Audio* (overview of masking / lossy coding)
- Codec manuals on SBR / spectral band replication (HE-AAC)
- Standard STFT processing texts (Oppenheim & Schafer; or practical scipy.signal STFT docs)
