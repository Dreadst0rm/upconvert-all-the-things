"""Multi-band target EQ and auto-clarity (enhance stage).

Inspired approximations — not calibrated Harman/DF/ISO lab dumps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import signal

EqMode = Literal["none", "auto-clarity", "target-curve"]
EqBandKind = Literal["shelf_low", "shelf_high", "peak"]
EqCurve = Literal[
    "flat",
    "harman",
    "diffuse-field",
    "equal-loudness",
    "warm",
    "analytical",
    "vocal-presence",
    "small-speaker",
]


@dataclass(frozen=True)
class EqBand:
    """One parametric/shelf band. Gains are mild inspired targets, not lab dumps."""

    kind: EqBandKind
    freq_hz: float
    gain_db: float
    q: float = 0.707


# Inspired multi-band approximations — not calibrated Harman/DF/ISO measurements.
EQ_CURVES: dict[str, tuple[EqBand, ...]] = {
    "flat": (),
    "harman": (
        EqBand("shelf_low", 105.0, 3.5, 0.7),
        EqBand("peak", 180.0, 1.2, 0.9),
        EqBand("peak", 2500.0, -1.0, 1.2),
        EqBand("shelf_high", 8000.0, -1.2, 0.7),
    ),
    "diffuse-field": (
        EqBand("shelf_low", 100.0, 0.8, 0.7),
        EqBand("peak", 3000.0, 1.5, 1.0),
        EqBand("shelf_high", 7000.0, 3.0, 0.7),
    ),
    "equal-loudness": (
        EqBand("shelf_low", 80.0, 4.0, 0.7),
        EqBand("peak", 500.0, -2.0, 0.8),
        EqBand("peak", 2500.0, -1.0, 1.0),
        EqBand("shelf_high", 9000.0, 3.5, 0.7),
    ),
    "warm": (
        EqBand("shelf_low", 120.0, 3.0, 0.7),
        EqBand("peak", 350.0, 1.5, 0.9),
        EqBand("shelf_high", 6000.0, -2.5, 0.7),
    ),
    "analytical": (
        EqBand("shelf_low", 100.0, -1.5, 0.7),
        EqBand("peak", 1800.0, 1.8, 1.1),
        EqBand("peak", 4500.0, 1.0, 1.2),
        EqBand("shelf_high", 10000.0, 0.5, 0.7),
    ),
    "vocal-presence": (
        EqBand("shelf_low", 100.0, -0.5, 0.7),
        EqBand("peak", 300.0, -1.5, 0.9),
        EqBand("peak", 1800.0, 2.5, 1.0),
        EqBand("peak", 3200.0, 1.5, 1.2),
    ),
    "small-speaker": (
        EqBand("shelf_low", 90.0, 4.5, 0.7),
        EqBand("peak", 200.0, 1.5, 0.9),
        EqBand("peak", 2800.0, 2.0, 1.0),
        EqBand("shelf_high", 7000.0, 1.5, 0.7),
    ),
}

EQ_CURVE_IDS: tuple[str, ...] = tuple(EQ_CURVES.keys())


def list_eq_curves() -> tuple[str, ...]:
    """Stable EQ curve IDs for CLI/GUI."""
    return EQ_CURVE_IDS


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


def _rbj_biquad_sos(
    kind: EqBandKind,
    freq_hz: float,
    gain_db: float,
    q: float,
    sample_rate: int,
) -> np.ndarray | None:
    """RBJ Audio EQ Cookbook biquad as one SOS row (shape 1×6)."""
    if abs(gain_db) < 0.05:
        return None
    sr = float(sample_rate)
    nyq = 0.5 * sr
    f0 = float(np.clip(freq_hz, 20.0, nyq * 0.95))
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * max(q, 0.1))

    if kind == "peak":
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / A
    elif kind == "shelf_low":
        two_sqrt_a_alpha = 2.0 * np.sqrt(A) * alpha
        b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
        a0 = (A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha
        a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
        a2 = (A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha
    elif kind == "shelf_high":
        two_sqrt_a_alpha = 2.0 * np.sqrt(A) * alpha
        b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
        a0 = (A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha
        a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
        a2 = (A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha
    else:
        raise ValueError(f"Unknown EQ band kind: {kind}")

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def _curve_sos(curve: str, sample_rate: int) -> np.ndarray | None:
    if curve not in EQ_CURVES:
        raise ValueError(
            f"Unknown EQ curve: {curve!r}. Choose from: {', '.join(EQ_CURVE_IDS)}"
        )
    bands = EQ_CURVES[curve]
    if not bands:
        return None
    rows: list[np.ndarray] = []
    for band in bands:
        row = _rbj_biquad_sos(
            band.kind, band.freq_hz, band.gain_db, band.q, sample_rate
        )
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    return np.vstack(rows)


def apply_eq(
    x: np.ndarray,
    *,
    sample_rate: int,
    mode: EqMode,
    curve: EqCurve | str = "flat",
) -> np.ndarray:
    """Perceptual EQ: auto-clarity dips or multi-band target curves."""
    if mode == "none":
        return x
    arr = _ensure_2d(x)
    sr = int(sample_rate)
    nyq = 0.5 * sr
    out = arr.copy()

    if mode == "target-curve":
        sos = _curve_sos(str(curve), sr)
        if sos is None:
            return x
        for c in range(out.shape[1]):
            out[:, c] = signal.sosfilt(sos, out[:, c])
        return _soft_limit(out if x.ndim == 2 else out[:, 0])

    # auto-clarity: mild mid scoop around dense band + slight presence lift
    for c in range(out.shape[1]):
        y = out[:, c]

        def _band_rms(sig: np.ndarray, lo: float, hi: float) -> float:
            lo_n = max(lo / nyq, 1e-4)
            hi_n = min(hi / nyq, 0.99)
            if hi_n <= lo_n:
                return 0.0
            sos_b = signal.butter(2, [lo_n, hi_n], btype="band", output="sos")
            return float(np.sqrt(np.mean(signal.sosfilt(sos_b, sig) ** 2) + 1e-18))

        mid = _band_rms(y, 250.0, 800.0)
        presence = _band_rms(y, 2000.0, 5000.0)
        ratio = mid / max(presence, 1e-9)
        dip = float(np.clip((ratio - 1.2) * 0.8, 0.0, 2.5))  # dB
        lift = float(np.clip((1.0 / max(ratio, 0.5) - 0.7) * 0.6, 0.0, 1.5))
        if dip > 0.05:
            sos_d = signal.butter(
                2,
                [min(300.0, nyq * 0.3) / nyq, min(700.0, nyq * 0.5) / nyq],
                btype="band",
                output="sos",
            )
            band = signal.sosfilt(sos_d, y)
            y = y - band * (1.0 - 10.0 ** (-dip / 20.0))
        if lift > 0.05:
            sos_h = signal.butter(
                1, min(3000.0, nyq * 0.8) / nyq, btype="high", output="sos"
            )
            high = signal.sosfilt(sos_h, y)
            y = y + high * (10.0 ** (lift / 20.0) - 1.0)
        out[:, c] = y
    return _soft_limit(out if x.ndim == 2 else out[:, 0])
