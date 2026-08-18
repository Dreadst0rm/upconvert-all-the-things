"""Pipeline summary and GUI clarity helpers."""

from __future__ import annotations

from pathlib import Path

from upconvert_all.pipeline import ProcessOptions
from upconvert_all.pipeline_summary import queue_media_kinds, summarize_pipeline
from upconvert_all.presets import (
    PRESET_IDS,
    get_preset,
    match_preset,
    preset_settings,
)


def test_preset_descriptions():
    for pid in PRESET_IDS:
        p = get_preset(pid)
        assert p.description.strip()
        assert p.label.strip()
    assert "lossy" in get_preset("listen-better").description.lower()
    assert "copy" in get_preset("archive-remux").description.lower()
    data = preset_settings("listen-better")
    assert "description" not in data
    assert "label" not in data


def test_summarize_listen_better():
    opts = ProcessOptions(output_dir=Path("out"), **preset_settings("listen-better"))
    text = summarize_pipeline(opts)
    assert "Repair audio (strong)" in text
    assert "Upconvert audio (24-bit" in text
    assert "auto-clarity EQ" in text
    assert "stereo 25%" in text
    assert "Write MKV" in text
    assert "Remux/copy" not in text


def test_summarize_archive_remux():
    opts = ProcessOptions(output_dir=Path("out"), **preset_settings("archive-remux"))
    text = summarize_pipeline(opts)
    assert text.startswith("Remux/copy only")
    assert "no repair, upconvert, or sweetening" in text
    assert "Write MKV" in text


def test_summarize_master_mkv():
    opts = ProcessOptions(output_dir=Path("out"), **preset_settings("master-mkv"))
    text = summarize_pipeline(opts)
    assert "Repair audio (strong) + video" in text
    assert "video lossless" in text
    assert "Enhance" not in text
    assert "Write MKV" in text


def test_summarize_immersive_and_rescue():
    immersive = ProcessOptions(
        output_dir=Path("out"), **preset_settings("immersive-listen")
    )
    text = summarize_pipeline(immersive)
    assert "binaural immersion" in text
    assert "crossfeed" in text
    assert "headphones" in text

    rescue = ProcessOptions(output_dir=Path("out"), **preset_settings("rescue-video"))
    rtext = summarize_pipeline(rescue)
    assert "Repair audio (medium) + video" in rtext
    assert "tighten sync" in rtext


def test_summarize_audio_queue_skips_video_steps():
    opts = ProcessOptions(
        output_dir=Path("out"),
        repair_audio=True,
        repair_video=True,
        upconvert_audio=False,
        upconvert_video=True,
        enhance_audio=False,
        enhance_video=True,
    )
    text = summarize_pipeline(opts, queue_kinds={"audio"})
    assert "Video steps skipped" in text
    mixed = summarize_pipeline(opts, queue_kinds={"audio", "video"})
    assert "Video steps skipped" not in mixed


def test_queue_media_kinds():
    assert queue_media_kinds([Path("a.mp3"), Path("b.wav")]) == {"audio"}
    assert queue_media_kinds([Path("a.mkv"), Path("notes.txt")]) == {"video"}


def test_preset_roundtrip_still_matches():
    for pid in PRESET_IDS:
        assert match_preset(preset_settings(pid)) == pid
