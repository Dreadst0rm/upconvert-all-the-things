"""Smoke tests for formats, lossy repair, and gapfill packing."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from upconvert_all.formats import collect_inputs, media_kind
from upconvert_all.gapfill import gap_fill, pack_bits_to_int24
from upconvert_all.lossy_repair import is_likely_lossy, repair_lossy_pcm


def test_media_kind():
    assert media_kind("a.mp4") == "video"
    assert media_kind("a.mkv") == "video"
    assert media_kind("a.webm") == "video"
    assert media_kind("a.mp3") == "audio"
    assert media_kind("a.flac") == "audio"
    assert media_kind("a.txt") == "unknown"


def test_lossy_suffix():
    assert is_likely_lossy(".mp3")
    assert is_likely_lossy(".aac")
    assert not is_likely_lossy(".flac")
    assert not is_likely_lossy(".wav")


def test_repair_pcm_shape():
    rng = np.random.default_rng(0)
    pcm = (rng.normal(0, 0.1, size=(2048, 2)) * 16000).astype(np.int16)
    out = repair_lossy_pcm(pcm, strength="light", use_torch=False)
    assert out.shape == pcm.shape
    assert out.dtype == np.int16


def test_gap_fill_20_lsb_zero():
    rng = np.random.default_rng(1)
    pcm = rng.integers(-20000, 20000, size=(512, 2), dtype=np.int16)
    out = gap_fill(pcm, output_bits=20, iterations=1, dither="none")
    assert out.shape == pcm.shape
    assert np.all((out & 0xF) == 0)


def test_sbm_dither_changes_output():
    rng = np.random.default_rng(2)
    pcm = rng.integers(-20000, 20000, size=(1024,), dtype=np.int16)
    undithered = gap_fill(pcm, output_bits=24, iterations=1, dither="none")
    dithered = gap_fill(pcm, output_bits=24, iterations=1, dither="sbm")
    assert undithered.shape == dithered.shape
    # SBM+TPDF should not be identical to undithered round for typical material
    assert not np.array_equal(undithered, dithered)


def test_pack_bits():
    samples = np.array([1, -2, 3], dtype=np.int32)
    packed = pack_bits_to_int24(samples, 20)
    assert np.all((packed & 0xF) == 0)


def test_collect_inputs(tmp_path: Path):
    (tmp_path / "a.mp3").write_bytes(b"")
    (tmp_path / "b.avi").write_bytes(b"")
    (tmp_path / "c.txt").write_bytes(b"")
    found = collect_inputs([tmp_path])
    names = {p.name for p in found}
    assert names == {"a.mp3", "b.avi"}


def test_ab_preview_builds_wavs(tmp_path: Path):
    from upconvert_all.pipeline import ProcessOptions, build_ab_preview

    src = Path("smoke_media/tone.mp3")
    if not src.is_file():
        import pytest

        pytest.skip("smoke_media/tone.mp3 missing")
    opts = ProcessOptions(
        output_dir=tmp_path,
        repair_audio=True,
        upconvert_audio=True,
        ml_upscaler=False,
        expand_iterations=1,
        dither="none",
        repair_strength="light",
        native_sample_rate=True,
    )
    result = build_ab_preview(src, opts, out_dir=tmp_path, duration_sec=1.0)
    assert result.source_wav.is_file()
    assert result.processed_wav.is_file()
    assert result.duration_sec > 0
    assert result.sample_rate > 0
    assert result.source_wav.stat().st_size > 0
    assert result.processed_wav.stat().st_size > 0


def test_native_sample_rate_preserved(tmp_path: Path):
    import soundfile as sf

    from upconvert_all.io_audio import load_pcm16
    from upconvert_all.pipeline import ProcessOptions, process_audio_file

    wav = tmp_path / "tone48.wav"
    sr = 48000
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    pcm = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)
    stereo = np.column_stack([pcm, pcm])
    sf.write(str(wav), stereo, sr, subtype="PCM_16")

    loaded, loaded_sr, _meta = load_pcm16(wav, target_sample_rate=None)
    assert loaded_sr == 48000
    assert loaded.shape[0] > 0

    forced, forced_sr, _ = load_pcm16(wav, target_sample_rate=44100)
    assert forced_sr == 44100

    out_dir = tmp_path / "out"
    opts = ProcessOptions(
        output_dir=out_dir,
        repair_audio=False,
        upconvert_audio=False,
        ml_upscaler=False,
        native_sample_rate=True,
    )
    outs = process_audio_file(wav, opts)
    assert outs
    info = sf.info(str(outs[0]))
    assert info.samplerate == 48000


def test_presets_defined_and_match():
    from upconvert_all.presets import (
        DEFAULT_PRESET,
        PRESET_IDS,
        get_preset,
        list_presets,
        match_preset,
        preset_settings,
    )

    assert DEFAULT_PRESET == "listen-better"
    assert len(list_presets()) == len(PRESET_IDS)
    for pid in PRESET_IDS:
        p = get_preset(pid)
        assert p.id == pid
        assert match_preset(preset_settings(pid)) == pid

    archive = preset_settings("archive-remux")
    assert archive["repair_audio"] is False
    assert archive["upconvert_audio"] is False
    assert archive["upconvert_video"] is False
    assert archive["ml_upscaler"] is False
    assert archive["enhance_audio"] is False

    master = preset_settings("master-mkv")
    assert master["upconvert_video"] is True
    assert master["container"] == "mkv"
    assert master["enhance_audio"] is False

    listen = preset_settings("listen-better")
    assert listen["repair_video"] is False
    assert listen["upconvert_audio"] is True
    assert listen["enhance_audio"] is True

    assert "immersive-listen" in PRESET_IDS


def test_cli_preset_override():
    from upconvert_all.cli import _build_parser, _options_from_args

    parser = _build_parser()
    argv = [
        "process",
        "x.mp3",
        "--preset",
        "archive-remux",
        "--repair-audio",
    ]
    args = parser.parse_args(argv)
    opts = _options_from_args(args, argv)
    assert opts.repair_audio is True  # explicit override
    assert opts.upconvert_audio is False  # from archive-remux
    assert opts.repair_video is False
    assert opts.ml_upscaler is False
    assert opts.enhance_audio is False


def test_enhance_mono_identity():
    from upconvert_all.enhance import enhance_audio_pcm

    rng = np.random.default_rng(3)
    pcm = rng.integers(-20000, 20000, size=(4096,), dtype=np.int16)
    out, desc = enhance_audio_pcm(
        pcm,
        subtype="PCM_16",
        sample_rate=44100,
        enhance_audio=True,
        eq_mode="auto-clarity",
        stereo_image_strength=40,
        immersion="binaural",
        crossfeed=True,
    )
    assert out.shape == pcm.shape
    assert out.dtype == np.int16
    assert "Enhance" in desc


def test_enhance_stereo_image_changes_and_peak_safe():
    from upconvert_all.enhance import (
        enhance_audio_pcm,
        pcm_to_float,
        true_peak_ceiling,
    )

    rng = np.random.default_rng(4)
    # Correlated stereo with some side
    t = np.linspace(0, 1, 8000, endpoint=False)
    l = 0.7 * np.sin(2 * np.pi * 440 * t)
    r = 0.7 * np.sin(2 * np.pi * 440 * t + 0.15)
    pcm = (np.column_stack([l, r]) * 30000).astype(np.int16)
    out, desc = enhance_audio_pcm(
        pcm,
        subtype="PCM_16",
        sample_rate=8000,
        enhance_audio=True,
        eq_mode="none",
        stereo_image_strength=50,
        stereo_image_mode="speaker",
        immersion="off",
    )
    assert out.shape == pcm.shape
    assert not np.array_equal(out, pcm)
    assert "image=" in desc
    xf = pcm_to_float(out, subtype="PCM_16")
    assert float(np.max(np.abs(xf))) <= 1.0 + 1e-6

    hot = np.column_stack([l, r]) * 1.5  # exceeds 0 dBFS sample peak
    capped = true_peak_ceiling(hot, sample_rate=8000, ceiling_db=-0.5)
    assert float(np.max(np.abs(capped))) < float(np.max(np.abs(hot)))
    assert float(np.max(np.abs(capped))) <= 10.0 ** (-0.5 / 20.0) + 1e-6


def test_enhance_archive_preset_off():
    from upconvert_all.presets import preset_settings

    archive = preset_settings("archive-remux")
    assert archive["enhance_audio"] is False
    assert archive["enhance_video"] is False
    assert archive["eq_mode"] == "none"
    assert archive["stereo_image_strength"] == 0
    assert archive["immersion"] == "off"
    assert archive["video_sync_tighten"] is False
    assert archive["video_denoise"] is False

    listen = preset_settings("listen-better")
    assert listen["enhance_audio"] is True
    assert listen["eq_mode"] == "auto-clarity"
    assert listen["stereo_image_strength"] > 0

    immersive = preset_settings("immersive-listen")
    assert immersive["immersion"] == "binaural"
    assert immersive["crossfeed"] is True


def test_immersion_binaural_spike():
    """M0 keep signal: binaural immersion alters stereo without exploding peaks."""
    from upconvert_all.enhance import immersion_process, stereo_image

    sr = 44100
    n = sr * 2  # 2s spike clip (scaled-down from 10s for test speed)
    t = np.linspace(0, 2, n, endpoint=False)
    l = 0.4 * np.sin(2 * np.pi * 330 * t)
    r = 0.4 * np.sin(2 * np.pi * 330 * t + 0.2)
    x = np.column_stack([l, r])
    imaged = stereo_image(x, sample_rate=sr, strength=30, mode="speaker")
    immersed = immersion_process(x, sample_rate=sr, mode="binaural", depth=0.4)
    assert imaged.shape == x.shape
    assert immersed.shape == x.shape
    assert not np.allclose(imaged, x)
    assert not np.allclose(immersed, x)
    assert float(np.max(np.abs(immersed))) <= 1.0 + 1e-9


def test_eq_target_curves():
    from upconvert_all.enhance import apply_eq, list_eq_curves

    sr = 44100
    n = 8192
    t = np.linspace(0, n / sr, n, endpoint=False)
    # Broadband-ish: sum of tones across bass / mid / treble
    x = (
        0.25 * np.sin(2 * np.pi * 80 * t)
        + 0.25 * np.sin(2 * np.pi * 440 * t)
        + 0.25 * np.sin(2 * np.pi * 3000 * t)
        + 0.25 * np.sin(2 * np.pi * 8000 * t)
    )
    stereo = np.column_stack([x, x])

    ids = list_eq_curves()
    assert "flat" in ids and "harman" in ids
    assert "diffuse-field" in ids and "equal-loudness" in ids

    flat = apply_eq(stereo, sample_rate=sr, mode="target-curve", curve="flat")
    assert np.allclose(flat, stereo)

    for cid in ids:
        if cid == "flat":
            continue
        y = apply_eq(stereo, sample_rate=sr, mode="target-curve", curve=cid)
        assert y.shape == stereo.shape
        assert not np.allclose(y, stereo, atol=1e-5), cid

    try:
        apply_eq(stereo, sample_rate=sr, mode="target-curve", curve="not-a-curve")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Unknown EQ curve" in str(exc)


def test_preset_option_fields_cover_cli_flags():
    from upconvert_all.presets import CLI_FIELD_FLAGS, PRESET_OPTION_FIELDS

    for field in PRESET_OPTION_FIELDS:
        assert field in CLI_FIELD_FLAGS, field


def test_mux_argv_helpers():
    from upconvert_all.video import (
        _af_sync_args,
        _mkv_video_codec_args,
        _mp4_video_codec_args,
        _vf_denoise_args,
    )

    assert _vf_denoise_args(False) == []
    assert _vf_denoise_args(True) == ["-vf", "hqdn3d=1.5:1.5:2:2"]
    assert _af_sync_args(True) == ["-af", "aresample=async=1:first_pts=0"]
    assert _mkv_video_codec_args(upconvert_video=True, denoise=False)[1] == "ffv1"
    assert _mkv_video_codec_args(upconvert_video=False, denoise=True)[1] == "libx264"
    assert _mkv_video_codec_args(upconvert_video=False, denoise=False) == ["-c:v", "copy"]
    assert "-pix_fmt" in _mp4_video_codec_args(upconvert_video=True, denoise=False)
    assert _mp4_video_codec_args(upconvert_video=False, denoise=False) == ["-c:v", "copy"]
