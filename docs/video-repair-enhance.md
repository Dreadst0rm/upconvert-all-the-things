# Video repair and enhance

**Module:** `src/upconvert_all/video.py` (mux/repair); orchestration in `pipeline.py`  
**Controls:** `--repair-video`, `--upconvert-video`, `--enhance-video`, `--video-sync-tighten`, `--video-denoise`, `--container`

## Video repair (container / stream)

**Goal:** make a broken file *play and remux*, not reconstruct missing pictures.

Typical ffmpeg strategy (`repair_video_container`):

1. Open with tolerant flags: `+genpts`, ignore DTS issues, `discardcorrupt`, `err_detect ignore_err`
2. Prefer **stream copy** into MKV (most tolerant container)
3. On failure, **re-encode** fallback: H.264 + AAC

This matches common “ffmpeg hospital” practice. It cannot:

- Restore frames deleted from the bitstream
- Fix wrong colors from a bad master grade
- Un-do heavy generation loss as a forensic tool

`genpts` rebuilds presentation timestamps so players can scrub; discarding corrupt packets may create seamless-looking skips where data was trash.

## Upconvert video

| Container | `--upconvert-video` on | off |
|-----------|-------------------------|-----|
| MKV | **FFV1** lossless (level 3, slice CRC) | Stream-copy video when possible |
| MP4 | H.264 **CRF 0** (near-lossless; MP4 lacks practical FFV1) | Stream-copy when possible |

Audio for mux may be repaired/upconverted/enhanced FLAC (MKV) or PCM WAV (MP4).

## Enhance video

Gated by `--enhance-video` (Archive forces off).

### A/V sync tighten (`--video-sync-tighten`)

Applies audio filter `aresample=async=1:first_pts=0` during mux so minor drift is absorbed by resampling. Requires re-encoding audio if the path would otherwise stream-copy audio from the video file.

Complements repair’s `genpts` (timestamps) with a soft **clock stretch** on audio.

### Light denoise (`--video-denoise`)

Inserts `hqdn3d=1.5:1.5:2:2` (conservative spatial/temporal denoise). Filters **cannot** stream-copy:

- With FFV1 upconvert: filter + FFV1 encode  
- Without upconvert: light **libx264 CRF 18** encode so the filter can run  

Off by default — denoise is lossy relative to a bit-perfect copy.

## Rescue video preset

Turns on repair, audio upconvert, light audio enhance, **enhance video + sync tighten**, denoise off — aimed at “get me a watchable file with locked lips.”

## Delivery compress

Separate from enhance: `--compress-mp4` writes a smaller H.264 (+ ALAC/AAC) file beside the master. See README quality table.

## Background references

- FFmpeg documentation: `fflags`, `genpts`, `aresample`, `hqdn3d`, FFV1  
- IETF / Matroska + FFV1 lossless archival practice (FFmpeg Wiki / MediaArea notes)  
- ITU / EBU sync and loudness docs for broadcast A/V alignment (context for why async resample exists)
