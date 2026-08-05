"""Supported media extensions and kind detection."""

from __future__ import annotations

from pathlib import Path

VIDEO_SUFFIXES = {".avi", ".mp4", ".mov", ".mkv", ".webm"}
AUDIO_SUFFIXES = {".mp3", ".flac", ".ape", ".aac", ".wav", ".m4a", ".ogg", ".oga"}
ALL_SUFFIXES = VIDEO_SUFFIXES | AUDIO_SUFFIXES

# soundfile/libsndfile typically handles these without ffmpeg
NATIVE_AUDIO = {".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif"}


def media_kind(path: Path | str) -> str:
    """Return 'video', 'audio', or 'unknown'."""
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    return "unknown"


def collect_inputs(paths: list[Path], *, recursive: bool = False) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(p.glob(pattern)):
                if child.is_file() and child.suffix.lower() in ALL_SUFFIXES:
                    found.append(child)
        elif p.is_file() and p.suffix.lower() in ALL_SUFFIXES:
            found.append(p)
    # stable unique
    seen: set[Path] = set()
    out: list[Path] = []
    for f in found:
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
