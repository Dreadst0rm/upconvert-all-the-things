"""Video probe, repair, and lossless remux via ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

ProgressCb = Callable[[str, float], None]


@dataclass
class StreamInfo:
    index: int
    codec_type: str
    codec_name: str
    extra: dict = field(default_factory=dict)


@dataclass
class MediaProbe:
    path: Path
    format_name: str
    duration: float | None
    streams: list[StreamInfo]

    @property
    def has_video(self) -> bool:
        return any(s.codec_type == "video" for s in self.streams)

    @property
    def has_audio(self) -> bool:
        return any(s.codec_type == "audio" for s in self.streams)


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found on PATH")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe not found on PATH")
    return path


def probe(path: Path | str) -> MediaProbe:
    path = Path(path)
    cmd = [
        ffprobe_bin(),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path.name}: {proc.stderr[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = []
    for s in data.get("streams", []):
        streams.append(
            StreamInfo(
                index=int(s.get("index", 0)),
                codec_type=str(s.get("codec_type", "")),
                codec_name=str(s.get("codec_name", "")),
                extra={
                    k: s.get(k)
                    for k in ("width", "height", "avg_frame_rate", "sample_rate", "channels")
                    if k in s
                },
            )
        )
    fmt = data.get("format", {})
    dur = fmt.get("duration")
    return MediaProbe(
        path=path,
        format_name=str(fmt.get("format_name", "")),
        duration=float(dur) if dur is not None else None,
        streams=streams,
    )


def _run_ffmpeg(cmd: list[str], *, label: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[-800:]
        raise RuntimeError(f"{label} failed:\n{err}")


def repair_video_container(
    src: Path | str,
    dst: Path | str,
    *,
    progress: ProgressCb | None = None,
) -> Path:
    """Best-effort repair: rebuild timestamps, drop corrupt packets, remux.

    Falls back to re-encoding video (libx264) + AAC if stream-copy fails.
    Does not recover deleted frames from a destroyed bitstream.
    """
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()

    if progress:
        progress("video repair remux", 0.2)

    common = [
        ff,
        "-hide_banner",
        "-y",
        "-err_detect",
        "ignore_err",
        "-fflags",
        "+genpts+igndts+discardcorrupt",
        "-i",
        str(src),
    ]

    # Prefer stream copy into MKV (most tolerant)
    copy_cmd = common + [
        "-map",
        "0",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        str(dst),
    ]
    try:
        _run_ffmpeg(copy_cmd, label="video repair (copy)")
        if progress:
            progress("video repair done (copy)", 0.45)
        return dst
    except RuntimeError:
        if progress:
            progress("video repair copy failed; re-encoding", 0.3)

    reenc = common + [
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    _run_ffmpeg(reenc, label="video repair (reencode)")
    if progress:
        progress("video repair done (reencode)", 0.45)
    return dst


def _vf_denoise_args(denoise: bool) -> list[str]:
    return ["-vf", "hqdn3d=1.5:1.5:2:2"] if denoise else []


def _af_sync_args(sync_tighten: bool) -> list[str]:
    return ["-af", "aresample=async=1:first_pts=0"] if sync_tighten else []


def _mkv_video_codec_args(*, upconvert_video: bool, denoise: bool) -> list[str]:
    if upconvert_video:
        return ["-c:v", "ffv1", "-level", "3", "-g", "1", "-slicecrc", "1"]
    if denoise:
        # Filters require encode; light H.264 when not doing FFV1 master.
        return ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast"]
    return ["-c:v", "copy"]


def _mp4_video_codec_args(*, upconvert_video: bool, denoise: bool) -> list[str]:
    if upconvert_video:
        return [
            "-c:v",
            "libx264",
            "-crf",
            "0",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
        ]
    if denoise:
        return [
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
        ]
    return ["-c:v", "copy"]


def mux_lossless_mkv(
    *,
    video_src: Path,
    audio_flac: Path | None,
    dst: Path,
    upconvert_video: bool,
    copy_audio_from_video: bool = False,
    sync_tighten: bool = False,
    denoise: bool = False,
    progress: ProgressCb | None = None,
) -> Path:
    """Write MKV with optional FFV1 lossless video and FLAC audio."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    if progress:
        progress("mux lossless mkv", 0.75)

    cmd = [ff, "-hide_banner", "-y", "-i", str(video_src)]
    if audio_flac is not None:
        cmd += ["-i", str(audio_flac)]

    cmd += ["-map", "0:v:0"]
    cmd += _vf_denoise_args(denoise)
    cmd += _mkv_video_codec_args(upconvert_video=upconvert_video, denoise=denoise)

    if audio_flac is not None:
        cmd += ["-map", "1:a:0", "-c:a", "flac"]
        cmd += _af_sync_args(sync_tighten)
    elif copy_audio_from_video:
        cmd += ["-map", "0:a:0?"]
        if sync_tighten:
            cmd += ["-c:a", "flac"]
            cmd += _af_sync_args(True)
        else:
            cmd += ["-c:a", "copy"]

    cmd += ["-map_metadata", "0", str(dst)]
    _run_ffmpeg(cmd, label="mux lossless mkv")
    if progress:
        progress("mux done", 0.95)
    return dst


