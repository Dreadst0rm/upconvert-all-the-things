"""Plain-language pipeline summary for the GUI (Qt-free)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .formats import media_kind
from .pipeline import ProcessOptions

_EQ_CURVE_WORDS = {
    "flat": "flat EQ",
    "harman": "Harman-inspired EQ",
    "diffuse-field": "diffuse-field EQ",
    "equal-loudness": "equal-loudness EQ",
    "warm": "warm EQ",
    "analytical": "analytical EQ",
    "vocal-presence": "vocal-presence EQ",
    "small-speaker": "small-speaker EQ",
}

_IMMERSION_WORDS = {
    "off": None,
    "binaural": "binaural immersion",
    "speaker-wide": "wider speaker image",
}


def queue_media_kinds(paths: Iterable[Path]) -> set[str]:
    """Return {audio, video} kinds present in `paths` (unknown dropped)."""
    kinds = {media_kind(p) for p in paths}
    kinds.discard("unknown")
    return kinds


def summarize_pipeline(
    options: ProcessOptions,
    *,
    queue_kinds: set[str] | None = None,
) -> str:
    """One-line description of what Run will do with the current options."""
    stages: list[str] = []
    processing = any(
        (
            options.repair_audio,
            options.repair_video,
            options.upconvert_audio,
            options.upconvert_video,
            options.enhance_audio,
            options.enhance_video,
        )
    )

    if options.repair_audio or options.repair_video:
        bits: list[str] = []
        if options.repair_audio:
            bits.append(f"audio ({options.repair_strength})")
        if options.repair_video:
            bits.append("video")
        stages.append("Repair " + " + ".join(bits))

    if options.upconvert_audio or options.upconvert_video:
        bits = []
        if options.upconvert_audio:
            extra = [f"{options.output_bits}-bit"]
            if options.ml_upscaler:
                extra.append("ML detail")
            bits.append("audio (" + ", ".join(extra) + ")")
        if options.upconvert_video:
            bits.append("video lossless")
        stages.append("Upconvert " + " + ".join(bits))

    if options.enhance_audio:
        bits = []
        if options.eq_mode == "auto-clarity":
            bits.append("auto-clarity EQ")
        elif options.eq_mode == "target-curve":
            bits.append(
                _EQ_CURVE_WORDS.get(options.eq_curve, f"{options.eq_curve} EQ")
            )
        if options.stereo_image_strength > 0:
            mode = (
                "headphones"
                if options.stereo_image_mode == "headphone"
                else "speakers"
            )
            bits.append(f"stereo {options.stereo_image_strength}% ({mode})")
        imm = _IMMERSION_WORDS.get(options.immersion)
        if imm:
            bits.append(imm)
        if options.crossfeed:
            bits.append("crossfeed")
        if bits:
            stages.append("Enhance audio: " + ", ".join(bits))
        else:
            stages.append("Enhance audio (no extra coloring)")

    if options.enhance_video:
        bits = []
        if options.video_sync_tighten:
            bits.append("tighten sync")
        if options.video_denoise:
            bits.append("light denoise")
        if bits:
            stages.append("Enhance video: " + ", ".join(bits))
        else:
            stages.append("Enhance video")

    dest = f"Write {options.container.upper()}"
    if options.compress_mp4:
        dest += f" + smaller delivery MP4 ({options.compress_quality})"
    if not options.native_sample_rate:
        dest += ", resample to 44.1 kHz"
    stages.append(dest)

    if not processing:
        body = (
            "Remux/copy only — no repair, upconvert, or sweetening → " + dest
        )
    else:
        body = " → ".join(stages)

    if queue_kinds == {"audio"}:
        video_wanted = (
            options.repair_video
            or options.upconvert_video
            or options.enhance_video
        )
        if video_wanted:
            body += "  ·  Video steps skipped (audio-only files)."

    return body
