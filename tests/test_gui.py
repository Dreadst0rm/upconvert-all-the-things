"""Offscreen GUI smoke tests for clarity layout and option mapping."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402
except ImportError as exc:
    pytest.skip(f"PySide6/Qt not usable: {exc}", allow_module_level=True)

from upconvert_all.ml_upscaler import ml_available  # noqa: E402
from upconvert_all.presets import (  # noqa: E402
    CUSTOM_ID,
    DEFAULT_PRESET,
    PRESET_IDS,
    PRESET_OPTION_FIELDS,
    get_preset,
    preset_settings,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def window(qapp):
    from PySide6.QtCore import QSettings

    from upconvert_all.gui import MainWindow, _SETTINGS_APP, _SETTINGS_ORG

    QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue("showAdvanced", False)
    win = MainWindow()
    win.chk_advanced.setChecked(False)
    win.show()
    yield win
    win.close()


def _expected_options(preset_id: str) -> dict:
    expected = preset_settings(preset_id)
    if not ml_available():
        expected["ml_upscaler"] = False
    return expected


def test_default_preset_and_simple_mode(window):
    assert window.preset.currentData() == DEFAULT_PRESET
    desc = get_preset(DEFAULT_PRESET).description
    assert window._preset_desc.text() == desc
    assert window._custom_note.isHidden()
    assert not window.chk_advanced.isChecked()
    assert window._repair_nested.isHidden()
    assert window._up_nested.isHidden()
    assert window._enh_a_nested.isHidden()
    assert window._honesty_full.isHidden()
    summary = window._summary.text()
    assert "Repair audio" in summary
    assert "Write MKV" in summary


def test_plain_language_combo_labels(window):
    assert window.dither.currentText().startswith("SBM")
    assert window.dither.currentData() == "sbm"
    assert "24-bit" in window.bits.currentText()
    assert window.bits.currentData() == 24
    assert "clarity" in window.eq_mode.currentText().lower()
    assert window.eq_mode.currentData() == "auto-clarity"
    assert "lossless" in window.chk_up_v.text().lower()
    assert "delivery MP4" in window.chk_compress.text()


def test_advanced_nests_under_parent_stage(window):
    window.chk_advanced.setChecked(True)
    assert not window._repair_nested.isHidden()  # listen-better repairs audio
    assert not window._up_nested.isHidden()
    assert not window._enh_a_nested.isHidden()
    assert window._enh_v_nested.isHidden()  # enhance video off
    assert not window._out_nested.isHidden()

    window.chk_repair_a.setChecked(False)
    assert window.preset.currentData() == CUSTOM_ID
    assert not window._custom_note.isHidden()
    assert window._repair_nested.isHidden()

    window.chk_advanced.setChecked(False)
    assert window._up_nested.isHidden()


def test_eq_curve_hidden_unless_target_curve(window):
    window.chk_advanced.setChecked(True)
    assert window._eq_curve_row.isHidden()
    idx = window.eq_mode.findData("target-curve")
    window.eq_mode.setCurrentIndex(idx)
    assert not window._eq_curve_row.isHidden()


def test_gui_presets_map_to_process_options(window):
    for pid in PRESET_IDS:
        window._apply_preset(pid)
        opts = window._options()
        expected = _expected_options(pid)
        for field in PRESET_OPTION_FIELDS:
            got = getattr(opts, field)
            assert got == expected[field], f"{pid}.{field}: {got!r} != {expected[field]!r}"
        assert window.preset.currentData() == pid
        assert window._preset_desc.text() == get_preset(pid).description


def test_archive_summary_and_about_limits(window):
    window._apply_preset("archive-remux")
    assert "Remux/copy only" in window._summary.text()
    window._limits_btn.setChecked(True)
    assert not window._honesty_full.isHidden()


def test_audio_queue_annotates_video_steps(window):
    window._apply_preset("rescue-video")
    window.list.addItem("track.mp3")
    assert "Video steps skipped" in window._summary.text()
