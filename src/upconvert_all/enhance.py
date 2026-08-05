"""Optional listening enhancement (EQ, stereo image, immersion).

Creative / perceptual processing — not archival recovery or true WFS.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy import signal

from .enhance_eq import (
    EQ_CURVE_IDS,
    EQ_CURVES,
    EqBand,
    EqCurve,
    EqMode,
    apply_eq,
    list_eq_curves,
)

# Re-export EQ API for stable import paths (cli/gui/tests may use enhance.*).
__all__ = [
    "EQ_CURVE_IDS",
    "EQ_CURVES",
    "EqBand",
    "EqCurve",
    "EqMode",
    "DEFAULT_TRUE_PEAK_DB",
    "ImmersionMode",
    "StereoImageMode",
    "apply_eq",
    "crossfeed_bauer",
    "enhance_active",
    "enhance_audio_pcm",
    "float_to_pcm",
    "immersion_process",
    "list_eq_curves",
    "pcm_to_float",
    "stereo_image",
    "true_peak_ceiling",
]

StereoImageMode = Literal["speaker", "headphone"]
ImmersionMode = Literal["off", "binaural", "speaker-wide"]

# Soft ceiling when enhance runs (true-peak / intersample headroom).
DEFAULT_TRUE_PEAK_DB = -0.5


def pcm_to_float(pcm: np.ndarray, *, subtype: str) -> np.ndarray:
    """Convert int16 or packed int24 (low 24 bits) to float64 in [-1, 1]."""
    arr = np.asarray(pcm)
    if subtype == "PCM_24":
        scale = float(1 << 23)
        return np.asarray(arr, dtype=np.float64) / scale
    return np.asarray(arr, dtype=np.float64) / 32768.0


def float_to_pcm(x: np.ndarray, *, subtype: str) -> np.ndarray:
    """Convert float [-1, 1] back to int16 or packed int24."""
    x = np.asarray(x, dtype=np.float64)
    if subtype == "PCM_24":
        scale = float(1 << 23)
        return np.clip(np.rint(x * scale), -(1 << 23), (1 << 23) - 1).astype(np.int32)
    return np.clip(np.rint(x * 32768.0), -32768, 32767).astype(np.int16)


def _ensure_2d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return x.reshape(-1, 1)
    return x


def _soft_limit(x: np.ndarray, peak: float = 0.98) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    if m > peak:
        x = x * (peak / m)
    return x


def true_peak_ceiling(
    x: np.ndarray,
    *,
    sample_rate: int,
    ceiling_db: float = DEFAULT_TRUE_PEAK_DB,
) -> np.ndarray:
    """Scale so 4×-oversampled peak stays under ceiling_db (approx true-peak)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return x
    ceiling = 10.0 ** (ceiling_db / 20.0)
    arr = _ensure_2d(x)
    peaks: list[float] = []
    for c in range(arr.shape[1]):
        ch = arr[:, c]
        # Cheap 4× peak estimate via linear upsample of abs envelope.
        n = ch.size
        up = np.zeros(n * 4, dtype=np.float64)
        up[::4] = ch
        # triangular kernel ≈ linear interp
        kernel = np.array([0.25, 0.5, 0.75, 1.0, 0.75, 0.5, 0.25], dtype=np.float64)
        up = np.convolve(up, kernel, mode="same")
        peaks.append(float(np.max(np.abs(up))))
    tp = max(peaks) if peaks else 0.0
    if tp <= ceiling or tp < 1e-12:
        return x
    return x * (ceiling / tp)



def _ms_reshape(
    left: np.ndarray, right: np.ndarray, side_gain: float
) -> tuple[np.ndarray, np.ndarray]:
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right) * side_gain
    return mid + side, mid - side


def _ambience_blend(
    left: np.ndarray, right: np.ndarray, amount: float, sample_rate: int
) -> tuple[np.ndarray, np.ndarray]:
    """Decorrelated side ambience with a short delayed reflection."""
    if amount <= 1e-6:
        return left, right
    side = 0.5 * (left - right)
    delay = max(1, int(0.012 * sample_rate))
    refl = np.zeros_like(side)
    refl[delay:] = side[:-delay] * 0.55
    # Mild HF damping on reflection
    nyq = 0.5 * sample_rate
    sos = signal.butter(1, min(6000.0, nyq * 0.9) / nyq, btype="low", output="sos")
    refl = signal.sosfilt(sos, refl)
    wet = amount * 0.35
    return left + refl * wet, right - refl * wet