def mux_mp4(
    *,
    video_src: Path,
    audio_wav: Path | None,
    dst: Path,
    upconvert_video: bool,
    sync_tighten: bool = False,
    denoise: bool = False,
    progress: ProgressCb | None = None,
) -> Path:
    """MP4-friendly mux: H.264 (CRF 0 near-lossless) + PCM s24le when possible."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    if progress:
        progress("mux mp4", 0.75)

    cmd = [ff, "-hide_banner", "-y", "-i", str(video_src)]
    if audio_wav is not None:
        cmd += ["-i", str(audio_wav)]

    cmd += ["-map", "0:v:0"]
    cmd += _vf_denoise_args(denoise)
    cmd += _mp4_video_codec_args(upconvert_video=upconvert_video, denoise=denoise)

    if audio_wav is not None:
        cmd += ["-map", "1:a:0", "-c:a", "pcm_s24le"]
        cmd += _af_sync_args(sync_tighten)
    else:
        if sync_tighten:
            cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k"]
            cmd += _af_sync_args(True)
        else:
            cmd += ["-map", "0:a:0?", "-c:a", "copy"]

    cmd += ["-movflags", "+faststart", str(dst)]
    _run_ffmpeg(cmd, label="mux mp4")
    if progress:
        progress("mux done", 0.95)
    return dst


def export_pcm24_wav(path: Path, pcm: np.ndarray, sample_rate: int = 44100) -> Path:
    """Write gap_fill int32 (low 24 bits) as WAV PCM_24 for MP4 mux."""
    import soundfile as sf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(pcm)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if np.issubdtype(arr.dtype, np.integer):
        arr = np.left_shift(np.asarray(arr, dtype=np.int32), 8)
    sf.write(str(path), arr, sample_rate, subtype="PCM_24")
    return path


def with_temp_dir():
    return tempfile.TemporaryDirectory(prefix="upconvert_all_")


# Delivery MP4 presets: shrink size while protecting restored A/V.
# Audio defaults to ALAC (lossless in MP4). Video uses high-quality H.264
# (visually near-transparent); the lossless/master file should be kept.
COMPRESS_PRESETS: dict[str, dict[str, str]] = {
    "transparent": {"crf": "15", "preset": "slow", "audio": "alac"},
    "high": {"crf": "18", "preset": "medium", "audio": "alac"},
    "balanced": {"crf": "20", "preset": "medium", "audio": "aac", "audio_bitrate": "320k"},
}


def compress_delivery_mp4(
    src: Path | str,
    dst: Path | str,
    *,
    quality: str = "transparent",
    progress: ProgressCb | None = None,
) -> Path:
    """Re-encode a master (MKV/MP4) into a compact delivery MP4.

    Preserves restored audio via ALAC (lossless) on transparent/high presets.
    Video uses libx264 at a high CRF quality (not archival lossless — keep the master).
    """
    src = Path(src)
    dst = Path(dst)
    if quality not in COMPRESS_PRESETS:
        raise ValueError(f"quality must be one of {tuple(COMPRESS_PRESETS)}")
    cfg = COMPRESS_PRESETS[quality]
    dst.parent.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    if not info.has_video:
        raise RuntimeError(f"compress_delivery_mp4 requires a video stream: {src.name}")

    if progress:
        progress(f"compress mp4 ({quality})", 0.96)

    ff = ffmpeg_bin()
    cmd = [
        ff,
        "-hide_banner",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-crf",
        cfg["crf"],
        "-preset",
        cfg["preset"],
        "-pix_fmt",
        "yuv420p",
    ]
    if info.has_audio:
        cmd += ["-map", "0:a:0"]
        if cfg["audio"] == "alac":
            cmd += ["-c:a", "alac"]
        else:
            cmd += ["-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "320k")]
    cmd += ["-movflags", "+faststart", "-map_metadata", "0", str(dst)]
    _run_ffmpeg(cmd, label=f"compress delivery mp4 ({quality})")
    if progress:
        progress("compress mp4 done", 0.99)
    return dst


def compress_audio_alac_m4a(
    src: Path | str,
    dst: Path | str,
    *,
    progress: ProgressCb | None = None,
) -> Path:
    """Lossless ALAC wrap of a FLAC/WAV master into .m4a (MP4 audio family)."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("compress alac m4a", 0.96)
    ff = ffmpeg_bin()
    cmd = [
        ff,
        "-hide_banner",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:a:0",
        "-c:a",
        "alac",
        "-map_metadata",
        "0",
        str(dst),
    ]
    _run_ffmpeg(cmd, label="compress alac m4a")
    if progress:
        progress("compress alac m4a done", 0.99)
    return dst
