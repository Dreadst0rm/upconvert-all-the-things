# Audio upconvert — SBM-style expand and dither

**Modules:** `src/upconvert_all/gapfill.py`, `src/upconvert_all/ml_upscaler.py`  
**Stage:** optional, after repair, before enhance  
**Controls:** `--upconvert-audio`, `--bits`, `--dither`, `--upconvert-iterations`, `--ml-upscaler`, `--native-sample-rate`

## Problem

Red-book / 16-bit PCM quantizes each sample to one of 65 536 levels. Going to 20- or 24-bit **containers** does not magically invent the missing LSBs of a real high-resolution recording. Sony’s **Super Bit Mapping (SBM)** and related noise-shaped dither techniques were about *encoding* high-res into 16-bit with shaped error — the inverse problem (“expand”) is ill-posed.

This project’s expand path is **SBM-inspired**: synthesize extra resolution *inside* each 16-bit quantization bin, then noise-shape when writing 20/24-bit.

## Pipeline (conceptual)

```text
int16 PCM
  → float expand (project into bin + smoothness / optional ML prefer)
  → iterate projection
  → dither-quantize to 20 or 24 bits
  → pack into 24-bit words for FLAC/WAV
```

### Expand / “gap fill”

1. Treat each sample as living in a quantization interval of width 1 LSB at 16-bit.
2. Maintain a high-precision float estimate consistent with that interval (**SBM-consistent projection**).
3. Apply mild temporal smoothness and optional **prefer** prior (spectral residual or Torch net) that nudges the residual toward richer HF detail — still constrained to the bin.
4. Repeat for `--upconvert-iterations` (GUI: **Iterations**).

Numba accelerates hot loops when available.

### Dither modes (`--dither`)

| Mode | Behavior |
|------|----------|
| `sbm` (default) | Noise-shaped TPDF-style dither; pushes quantization error toward less audible bands (FIR shaping filter in `sbm_noise_shaping_filter`) |
| `tpdf` | Flat triangular PDF dither (classic anti-quantize correlation) |
| `none` | Round without dither (can sound “grittier” / more correlated error) |

### Bit depth (`--bits`)

- **24** — full 24-bit packed samples  
- **20** — 20 significant bits left-aligned in a 24-bit word (lower 4 bits zero) — matches some legacy SuperMap-style packing

### Sample rate

`--native-sample-rate` (default **on**) keeps the source rate through decode/process/encode. `--no-native-sample-rate` forces 44.1 kHz (legacy path). Repair STFT / enhance filters all take the working `sample_rate`.

### ML upscaler

`ml_upscaler` supplies a **preference function** during expand (Torch if installed, else NumPy spectral residual). It does **not** turn on a separate neural “upscaler” product; it biases the underdetermined expand. GUI greys out the checkbox without PyTorch.

## Honesty

- Output is a **wider container** with synthesized LSBs + shaped quantization — useful for listening headroom and DSP chains, not a claim of “hi-res master recovered.”
- Tags / conversion logs should describe gap-fill and dither (see `process_description` / FLAC COMMENT fields).

## Background references

- Sony Super Bit Mapping (marketing/technical notes on noise-shaped reduction to 16-bit)
- Lipshitz, Vanderkooy, Wannamaker — dither and noise shaping for audio quantization
- Wannamaker, *Psychoacoustically Optimal Noise Shaping* (TPDF / shaped dither theory)
