"""Selective repair + upconvert orchestration for audio and video."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import soundfile as sf

from .conversion_log import ConversionLog
from .encode import tags_for_track, write_flac
from .enhance import enhance_audio_pcm
from .formats import media_kind
from .gapfill import gap_fill, process_description
from .io_audio import (
    SAMPLE_RATE,
    extract_audio_from_video,
    load_audio_clip,
    load_audio_segment,
)
from .lossy_repair import (
    is_likely_lossy,
    repair_backend,
    repair_description,
    repair_lossy_pcm,
)
from .video import (
    compress_audio_alac_m4a,
    compress_delivery_mp4,
    export_pcm24_wav,
    mux_lossless_mkv,
    mux_mp4,
    probe,
    repair_video_container,
    with_temp_dir,
)

ProgressCb = Callable[[str, float], None]
Container = Literal["mkv", "mp4", "flac"]
CompressQuality = Literal["transparent", "high", "balanced"]


@dataclass
class ProcessOptions:
    output_dir: Path
    repair_audio: bool = True
    repair_video: bool = True
    upconvert_audio: bool = True
    upconvert_video: bool = False
    repair_strength: str = "strong"
    output_bits: int = 24
    ml_upscaler: bool = True
    expand_iterations: int = 5
    dither: str = "sbm"  # sbm | tpdf | none
    flac_level: int = 5
    container: Container = "mkv"
    force_ffmpeg: bool = False
    # Post-process: delivery MP4/M4A without replacing the master
    compress_mp4: bool = False
    compress_quality: CompressQuality = "transparent"
    keep_master: bool = True
    # Keep source rate by default; False forces resample to 44.1 kHz.
    native_sample_rate: bool = True
    # Optional perceptual enhance (after repair/upconvert; off for archive).
    enhance_audio: bool = False
    enhance_video: bool = False
    eq_mode: str = "none"  # none | auto-clarity | target-curve
    eq_curve: str = "flat"  # see enhance.EQ_CURVE_IDS
    stereo_image_strength: int = 0  # 0–100
    stereo_image_mode: str = "speaker"  # speaker | headphone
    immersion: str = "off"  # off | binaural | speaker-wide
    immersion_depth: float = 0.35
    crossfeed: bool = False
    video_sync_tighten: bool = False
    video_denoise: bool = False


def _target_sample_rate(options: ProcessOptions) -> int | None:
    return None if options.native_sample_rate else SAMPLE_RATE


def _prefer_fn(enabled: bool, *, sample_rate: int):
    if not enabled:
        return None
    from .ml_upscaler import make_prefer_fn

    return make_prefer_fn(use_torch=True, sample_rate=sample_rate)


def _ml_backend(enabled: bool) -> str | None:
    if not enabled:
        return None
    from .ml_upscaler import backend_name

    return backend_name(prefer_torch=True)


def _process_audio_pcm(
    pcm: np.ndarray,
    *,
    options: ProcessOptions,
    source_suffix: str,
    sample_rate: int,
    force_repair: bool = False,
    progress: ProgressCb | None = None,
) -> tuple[np.ndarray, str, bool, str]:
    """Returns (pcm_out, flac_subtype, repaired, description)."""
    repaired = False
    should_repair = options.repair_audio and (
        force_repair
        or is_likely_lossy(source_suffix)
        or source_suffix.lower() in {".aac", ".mp3", ".m4a"}
    )
    if should_repair:
        if progress:
            progress("repair lossy audio", 0.15)
        pcm = repair_lossy_pcm(
            pcm,
            strength=options.repair_strength,  # type: ignore[arg-type]
            sample_rate=sample_rate,
        )
        repaired = True

    prefer = _prefer_fn(
        options.ml_upscaler and options.upconvert_audio, sample_rate=sample_rate
    )
    if options.upconvert_audio:
        if progress:
            progress("upconvert audio", 0.4)
        pcm_out = gap_fill(
            pcm,
            output_bits=options.output_bits,
            prefer_fn=prefer,
            iterations=options.expand_iterations,
            dither=options.dither,
            progress=progress,
        )
        subtype = "PCM_24"
    else:
        pcm_out = pcm
        subtype = "PCM_16"

    enhance_desc = ""
    if options.enhance_audio:
        if progress:
            progress("enhance audio", 0.72)
        pcm_out, enhance_desc = enhance_audio_pcm(
            pcm_out,
            subtype=subtype,
            sample_rate=sample_rate,
            enhance_audio=True,
            eq_mode=options.eq_mode,
            eq_curve=options.eq_curve,
            stereo_image_strength=options.stereo_image_strength,
            stereo_image_mode=options.stereo_image_mode,
            immersion=options.immersion,
            immersion_depth=options.immersion_depth,
            crossfeed=options.crossfeed,
        )

    parts: list[str] = []
    if repaired:
        parts.append(
            repair_description(
                options.repair_strength,  # type: ignore[arg-type]
                repair_backend(prefer_torch=options.ml_upscaler),
            )
        )
    parts.append(
        process_description(
            gap_fill_enabled=options.upconvert_audio,
            output_bits=options.output_bits if options.upconvert_audio else None,
            ml_upscaler=options.ml_upscaler and options.upconvert_audio,
            dither=options.dither if options.upconvert_audio else "none",
        )
    )
    if enhance_desc:
        parts.append(enhance_desc)
    return pcm_out, subtype, repaired, " ".join(parts)


def process_audio_file(
    path: Path,
    options: ProcessOptions,
    *,
    progress: ProgressCb | None = None,
) -> list[Path]:
    path = Path(path)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    clip, meta = load_audio_clip(
        path,
        force_ffmpeg=options.force_ffmpeg,
        target_sample_rate=_target_sample_rate(options),
    )
    log_stem = f"{path.stem}.from-{path.suffix.lstrip('.')}"
    clog = ConversionLog(options.output_dir / f"{log_stem}.convert.log", source=str(path))

    def prog(msg: str, frac: float) -> None:
        clog.step(int(frac * 100), msg)
        if progress:
            progress(msg, frac)

    pcm_out, subtype, repaired, description = _process_audio_pcm(
        clip.pcm,
        options=options,
        source_suffix=path.suffix,
        sample_rate=clip.sample_rate,
        progress=prog,
    )
    out_path = options.output_dir / f"{log_stem}.flac"
    tags = tags_for_track(
        album=meta.album or "UpConvert",
        artist=meta.artist or "Unknown",
        title=meta.title or path.stem,
        track_number=meta.track_number,
        track_total=meta.track_total,
        gap_fill=options.upconvert_audio,
        output_bits=options.output_bits if options.upconvert_audio else None,
        ml_upscaler=options.ml_upscaler and options.upconvert_audio,
        ml_backend=_ml_backend(options.ml_upscaler and options.upconvert_audio),
        repair_lossy=repaired,
        repair_strength=options.repair_strength if repaired else None,
        description=description,
        extra_comment=(
            f"source={path.name}; decode={meta.backend}; sample_rate={clip.sample_rate}"
        ),
    )
    prog("write flac", 0.9)
    write_flac(
        out_path,
        pcm_out,
        sample_rate=clip.sample_rate,
        subtype=subtype,
        compression_level=options.flac_level,
        tags=tags,
    )
    outputs = [out_path]
    if options.compress_mp4:
        m4a = options.output_dir / f"{log_stem}.m4a"
        prog("post-compress alac", 0.96)
        compress_audio_alac_m4a(out_path, m4a, progress=prog)
        outputs.append(m4a)
        if not options.keep_master:
            out_path.unlink(missing_ok=True)
            outputs = [m4a]
    clog.complete(outputs=outputs, ok=True)
    if progress:
        progress("done", 1.0)
    return outputs


def process_video_file(
    path: Path,
    options: ProcessOptions,
    *,
    progress: ProgressCb | None = None,
) -> list[Path]:
    path = Path(path)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    info = probe(path)
    clog = ConversionLog(options.output_dir / f"{path.stem}.convert.log", source=str(path))

    def prog(msg: str, frac: float) -> None:
        clog.step(int(frac * 100), msg)
        if progress:
            progress(msg, frac)

    container: Container = "mkv" if options.container == "flac" else options.container
    ext = ".mkv" if container == "mkv" else ".mp4"
    out_path = options.output_dir / f"{path.stem}.upconverted{ext}"
    target_sr = _target_sample_rate(options)

    with with_temp_dir() as tmp:
        tmp_path = Path(tmp)
        work_video = path

        if options.repair_video:
            repaired_path = tmp_path / "repaired.mkv"
            prog("repair video", 0.1)
            repair_video_container(path, repaired_path, progress=prog)
            work_video = repaired_path

        audio_flac: Path | None = None
        audio_wav: Path | None = None

        need_audio = info.has_audio and (
            options.repair_audio or options.upconvert_audio or options.enhance_audio
        )
        if need_audio:
            prog("extract audio", 0.35)
            clip, _meta = extract_audio_from_video(
                work_video, target_sample_rate=target_sr
            )
            pcm_out, subtype, _repaired, _desc = _process_audio_pcm(
                clip.pcm,
                options=options,
                source_suffix=".mp3",
                sample_rate=clip.sample_rate,
                force_repair=options.repair_audio,
                progress=prog,
            )
            if container == "mkv":
                audio_flac = tmp_path / "audio.flac"
                write_flac(
                    audio_flac,
                    pcm_out,
                    sample_rate=clip.sample_rate,
                    subtype=subtype,
                    compression_level=options.flac_level,
                )
            else:
                audio_wav = tmp_path / "audio.wav"
                if subtype == "PCM_24":
                    export_pcm24_wav(audio_wav, pcm_out, sample_rate=clip.sample_rate)
                else:
                    sf.write(
                        str(audio_wav),
                        pcm_out,
                        clip.sample_rate,
                        subtype="PCM_16",
                    )

        sync = bool(options.enhance_video and options.video_sync_tighten)
        denoise = bool(options.enhance_video and options.video_denoise)
        prog("mux output", 0.7)
        if container == "mkv":
            mux_lossless_mkv(
                video_src=work_video,
                audio_flac=audio_flac,
                dst=out_path,
                upconvert_video=options.upconvert_video,
                copy_audio_from_video=audio_flac is None and info.has_audio,
                sync_tighten=sync,
                denoise=denoise,
                progress=prog,
            )
        else:
            mux_mp4(
                video_src=work_video,
                audio_wav=audio_wav,
                dst=out_path,
                upconvert_video=options.upconvert_video,
                sync_tighten=sync,
                denoise=denoise,
                progress=prog,
            )

    outputs = [out_path]
    if options.compress_mp4:
        mp4_path = options.output_dir / f"{path.stem}.delivery.mp4"
        prog("post-compress mp4", 0.96)
        compress_delivery_mp4(
            out_path,
            mp4_path,
            quality=options.compress_quality,
            progress=prog,
        )
        outputs.append(mp4_path)
        if not options.keep_master:
            out_path.unlink(missing_ok=True)
            outputs = [mp4_path]
    clog.complete(outputs=outputs, ok=True)
    if progress:
        progress("done", 1.0)
    return outputs


def process_file(
    path: Path,
    options: ProcessOptions,
    *,
    progress: ProgressCb | None = None,
) -> list[Path]:
    path = Path(path)
    kind = media_kind(path)
    if kind == "audio":
        return process_audio_file(path, options, progress=progress)
    if kind == "video":
        return process_video_file(path, options, progress=progress)
    raise ValueError(f"Unsupported media: {path.suffix}")


@dataclass
class AbPreviewResult:
    source_wav: Path
    processed_wav: Path
    start_sec: float
    duration_sec: float
    description: str
    sample_rate: int


def _write_preview_wav(
    path: Path, pcm: np.ndarray, *, subtype: str, sample_rate: int
) -> Path:
    arr = np.asarray(pcm)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if subtype == "PCM_24" and np.issubdtype(arr.dtype, np.integer):
        arr = np.left_shift(np.asarray(arr, dtype=np.int32), 8)
    sf.write(str(path), arr, sample_rate, subtype=subtype)
    return path


def build_ab_preview(
    path: Path,
    options: ProcessOptions,
    *,
    out_dir: Path,
    duration_sec: float = 15.0,
    progress: ProgressCb | None = None,
) -> AbPreviewResult:
    """Build short source vs processed WAVs using current audio repair/upconvert settings."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = media_kind(path)
    if kind == "unknown":
        raise ValueError(f"Unsupported media: {path.suffix}")

    start_sec = 0.0
    try:
        info = probe(path)
    except RuntimeError:
        info = None
    if info is not None:
        if kind == "video" and not info.has_audio:
            raise RuntimeError(f"no audio stream in {path.name}")
        if info.duration and info.duration > duration_sec:
            start_sec = max(0.0, (info.duration - duration_sec) / 2.0)

    if progress:
        progress("extract preview segment", 0.1)
    clip, _meta = load_audio_segment(
        path,
        start_sec=start_sec,
        duration_sec=duration_sec,
        target_sample_rate=_target_sample_rate(options),
    )
    actual_dur = clip.pcm.shape[0] / float(clip.sample_rate)

    source_wav = out_dir / "ab_source.wav"
    processed_wav = out_dir / "ab_processed.wav"
    _write_preview_wav(
        source_wav, clip.pcm, subtype="PCM_16", sample_rate=clip.sample_rate
    )

    force_repair = bool(options.repair_audio and kind == "video")
    pcm_out, subtype, _repaired, description = _process_audio_pcm(
        clip.pcm,
        options=options,
        source_suffix=path.suffix if kind == "audio" else ".mp3",
        sample_rate=clip.sample_rate,
        force_repair=force_repair,
        progress=progress,
    )
    if progress:
        progress("write preview wavs", 0.9)
    _write_preview_wav(
        processed_wav, pcm_out, subtype=subtype, sample_rate=clip.sample_rate
    )
    if progress:
        progress("preview ready", 1.0)
    return AbPreviewResult(
        source_wav=source_wav,
        processed_wav=processed_wav,
        start_sec=start_sec,
        duration_sec=actual_dur,
        description=description,
        sample_rate=clip.sample_rate,
    )