def _xtc_mild(
    left: np.ndarray, right: np.ndarray, amount: float, sample_rate: int
) -> tuple[np.ndarray, np.ndarray]:
    """Approximate speaker crosstalk cancellation (mild FIR-ish IIR)."""
    if amount <= 1e-6:
        return left, right
    # ~200 µs ITD + HF-rolled opposite feed
    delay = max(1, int(0.0002 * sample_rate))
    nyq = 0.5 * sample_rate
    sos = signal.butter(1, min(5000.0, nyq * 0.85) / nyq, btype="low", output="sos")
    gain = 0.35 * amount

    def _feed(src: np.ndarray) -> np.ndarray:
        d = np.zeros_like(src)
        d[delay:] = src[:-delay]
        return signal.sosfilt(sos, d) * gain

    l = left - _feed(right)
    r = right - _feed(left)
    return l, r


def stereo_image(
    x: np.ndarray,
    *,
    sample_rate: int,
    strength: int,
    mode: StereoImageMode = "speaker",
) -> np.ndarray:
    """M/S reshape + ambience; optional mild XTC for speakers."""
    strength = int(np.clip(strength, 0, 100))
    if strength <= 0:
        return x
    arr = _ensure_2d(x)
    if arr.shape[1] < 2:
        return x
    t = strength / 100.0
    side_gain = 1.0 + (0.55 if mode == "speaker" else 0.35) * t
    l, r = _ms_reshape(arr[:, 0], arr[:, 1], side_gain)
    l, r = _ambience_blend(l, r, t, sample_rate)
    if mode == "speaker":
        l, r = _xtc_mild(l, r, t, sample_rate)
    elif mode == "headphone":
        # Light pinna-ish presence shelf instead of XTC
        nyq = 0.5 * sample_rate
        sos = signal.butter(1, min(4000.0, nyq * 0.85) / nyq, btype="high", output="sos")
        lift = 0.08 * t
        l = l + signal.sosfilt(sos, l) * lift
        r = r + signal.sosfilt(sos, r) * lift
    out = arr.copy()
    out[:, 0], out[:, 1] = _soft_limit(np.column_stack([l, r])).T
    return out if x.ndim == 2 else out[:, 0]


def crossfeed_bauer(
    x: np.ndarray,
    *,
    sample_rate: int,
    amount: float = 0.4,
) -> np.ndarray:
    """Bauer-style lowpassed headphone crossfeed."""
    if amount <= 1e-6:
        return x
    arr = _ensure_2d(x)
    if arr.shape[1] < 2:
        return x
    nyq = 0.5 * sample_rate
    sos = signal.butter(1, min(700.0, nyq * 0.4) / nyq, btype="low", output="sos")
    delay = max(1, int(0.0003 * sample_rate))
    l, r = arr[:, 0], arr[:, 1]
    lf = signal.sosfilt(sos, l)
    rf = signal.sosfilt(sos, r)
    ld = np.zeros_like(lf)
    rd = np.zeros_like(rf)
    ld[delay:] = lf[:-delay]
    rd[delay:] = rf[:-delay]
    g = 0.5 * amount
    out = arr.copy()
    out[:, 0] = l + rd * g
    out[:, 1] = r + ld * g
    out = _soft_limit(out)
    return out if x.ndim == 2 else out[:, 0]


