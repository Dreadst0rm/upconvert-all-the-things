"""Load 16-bit PCM from audio files (soundfile + ffmpeg fallback).

By default keeps the source sample rate. Pass target_sample_rate=44100 to force CD rate.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .formats import AUDIO_SUFFIXES, NATIVE_AUDIO

# Legacy / fallback rate when probing fails or caller forces CD rate.
SAMPLE_RATE = 44100


@dataclass
class SourceMeta:
    path: Path
    album: str | None = None
    artist: str | None = None
    title: str | None = None
    track_number: int | None = None
    track_total: int | None = None
    backend: str = "unknown"
    notes: list[str] = field(default_factory=list)


@dataclass
class AudioClip:
    """Decoded PCM ready for repair / expand."""

    pcm: np.ndarray  # int16 (n, 2)
    sample_rate: int = SAMPLE_RATE
    source: Path | None = None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def probe_audio_sample_rate(path: Path | str) -> int | None:
    """Return first audio stream sample rate, or None if unknown."""
    path = Path(path)
    if not ffprobe_available():
        return None
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "csv=p=0",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        rate = int(float(line[0].strip()))
    except ValueError:
        return None
    return rate if rate > 0 else None


def read_file_tags(path: Path) -> SourceMeta:
    meta = SourceMeta(path=path)
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path), easy=True)
        if audio is None:
            return meta

        def _first(key: str) -> str | None:
            vals = audio.get(key)
            if not vals:
                return None
            return str(vals[0]).strip() or None

        meta.album = _first("album")
        meta.artist = _first("artist") or _first("albumartist")
        meta.title = _first("title")
        track = _first("tracknumber")
        if track:
            part = track.split("/")[0].strip()
            if part.isdigit():
                meta.track_number = int(part)
            if "/" in track:
                total = track.split("/", 1)[1].strip()
                if total.isdigit():
                    meta.track_total = int(total)
    except Exception as exc:
        meta.notes.append(f"tag-read-skipped:{exc}")
    return meta


def _normalize_pcm(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.dtype != np.int16:
        if np.issubdtype(arr.dtype, np.floating):
            clipped = np.clip(arr, -1.0, 1.0 - 1.0 / 32768.0)
            arr = np.round(clipped * 32768.0).astype(np.int16)
        else:
            arr = np.clip(arr, -32768, 32767).astype(np.int16)
    if arr.shape[1] > 2:
        arr = arr[:, :2]
    elif arr.shape[1] == 1:
        arr = np.column_stack([arr[:, 0], arr[:, 0]])
    return np.ascontiguousarray(arr)


def _load_soundfile(path: Path) -> tuple[np.ndarray, int, str]:
    import soundfile as sf

    with sf.SoundFile(str(path)) as f:
        subtype = (f.subtype or "").upper()
        fmt = f.format or "unknown"
        if "PCM_16" in subtype or subtype in {"PCM_S8", "PCM_U8"}:
            data = f.read(dtype="int16", always_2d=True)
        else:
            data = f.read(dtype="float64", always_2d=True)
        sr = int(f.samplerate)
    return _normalize_pcm(data), sr, f"soundfile:{fmt}/{subtype}"


def _resample(pcm: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr:
        return pcm
    from scipy import signal

    n_out = int(round(pcm.shape[0] * target_sr / sr))
    outs = []
    for c in range(pcm.shape[1]):
        outs.append(
            signal.resample(pcm[:, c].astype(np.float64), n_out).astype(np.float64)
        )
    stacked = np.column_stack(outs)
    clipped = np.clip(stacked, -32768, 32767)
    return clipped.astype(np.int16)


def _load_ffmpeg(
    path: Path,
    *,
    sample_rate: int | None = None,
) -> tuple[np.ndarray, int, str]:
    if not ffmpeg_available():
        raise RuntimeError(
            f"ffmpeg not found on PATH; install ffmpeg to decode {path.suffix}"
        )
    native = probe_audio_sample_rate(path) or SAMPLE_RATE
    out_sr = int(sample_rate) if sample_rate is not None else int(native)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "2",
        "-ar",
        str(out_sr),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"ffmpeg decode failed for {path.name}: {err}")
    raw = np.frombuffer(proc.stdout, dtype=np.int16)
    if raw.size == 0:
        raise RuntimeError(f"ffmpeg produced empty audio for {path.name}")
    if raw.size % 2:
        raw = raw[:-1]
    pcm = raw.reshape(-1, 2)
    return pcm, out_sr, f"ffmpeg:s16le@{out_sr}"


def load_pcm16(
    path: Path | str,
    *,
    force_ffmpeg: bool = False,
    target_sample_rate: int | None = None,
) -> tuple[np.ndarray, int, SourceMeta]:
    """Decode stereo int16 PCM.

    target_sample_rate=None keeps the source rate (default).
    Pass 44100 (or another rate) to resample.
    """
    path = Path(path)
    meta = read_file_tags(path)
    suffix = path.suffix.lower()

    use_ffmpeg = force_ffmpeg or suffix not in NATIVE_AUDIO
    if use_ffmpeg and not ffmpeg_available() and suffix in NATIVE_AUDIO:
        use_ffmpeg = False

    if use_ffmpeg:
        pcm, sr, backend = _load_ffmpeg(path, sample_rate=target_sample_rate)
    else:
        try:
            pcm, sr, backend = _load_soundfile(path)
            if target_sample_rate is not None and sr != target_sample_rate:
                if ffmpeg_available():
                    pcm, sr, backend = _load_ffmpeg(
                        path, sample_rate=target_sample_rate
                    )
                else:
                    pcm = _resample(pcm, sr, target_sample_rate)
                    sr = target_sample_rate
                    backend += f"+scipy-resample@{sr}"
        except Exception:
            if not ffmpeg_available():
                raise
            pcm, sr, backend = _load_ffmpeg(path, sample_rate=target_sample_rate)

    meta.backend = backend
    if meta.title is None:
        meta.title = path.stem
    return pcm, sr, meta


def load_pcm16_44100(
    path: Path | str,
    *,
    force_ffmpeg: bool = False,
) -> tuple[np.ndarray, SourceMeta]:
    """Backward-compatible loader that always resamples to 44.1 kHz."""
    pcm, _sr, meta = load_pcm16(
        path, force_ffmpeg=force_ffmpeg, target_sample_rate=SAMPLE_RATE
    )
    return pcm, meta


def load_audio_clip(
    path: Path | str,
    *,
    force_ffmpeg: bool = False,
    target_sample_rate: int | None = None,
) -> tuple[AudioClip, SourceMeta]:
    pcm, sr, meta = load_pcm16(
        path, force_ffmpeg=force_ffmpeg, target_sample_rate=target_sample_rate
    )
    return AudioClip(pcm=pcm, sample_rate=sr, source=Path(path)), meta


def load_audio_segment(
    path: Path | str,
    *,
    start_sec: float = 0.0,
    duration_sec: float = 15.0,
    target_sample_rate: int | None = None,
) -> tuple[AudioClip, SourceMeta]:
    """Decode a short stereo 16-bit segment (audio or video)."""
    path = Path(path)
    if not ffmpeg_available():
        clip, meta = load_audio_clip(path, target_sample_rate=target_sample_rate)
        n = int(round(duration_sec * clip.sample_rate))
        i0 = int(round(max(0.0, start_sec) * clip.sample_rate))
        pcm = clip.pcm[i0 : i0 + n]
        if pcm.size == 0:
            raise RuntimeError(f"empty audio segment for {path.name}")
        return AudioClip(pcm=pcm, sample_rate=clip.sample_rate, source=path), meta

    meta = read_file_tags(path)
    start = max(0.0, float(start_sec))
    dur = max(0.1, float(duration_sec))
    native = probe_audio_sample_rate(path) or SAMPLE_RATE
    out_sr = int(target_sample_rate) if target_sample_rate is not None else int(native)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(path),
        "-vn",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "2",
        "-ar",
        str(out_sr),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"ffmpeg segment failed for {path.name}: {err}")
    raw = np.frombuffer(proc.stdout, dtype=np.int16)
    if raw.size == 0:
        raise RuntimeError(f"no audio in segment for {path.name}")
    if raw.size % 2:
        raw = raw[:-1]
    pcm = raw.reshape(-1, 2)
    meta.backend = f"ffmpeg:segment@{start:.1f}s+{dur:.1f}s@{out_sr}Hz"
    if meta.title is None:
        meta.title = path.stem
    return AudioClip(pcm=pcm, sample_rate=out_sr, source=path), meta


def extract_audio_from_video(
    path: Path | str,
    *,
    target_sample_rate: int | None = None,
) -> tuple[AudioClip, SourceMeta]:
    """Decode first audio stream from a video container to 16-bit stereo."""
    return load_audio_clip(
        path, force_ffmpeg=True, target_sample_rate=target_sample_rate
    )


def is_supported_audio(path: Path | str) -> bool:
    return Path(path).suffix.lower() in AUDIO_SUFFIXES
