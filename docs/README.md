# Technical documentation

User-facing options live in the [main README](../README.md). These notes explain **why** the pipeline behaves as it does and what the algorithms are (and are not).

| Document | Stage |
|----------|--------|
| [Audio repair](audio-repair.md) | Lossy cleanup + bandwidth extension |
| [Audio upconvert](audio-upconvert.md) | SBM-style bit expand + dither |
| [Audio enhance](audio-enhance.md) | Perceptual EQ / image / immersion |
| [Video repair & enhance](video-repair-enhance.md) | ffmpeg repair, FFV1, sync, denoise |

Related integration package (Databricks gold → Dataverse CRM serving): [../integrations/databricks-dataverse/README.md](../integrations/databricks-dataverse/README.md).

## Mental model

```text
Source  →  Repair (artifact / container)  →  Upconvert (bit depth / codec)
        →  Enhance (taste / playback)     →  Encode / remux
```

| Stage | Goal | Honesty |
|-------|------|---------|
| Repair | Make damaged or heavily compressed media *more listenable / playable* | Does not recreate lost master data or deleted frames |
| Upconvert | Store audio in a wider bit-depth container with shaped dither; optionally lossless video | Extra bits are *synthesized*, not recovered |
| Enhance | Creative listening/viewing sweetening | Off for archive; never claim true WFS or studio holography |

## Code map

| Concern | Module |
|---------|--------|
| Orchestration | `src/upconvert_all/pipeline.py` |
| Lossy audio repair | `src/upconvert_all/lossy_repair.py` |
| Bit expand / dither | `src/upconvert_all/gapfill.py` |
| ML / spectral prior | `src/upconvert_all/ml_upscaler.py` |
| Listening enhance | `src/upconvert_all/enhance.py` |
| Target EQ curves | `src/upconvert_all/enhance_eq.py` |
| Video ffmpeg | `src/upconvert_all/video.py` |
| Presets | `src/upconvert_all/presets.py` |
