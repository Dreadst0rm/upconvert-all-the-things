# Audio enhance — EQ, image, immersion

**Module:** `src/upconvert_all/enhance.py`  
**Stage:** optional, **after** repair/upconvert, before write  
**Controls:** `--enhance-audio`, `--eq-*`, `--stereo-image*`, `--immersion*`, `--crossfeed`

## Design principle

Enhance is **taste / playback geometry**, not recovery. Archive remux and Master MKV presets leave it off so masters stay unsweetened.

Order of operations:

```text
float PCM → EQ → stereo image → immersion → crossfeed → true-peak ceiling → int PCM
```

Each step is a no-op when its control is off / zero. Mono skips image, immersion, and crossfeed.

---

## Equalizer

### `auto-clarity`

Estimates band RMS in a low-mid band (~250–800 Hz) vs presence (~2–5 kHz). If mids dominate, apply a mild **dip**; if presence is weak, a mild **high shelf lift**. Goal: reduce “boxy” masking without multiband compression.

This is a lightweight cousin of masking-aware EQ ideas, not a full ITU loudness processor.

### `target-curve` + `--eq-curve`

Multi-band parametric/shelf profiles (RBJ biquads). **Inspired approximations** — not calibrated Harman/DF/ISO lab dumps.

| Curve | Intent |
|-------|--------|
| `flat` | Identity (no filters) |
| `harman` | Mild bass shelf + slight upper-mid/treble shaping (OE preference *direction*) |
| `diffuse-field` | Brighter DF-inspired treble; less bass than Harman |
| `equal-loudness` | ISO 226–inspired quiet-listen tilt (bass + high lift, mid dip) |
| `warm` | Bass/lower-mid lift, soft treble roll-off |
| `analytical` | Controlled bass, slight presence peak (monitor-ish) |
| `vocal-presence` | Forward 1–3 kHz for speech/vocals |
| `small-speaker` | Stronger bass + presence for small playback systems |

Unknown curve IDs raise `ValueError`. Curve list: `enhance.list_eq_curves()`.

True **ITU-R BS.1770** loudness-matched tilt remains a future refinement; use `equal-loudness` as a perceptual stand-in for quiet listening.

---

## Stereo image (“holography-style”)

**Not** a licensed Carver Phase Linear “Sonic Holography” implementation. Shipped name: stereo image / holography-**style**.

| Step | Role |
|------|------|
| M/S reshape | Increase side relative to mid (`strength` 0–100) |
| Ambience blend | Delayed, HF-damped side reflection mixed ±L/R |
| Speaker XTC | Mild opposite-channel cancel (short delay + lowpass) approximating **crosstalk cancellation** for loudspeakers |
| Headphone mode | Skip XTC; lighter width + pinna-ish presence shelf |

Crosstalk cancellation (XTC) literature: Bauer, Schroeder, and later BACCH / Ambiophonics-style work — commercial systems are far more elaborate (measured HRTFs, head tracking). Ours is a **mild fixed approximation** with soft limiting.

---

## Immersion (WFS-inspired)

**Wave field synthesis (WFS)** physically recreates a wavefront with a dense loudspeaker array and room geometry (Berkhout et al.). A stereo file cannot do that.

Our modes:

| Mode | Approach |
|------|----------|
| `binaural` | Virtual L/R on an arc via **ITD** (interaural time difference) + **ILD** (level), plus damped early reflection from mid; slight M/S widen |
| `speaker-wide` | Stronger M/S + ambience + light XTC (no binaural ITD) |
| `off` | Bypass |

`--immersion-depth` scales delay, attenuation, and reflection amount.

Optional package HRTF datasets were deferred; v1 uses analytic ITD/ILD + IIR damping (numpy/scipy only).

---

## Crossfeed

Bauer-style **lowpassed, delayed** bleed of L→R and R→L for headphones. Reduces the “in-head” extreme of hard-panned stereo. Pairs well with `immersion=binaural` and headphone image mode (Immersive listen preset).

---

## True-peak ceiling

After enhance, estimate peak with a cheap **4×** interpolated envelope and scale so peak stays under about **−0.5 dBTP**. Reduces intersample overs when DACs / lossy re-encodes reconstruct between samples. Not a full ITU True Peak meter (BS.1770 Annex 2); good enough as a safety net.

---

## Preset mapping

| Preset | Enhance audio highlights |
|--------|---------------------------|
| Listen better | `auto-clarity` + stereo image ~25, immersion off |
| Immersive listen | clarity + binaural + crossfeed + headphone image |
| Archive / Master | all enhance off |

## Background references

- Berkhout, de Vries, Vogel — Wave field synthesis foundations  
- Blauert — *Spatial Hearing* (ITD/ILD)  
- Bauer — stereophonic crosstalk / headphone crossfeed  
- ITU-R BS.1770 — loudness and true-peak (for future loudness-tilt work)  
- Olive / Harman — headphone preference curves (inspiration only for shelf labels)