def immersion_process(
    x: np.ndarray,
    *,
    sample_rate: int,
    mode: ImmersionMode,
    depth: float = 0.35,
) -> np.ndarray:
    """WFS-inspired stereo/binaural immersion (2-ch only; not true WFS)."""
    if mode == "off":
        return x
    arr = _ensure_2d(x)
    if arr.shape[1] < 2:
        return x
    depth = float(np.clip(depth, 0.0, 1.0))
    sr = int(sample_rate)
    l0, r0 = arr[:, 0], arr[:, 1]
    mid = 0.5 * (l0 + r0)

    # Place L/R on a virtual arc via ITD + ILD
    itd = max(1, int((0.00025 + 0.00035 * depth) * sr))
    ild = 10.0 ** ((-1.5 - 2.0 * depth) / 20.0)

    def _delay(sig: np.ndarray, d: int) -> np.ndarray:
        out = np.zeros_like(sig)
        if d < sig.size:
            out[d:] = sig[:-d]
        return out

    if mode == "binaural":
        # Contralateral: delayed + attenuated opposite channel + early reflection
        l = l0 * (1.0 - 0.15 * depth) + _delay(r0, itd) * ild * 0.55
        r = r0 * (1.0 - 0.15 * depth) + _delay(l0, itd) * ild * 0.55
        er_d = max(1, int(0.008 * sr))
        nyq = 0.5 * sr
        sos = signal.butter(1, min(4500.0, nyq * 0.85) / nyq, btype="low", output="sos")
        er = signal.sosfilt(sos, mid)
        er = _delay(er, er_d) * (0.18 * depth)
        l = l + er
        r = r + er * 0.92
        # Slight side expand for stage width
        l, r = _ms_reshape(l, r, 1.0 + 0.25 * depth)
    else:
        # speaker-wide: widen + deeper ambience, no binaural ITD
        l, r = _ms_reshape(l0, r0, 1.0 + 0.7 * depth)
        l, r = _ambience_blend(l, r, 0.5 + 0.5 * depth, sr)
        l, r = _xtc_mild(l, r, 0.4 * depth, sr)

    out = arr.copy()
    out[:, 0], out[:, 1] = _soft_limit(np.column_stack([l, r])).T
    return out if x.ndim == 2 else out[:, 0]


def enhance_active(
    *,
    enhance_audio: bool,
    eq_mode: str,
    stereo_image_strength: int,
    immersion: str,
    crossfeed: bool,
) -> bool:
    if not enhance_audio:
        return False
    return (
        eq_mode != "none"
        or int(stereo_image_strength) > 0
        or immersion != "off"
        or crossfeed
    )


def enhance_audio_pcm(
    pcm: np.ndarray,
    *,
    subtype: str,
    sample_rate: int,
    enhance_audio: bool = False,
    eq_mode: EqMode | str = "none",
    eq_curve: EqCurve | str = "flat",
    stereo_image_strength: int = 0,
    stereo_image_mode: StereoImageMode | str = "speaker",
    immersion: ImmersionMode | str = "off",
    immersion_depth: float = 0.35,
    crossfeed: bool = False,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
) -> tuple[np.ndarray, str]:
    """Run enhance chain on PCM; returns (pcm, description fragment)."""
    if not enhance_active(
        enhance_audio=enhance_audio,
        eq_mode=str(eq_mode),
        stereo_image_strength=int(stereo_image_strength),
        immersion=str(immersion),
        crossfeed=crossfeed,
    ):
        return pcm, ""

    x = pcm_to_float(pcm, subtype=subtype)
    parts: list[str] = []

    if eq_mode != "none":
        x = apply_eq(
            x,
            sample_rate=sample_rate,
            mode=eq_mode,  # type: ignore[arg-type]
            curve=eq_curve,  # type: ignore[arg-type]
        )
        parts.append(f"eq={eq_mode}" + (f"/{eq_curve}" if eq_mode == "target-curve" else ""))

    if int(stereo_image_strength) > 0:
        x = stereo_image(
            x,
            sample_rate=sample_rate,
            strength=int(stereo_image_strength),
            mode=stereo_image_mode,  # type: ignore[arg-type]
        )
        parts.append(f"image={stereo_image_mode}:{int(stereo_image_strength)}")

    if immersion != "off":
        x = immersion_process(
            x,
            sample_rate=sample_rate,
            mode=immersion,  # type: ignore[arg-type]
            depth=float(immersion_depth),
        )
        parts.append(f"immersion={immersion}:{float(immersion_depth):.2f}")

    if crossfeed:
        x = crossfeed_bauer(x, sample_rate=sample_rate)
        parts.append("crossfeed")

    x = true_peak_ceiling(x, sample_rate=sample_rate, ceiling_db=true_peak_db)
    parts.append(f"truepeak<={true_peak_db:.1f}dB")

    desc = (
        "Enhance (perceptual, not archival): " + ", ".join(parts) + ". "
        "Not true WFS or studio holography."
    )
    return float_to_pcm(x, subtype=subtype), desc
