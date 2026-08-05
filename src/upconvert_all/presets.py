"""Named process presets shared by GUI and CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

PresetId = Literal[
    "listen-better",
    "rescue-video",
    "archive-remux",
    "master-mkv",
    "immersive-listen",
]

CUSTOM_ID = "custom"
DEFAULT_PRESET: PresetId = "listen-better"

PRESET_IDS: tuple[PresetId, ...] = (
    "listen-better",
    "rescue-video",
    "archive-remux",
    "master-mkv",
    "immersive-listen",
)

_ENHANCE_KEYS = (
    "enhance_audio",
    "enhance_video",
    "eq_mode",
    "eq_curve",
    "stereo_image_strength",
    "stereo_image_mode",
    "immersion",
    "immersion_depth",
    "crossfeed",
    "video_sync_tighten",
    "video_denoise",
)

# Single ordered list of ProcessOptions fields controlled by presets / match_preset.
PRESET_OPTION_FIELDS: tuple[str, ...] = (
    "repair_audio",
    "repair_video",
    "upconvert_audio",
    "upconvert_video",
    "repair_strength",
    "output_bits",
    "ml_upscaler",
    "expand_iterations",
    "dither",
    "flac_level",
    "container",
    "compress_mp4",
    "compress_quality",
    "native_sample_rate",
    *_ENHANCE_KEYS,
)

# argparse Namespace attribute when it differs from ProcessOptions field name.
CLI_ARG_ATTR: dict[str, str] = {
    "output_bits": "bits",
}


@dataclass(frozen=True)
class PresetProfile:
    """Subset of ProcessOptions (+ display label) controlled by a preset."""

    id: PresetId
    label: str
    repair_audio: bool
    repair_video: bool
    upconvert_audio: bool
    upconvert_video: bool
    repair_strength: str
    output_bits: int
    ml_upscaler: bool
    expand_iterations: int
    dither: str
    flac_level: int
    container: str
    compress_mp4: bool
    compress_quality: str
    native_sample_rate: bool
    enhance_audio: bool = False
    enhance_video: bool = False
    eq_mode: str = "none"
    eq_curve: str = "flat"
    stereo_image_strength: int = 0
    stereo_image_mode: str = "speaker"
    immersion: str = "off"
    immersion_depth: float = 0.35
    crossfeed: bool = False
    video_sync_tighten: bool = False
    video_denoise: bool = False


_PRESETS: dict[str, PresetProfile] = {
    "listen-better": PresetProfile(
        id="listen-better",
        label="Listen better",
        repair_audio=True,
        repair_video=False,
        upconvert_audio=True,
        upconvert_video=False,
        repair_strength="strong",
        output_bits=24,
        ml_upscaler=True,
        expand_iterations=5,
        dither="sbm",
        flac_level=5,
        container="mkv",
        compress_mp4=False,
        compress_quality="transparent",
        native_sample_rate=True,
        enhance_audio=True,
        eq_mode="auto-clarity",
        stereo_image_strength=25,
        stereo_image_mode="speaker",
        immersion="off",
        crossfeed=False,
    ),
    "rescue-video": PresetProfile(
        id="rescue-video",
        label="Rescue video",
        repair_audio=True,
        repair_video=True,
        upconvert_audio=True,
        upconvert_video=False,
        repair_strength="medium",
        output_bits=24,
        ml_upscaler=True,
        expand_iterations=5,
        dither="sbm",
        flac_level=5,
        container="mkv",
        compress_mp4=False,
        compress_quality="transparent",
        native_sample_rate=True,
        enhance_audio=True,
        enhance_video=True,
        eq_mode="auto-clarity",
        stereo_image_strength=15,
        stereo_image_mode="speaker",
        immersion="off",
        video_sync_tighten=True,
        video_denoise=False,
    ),
    "archive-remux": PresetProfile(
        id="archive-remux",
        label="Archive remux",
        repair_audio=False,
        repair_video=False,
        upconvert_audio=False,
        upconvert_video=False,
        repair_strength="light",
        output_bits=24,
        ml_upscaler=False,
        expand_iterations=5,
        dither="none",
        flac_level=5,
        container="mkv",
        compress_mp4=False,
        compress_quality="transparent",
        native_sample_rate=True,
        enhance_audio=False,
        enhance_video=False,
        eq_mode="none",
        stereo_image_strength=0,
        immersion="off",
        crossfeed=False,
        video_sync_tighten=False,
        video_denoise=False,
    ),
    "master-mkv": PresetProfile(
        id="master-mkv",
        label="Master MKV",
        repair_audio=True,
        repair_video=True,
        upconvert_audio=True,
        upconvert_video=True,
        repair_strength="strong",
        output_bits=24,
        ml_upscaler=True,
        expand_iterations=5,
        dither="sbm",
        flac_level=5,
        container="mkv",
        compress_mp4=False,
        compress_quality="transparent",
        native_sample_rate=True,
        enhance_audio=False,
        enhance_video=False,
        eq_mode="none",
        stereo_image_strength=0,
        immersion="off",
        crossfeed=False,
        video_sync_tighten=False,
        video_denoise=False,
    ),
    "immersive-listen": PresetProfile(
        id="immersive-listen",
        label="Immersive listen",
        repair_audio=True,
        repair_video=False,
        upconvert_audio=True,
        upconvert_video=False,
        repair_strength="strong",
        output_bits=24,
        ml_upscaler=True,
        expand_iterations=5,
        dither="sbm",
        flac_level=5,
        container="mkv",
        compress_mp4=False,
        compress_quality="transparent",
        native_sample_rate=True,
        enhance_audio=True,
        eq_mode="auto-clarity",
        eq_curve="harman",
        stereo_image_strength=20,
        stereo_image_mode="headphone",
        immersion="binaural",
        immersion_depth=0.4,
        crossfeed=True,
    ),
}


def list_presets() -> list[PresetProfile]:
    return [_PRESETS[pid] for pid in PRESET_IDS]


def get_preset(preset_id: str) -> PresetProfile:
    try:
        return _PRESETS[preset_id]
    except KeyError as exc:
        raise ValueError(f"Unknown preset: {preset_id}") from exc


def preset_settings(preset_id: str) -> dict[str, Any]:
    """ProcessOptions field kwargs from a preset (excludes id/label)."""
    p = get_preset(preset_id)
    data = asdict(p)
    data.pop("id")
    data.pop("label")
    return data


def match_preset(settings: dict[str, Any]) -> str | None:
    """Return preset id if `settings` matches a profile, else None."""
    for pid in PRESET_IDS:
        profile = _PRESETS[pid]
        if all(settings.get(k) == getattr(profile, k) for k in PRESET_OPTION_FIELDS):
            return pid
    return None


def coerce_preset_field(field: str, value: Any) -> Any:
    """Normalize values that CLI/GUI may pass with wider types."""
    if field == "expand_iterations":
        return max(1, int(value))
    if field == "stereo_image_strength":
        return max(0, min(100, int(value)))
    if field == "immersion_depth":
        return float(max(0.0, min(1.0, float(value))))
    if field == "output_bits":
        return int(value)
    if field == "flac_level":
        return int(value)
    return value


def pick_preset_option_values(pick, args) -> dict[str, Any]:
    """Build ProcessOptions kwargs for PRESET_OPTION_FIELDS via pick(field, arg_val)."""
    out: dict[str, Any] = {}
    for field in PRESET_OPTION_FIELDS:
        attr = CLI_ARG_ATTR.get(field, field)
        out[field] = coerce_preset_field(field, pick(field, getattr(args, attr)))
    return out


# CLI tokens that override a given ProcessOptions field after --preset.
CLI_FIELD_FLAGS: dict[str, tuple[str, ...]] = {
    "repair_audio": ("--repair-audio", "--no-repair-audio"),
    "repair_video": ("--repair-video", "--no-repair-video"),
    "upconvert_audio": ("--upconvert-audio", "--no-upconvert-audio"),
    "upconvert_video": ("--upconvert-video", "--no-upconvert-video"),
    "repair_strength": ("--repair-strength",),
    "output_bits": ("--bits",),
    "ml_upscaler": ("--ml-upscaler", "--no-ml-upscaler"),
    "expand_iterations": ("--upconvert-iterations", "--expand-iterations"),
    "dither": ("--dither",),
    "flac_level": ("--flac-level",),
    "container": ("--container",),
    "compress_mp4": ("--compress-mp4", "--no-compress-mp4"),
    "compress_quality": ("--compress-quality",),
    "native_sample_rate": ("--native-sample-rate", "--no-native-sample-rate"),
    "enhance_audio": ("--enhance-audio", "--no-enhance-audio"),
    "enhance_video": ("--enhance-video", "--no-enhance-video"),
    "eq_mode": ("--eq-mode",),
    "eq_curve": ("--eq-curve",),
    "stereo_image_strength": ("--stereo-image",),
    "stereo_image_mode": ("--stereo-image-mode",),
    "immersion": ("--immersion",),
    "immersion_depth": ("--immersion-depth",),
    "crossfeed": ("--crossfeed", "--no-crossfeed"),
    "video_sync_tighten": ("--video-sync-tighten", "--no-video-sync-tighten"),
    "video_denoise": ("--video-denoise", "--no-video-denoise"),
}


def cli_field_explicit(argv: list[str], field: str) -> bool:
    flags = CLI_FIELD_FLAGS.get(field, ())
    return any(tok in argv for tok in flags)
