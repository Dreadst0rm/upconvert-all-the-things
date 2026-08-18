"""PySide6 GUI for selective media repair + upconvert."""

from __future__ import annotations

import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .enhance import list_eq_curves
from .formats import ALL_SUFFIXES, collect_inputs
from .ml_upscaler import ml_available
from .pipeline import ProcessOptions, build_ab_preview, process_file
from .pipeline_summary import queue_media_kinds, summarize_pipeline
from .presets import (
    CUSTOM_ID,
    DEFAULT_PRESET,
    PRESET_OPTION_FIELDS,
    get_preset,
    list_presets,
)

HONESTY = (
    "Best-effort repair/upconvert only. Does not recover studio masters or deleted video frames.\n"
    "Audio: SuperMap-style lossy repair + optional 20/24-bit FLAC expand.\n"
    "Video: ffmpeg timestamp/corrupt-packet repair; optional FFV1 lossless (MKV).\n"
    "Enhance: optional EQ / stereo image / immersion (perceptual — not true WFS).\n"
    "Post-compress MP4: ALAC audio + high-quality H.264; master file is kept.\n"
    "A/B Preview: ~15s middle clip — compare source vs current audio settings before Run."
)

HONESTY_SHORT = (
    "Best-effort only — not a studio master. Enhance is perceptual sweetening, not WFS."
)

_EQ_CURVE_LABELS = {
    "flat": "Flat (no target)",
    "harman": "Harman-inspired",
    "diffuse-field": "Diffuse-field inspired",
    "equal-loudness": "Equal-loudness inspired",
    "warm": "Warm",
    "analytical": "Analytical",
    "vocal-presence": "Vocal presence",
    "small-speaker": "Small speaker",
}

_SETTINGS_ORG = "UpConvertAll"
_SETTINGS_APP = "UpConvertAllTheThings"


class Worker(QObject):
    log = Signal(str)
    finished = Signal(bool)

    def __init__(self, paths: list[Path], options: ProcessOptions) -> None:
        super().__init__()
        self.paths = paths
        self.options = options
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @Slot()
    def run(self) -> None:
        ok_all = True
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futs = {
                    pool.submit(self._one, p): p
                    for p in self.paths
                    if not self._cancel
                }
                for fut in as_completed(futs):
                    path = futs[fut]
                    try:
                        outs = fut.result()
                        for o in outs:
                            self.log.emit(f"OK  {path.name} → {o}")
                    except Exception as exc:
                        ok_all = False
                        self.log.emit(f"ERR {path.name}: {exc}")
        except Exception as exc:
            ok_all = False
            self.log.emit(f"Worker failed: {exc}\n{traceback.format_exc()}")
        self.finished.emit(ok_all)

    def _one(self, path: Path) -> list[Path]:
        def prog(msg: str, frac: float) -> None:
            self.log.emit(f"  {path.name}: {int(frac * 100)}% {msg}")

        return process_file(path, self.options, progress=prog)


class PreviewWorker(QObject):
    log = Signal(str)
    finished = Signal(object)  # AbPreviewResult | None
    failed = Signal(str)

    def __init__(self, path: Path, options: ProcessOptions, out_dir: Path) -> None:
        super().__init__()
        self.path = path
        self.options = options
        self.out_dir = out_dir

    @Slot()
    def run(self) -> None:
        try:
            def prog(msg: str, frac: float) -> None:
                self.log.emit(f"  preview: {int(frac * 100)}% {msg}")

            result = build_ab_preview(
                self.path,
                self.options,
                out_dir=self.out_dir,
                duration_sec=15.0,
                progress=prog,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")


def _wrap_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return lab


def _labeled_row(label: str, widget: QWidget, tooltip: str | None = None) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lab = QLabel(label)
    lab.setMinimumWidth(128)
    lab.setMaximumWidth(168)
    lay.addWidget(lab)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay.addWidget(widget, stretch=1)
    if tooltip:
        lab.setToolTip(tooltip)
        widget.setToolTip(tooltip)
        row.setToolTip(tooltip)
    row.setMinimumWidth(200)
    return row


def _make_group(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(4)
    return box, lay


def _make_nested() -> tuple[QWidget, QVBoxLayout]:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(18, 2, 0, 2)
    lay.setSpacing(4)
    return wrap, lay


def _fill_combo(
    combo: QComboBox,
    items: list[tuple[str, object]],
    *,
    tips: dict | None = None,
) -> None:
    combo.clear()
    for label, data in items:
        combo.addItem(label, data)
        if tips and data in tips:
            combo.setItemData(
                combo.count() - 1,
                tips[data],
                Qt.ItemDataRole.ToolTipRole,
            )


def _set_combo_data(combo: QComboBox, value: object) -> None:
    idx = combo.findData(value)
    if idx < 0 and value is not None:
        idx = combo.findData(str(value))
    if idx < 0 and isinstance(value, str):
        try:
            idx = combo.findData(int(value))
        except ValueError:
            pass
    if idx >= 0:
        combo.setCurrentIndex(idx)


# Hover help for option controls.
_TIP_PRESET = (
    "Named settings packs (Listen better, Rescue video, Archive remux, Master MKV, "
    "Immersive listen). Tweaking any control switches to Custom."
)
_TIP_ADVANCED = (
    "Show extra knobs (repair strength, bit depth, EQ curve, dither, and so on). "
    "Presets still fill these in when hidden."
)
_TIP_REPAIR_A = (
    "Clean up lossy-audio artifacts (MP3/AAC/etc.) with spectral repair + bandwidth "
    "extension. Does not recover a studio master."
)
_TIP_REPAIR_V = (
    "Best-effort video container repair via ffmpeg (rebuild timestamps, drop corrupt "
    "packets; re-encode fallback). Cannot restore deleted frames."
)
_TIP_UP_A = (
    "Expand 16-bit audio toward 20/24-bit with SBM-style synthesis + dither. "
    "Approximate only — not a true high-res master."
)
_TIP_UP_V = (
    "Re-encode video as lossless FFV1 inside MKV (or near-lossless H.264 in MP4). "
    "Off = stream-copy video when possible."
)
_TIP_ML = (
    "Slightly richer residual detail during audio upconvert (optional ML/spectral "
    "preference). Falls back to analytic expand if ML is unavailable."
)
_TIP_ML_UNAVAILABLE = (
    "Richer detail (optional ML) requires PyTorch. Install with: "
    'python -m pip install -e ".[ml]"'
)
_TIP_COMPRESS = (
    "After writing the master, also make a smaller delivery MP4/M4A (H.264 + ALAC/AAC). "
    "Master file is kept by default."
)
_TIP_NATIVE_SR = (
    "Keep the source sample rate (e.g. 48 kHz video audio). "
    "Uncheck to resample everything to 44.1 kHz."
)
_TIP_STRENGTH = (
    "How aggressive lossy-audio repair is: light / medium / strong "
    "(more artifact cleanup and HF synthesis)."
)
_TIP_BITS = "Target bit depth for upconverted audio: 24-bit (default) or 20-bit, packed in FLAC/WAV."
_TIP_ITERS = (
    "Upconvert projection iterations. Higher = smoother / more refined detail, slower."
)
_TIP_DITHER = (
    "Final quantize dither: SBM (noise-shaped TPDF, recommended), flat TPDF, or none."
)
_TIP_CONTAINER = (
    "Output container for video jobs: MKV (best for lossless FFV1/FLAC) or MP4 "
    "(broader player support)."
)
_TIP_FLAC = (
    "FLAC compression 0–8 (higher = smaller file, slower encode). Does not change sound."
)
_TIP_MP4Q = (
    "Delivery encode quality when a smaller MP4 is also written: "
    "transparent (CRF 15 + ALAC), high (CRF 18 + ALAC), balanced (CRF 20 + AAC)."
)
_TIP_ENHANCE_A = (
    "Perceptual listening enhance after repair/upconvert (EQ, image, immersion). "
    "Creative sweetening — not archival recovery."
)
_TIP_ENHANCE_V = (
    "Enable video enhance options (A/V sync tighten, light denoise). Off for archive masters."
)
_TIP_EQ = (
    "Enhance EQ: off, auto clarity (mild mid scoop / presence), or a named target curve."
)
_TIP_EQ_CURVE = (
    "Target curve when EQ mode is Target curve: flat, Harman-inspired, diffuse-field, "
    "equal-loudness, warm, analytical, vocal-presence, small-speaker. "
    "Inspired approximations — not calibrated lab targets."
)
_TIP_IMAGE = (
    "Stereo width 0–100 (M/S + ambience; mild crosstalk cancel on speakers). "
    "0 = off. Not trademark Sonic Holography."
)
_TIP_IMAGE_MODE = (
    "Speakers (mild crosstalk cancel) or headphones (width + presence shelf)."
)
_TIP_IMMERSION = (
    "Immersion: off, binaural (headphones), or wider speakers. "
    "Stereo only — not true wave-field synthesis."
)
_TIP_IMMERSION_DEPTH = "How deep the immersion stage / early reflections feel (subtle → deep)."
_TIP_CROSSFEED = "Bauer-style lowpassed headphone crossfeed (pairs well with binaural immersion)."
_TIP_SYNC = "Tighten A/V sync with ffmpeg aresample=async (requires Enhance video)."
_TIP_DENOISE = (
    "Light hqdn3d denoise (requires Enhance video). Forces a video re-encode when stream-copy "
    "would otherwise be used."
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UpConvert All The Things")
        self.resize(900, 760)
        self.setMinimumSize(480, 520)
        self._worker: Worker | None = None
        self._thread: QThread | None = None
        self._preview_worker: PreviewWorker | None = None
        self._preview_thread: QThread | None = None
        self._preview_dir: tempfile.TemporaryDirectory[str] | None = None
        self._source_wav: Path | None = None
        self._processed_wav: Path | None = None
        self._playing_processed = True
        self._layout_key: tuple | None = None
        self._applying_preset = False

        root = QWidget()
        self.setCentralWidget(root)
        self._root_layout = QVBoxLayout(root)
        self._root_layout.setSpacing(8)
        self._root_layout.setContentsMargins(8, 8, 8, 8)

        self._build_honesty()
        self._build_files()
        self._build_preset_header()
        self._build_summary()
        self._build_options()
        self._build_output_folder()
        self._build_preview()
        self._build_run()
        self._build_log()

        self._output = Path("output")
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(1.0)

        self._apply_preset(DEFAULT_PRESET)
        self._sync_ml_checkbox_availability()
        self._sync_control_enablement()
        self._update_summary()
        self._reflow_layout(force=True)

    def _build_honesty(self) -> None:
        short = _wrap_label(HONESTY_SHORT)
        short.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._limits_btn = QToolButton()
        self._limits_btn.setText("About limits")
        self._limits_btn.setCheckable(True)
        self._limits_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._limits_btn.setArrowType(Qt.ArrowType.RightArrow)
        self._limits_btn.setToolTip("Show what this app does and does not claim to do.")
        self._limits_btn.toggled.connect(self._toggle_limits)
        head = QHBoxLayout()
        head.addWidget(short, stretch=1)
        head.addWidget(self._limits_btn)
        self._root_layout.addLayout(head)

        self._honesty_full = _wrap_label(HONESTY)
        self._honesty_full.setToolTip(HONESTY)
        self._honesty_full.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._honesty_full.setVisible(False)
        self._root_layout.addWidget(self._honesty_full)

    def _build_files(self) -> None:
        files_box, files_lay = _make_group("Files to process")
        self.list = QListWidget()
        self.list.setMinimumHeight(48)
        self.list.setToolTip("Queue of files to process. Select one for A/B Preview.")
        self.list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        files_lay.addWidget(self.list, stretch=1)
        file_btns = QGridLayout()
        file_btns.setSpacing(6)
        add_btn = QPushButton("Add files…")
        add_btn.setToolTip("Add individual media files to the queue.")
        add_btn.clicked.connect(self.add_files)
        add_dir = QPushButton("Add folder…")
        add_dir.setToolTip("Add all supported media from a folder (recursive).")
        add_dir.clicked.connect(self.add_folder)
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Remove all files from the queue.")
        clear_btn.clicked.connect(self.list.clear)
        self._file_btns = (add_btn, add_dir, clear_btn)
        self._file_btns_grid = file_btns
        for i, btn in enumerate(self._file_btns):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            file_btns.addWidget(btn, 0, i)
        files_lay.addLayout(file_btns)
        self._files_box = files_box
        self._root_layout.addWidget(files_box, stretch=2)
        model = self.list.model()
        model.rowsInserted.connect(self._update_summary)
        model.rowsRemoved.connect(self._update_summary)

    def _build_preset_header(self) -> None:
        self.preset = QComboBox()
        for p in list_presets():
            self.preset.addItem(p.label, p.id)
            self.preset.setItemData(
                self.preset.count() - 1,
                p.description,
                Qt.ItemDataRole.ToolTipRole,
            )
        self.preset.addItem("Custom", CUSTOM_ID)
        self.preset.setItemData(
            self.preset.count() - 1,
            "Manual settings (no longer a named preset).",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.preset.currentIndexChanged.connect(self._on_preset_chosen)
        self._root_layout.addWidget(_labeled_row("Preset", self.preset, _TIP_PRESET))

        self._preset_desc = _wrap_label("")
        self._preset_desc.setObjectName("presetDescription")
        self._root_layout.addWidget(self._preset_desc)

        self._custom_note = _wrap_label(
            "You changed settings from the preset defaults."
        )
        self._custom_note.setVisible(False)
        self._root_layout.addWidget(self._custom_note)

        self.chk_advanced = QCheckBox("Show advanced settings")
        self.chk_advanced.setToolTip(_TIP_ADVANCED)
        stored = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(
            "showAdvanced", False, type=bool
        )
        self.chk_advanced.setChecked(bool(stored))
        self.chk_advanced.toggled.connect(self._on_advanced_toggled)
        self._root_layout.addWidget(self.chk_advanced)

    def _build_summary(self) -> None:
        box, lay = _make_group("What will happen")
        self._summary = _wrap_label("")
        self._summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._summary.setToolTip(
            "Live recap of the current pipeline. Updates as you change settings."
        )
        lay.addWidget(self._summary)
        self._root_layout.addWidget(box)

    def _build_options(self) -> None:
        opts_inner = QWidget()
        opts_layout = QVBoxLayout(opts_inner)
        opts_layout.setContentsMargins(0, 0, 4, 0)
        opts_layout.setSpacing(8)

        # --- 1. Repair ---
        self.chk_repair_a = QCheckBox("Repair audio")
        self.chk_repair_a.setToolTip(_TIP_REPAIR_A)
        self.chk_repair_v = QCheckBox("Repair video")
        self.chk_repair_v.setToolTip(_TIP_REPAIR_V)
        self.strength = QComboBox()
        _fill_combo(
            self.strength,
            [
                ("Light — less cleanup", "light"),
                ("Medium", "medium"),
                ("Strong — more artifact cleanup", "strong"),
            ],
        )

        repair_box, repair_lay = _make_group("1. Repair")
        self._repair_checks = (self.chk_repair_a, self.chk_repair_v)
        self._repair_checks_grid = QGridLayout()
        self._repair_checks_grid.setSpacing(4)
        repair_lay.addLayout(self._repair_checks_grid)
        self._repair_nested, repair_nested_lay = _make_nested()
        self._repair_setting_rows = (
            _labeled_row("Strength", self.strength, _TIP_STRENGTH),
        )
        self._repair_settings_grid = QGridLayout()
        self._repair_settings_grid.setSpacing(4)
        repair_nested_lay.addLayout(self._repair_settings_grid)
        repair_lay.addWidget(self._repair_nested)
        opts_layout.addWidget(repair_box)

        # --- 2. Upconvert ---
        self.chk_up_a = QCheckBox("Upconvert audio (20/24-bit)")
        self.chk_up_a.setToolTip(_TIP_UP_A)
        self.chk_up_v = QCheckBox("Re-encode video losslessly")
        self.chk_up_v.setToolTip(_TIP_UP_V)
        self.chk_ml = QCheckBox("Richer detail (optional ML)")
        self.chk_ml.setToolTip(_TIP_ML)
        self.bits = QComboBox()
        _fill_combo(
            self.bits,
            [("24-bit (default)", 24), ("20-bit", 20)],
        )
        self.expand_iters = QSpinBox()
        self.expand_iters.setRange(1, 12)
        self.expand_iters.setValue(5)
        self.dither = QComboBox()
        _fill_combo(
            self.dither,
            [
                ("SBM noise-shaped (recommended)", "sbm"),
                ("Flat TPDF", "tpdf"),
                ("None", "none"),
            ],
        )

        up_box, up_lay = _make_group("2. Upconvert")
        self._up_checks = (self.chk_up_a, self.chk_up_v)
        self._up_checks_grid = QGridLayout()
        self._up_checks_grid.setSpacing(4)
        up_lay.addLayout(self._up_checks_grid)
        self._up_nested, up_nested_lay = _make_nested()
        self._up_nested_checks = (self.chk_ml,)
        self._up_nested_checks_grid = QGridLayout()
        self._up_nested_checks_grid.setSpacing(4)
        up_nested_lay.addLayout(self._up_nested_checks_grid)
        self._up_setting_rows = (
            _labeled_row("Bit depth", self.bits, _TIP_BITS),
            _labeled_row("Expand iterations", self.expand_iters, _TIP_ITERS),
            _labeled_row("Dither", self.dither, _TIP_DITHER),
        )
        self._up_settings_grid = QGridLayout()
        self._up_settings_grid.setSpacing(4)
        up_nested_lay.addLayout(self._up_settings_grid)
        up_lay.addWidget(self._up_nested)
        opts_layout.addWidget(up_box)

        # --- 3. Enhance audio ---
        self.chk_enhance_a = QCheckBox("Enhance audio (listening)")
        self.chk_enhance_a.setToolTip(_TIP_ENHANCE_A)
        self.chk_crossfeed = QCheckBox("Headphone crossfeed")
        self.chk_crossfeed.setToolTip(_TIP_CROSSFEED)
        self.eq_mode = QComboBox()
        _fill_combo(
            self.eq_mode,
            [
                ("Off", "none"),
                ("Auto clarity (mild presence)", "auto-clarity"),
                ("Target curve", "target-curve"),
            ],
        )
        self.eq_curve = QComboBox()
        _fill_combo(
            self.eq_curve,
            [
                (_EQ_CURVE_LABELS.get(cid, cid), cid)
                for cid in list_eq_curves()
            ],
        )
        self.stereo_image = QSpinBox()
        self.stereo_image.setRange(0, 100)
        self.stereo_image.setSuffix(" %")
        self.stereo_image_mode = QComboBox()
        _fill_combo(
            self.stereo_image_mode,
            [
                ("Speakers (mild crosstalk cancel)", "speaker"),
                ("Headphones (width + presence)", "headphone"),
            ],
        )
        self.immersion = QComboBox()
        _fill_combo(
            self.immersion,
            [
                ("Off", "off"),
                ("Binaural (headphones)", "binaural"),
                ("Wider speakers (not true WFS)", "speaker-wide"),
            ],
        )
        self.immersion_depth = QSpinBox()
        self.immersion_depth.setRange(0, 100)
        self.immersion_depth.setSuffix(" %")
        self.immersion_depth.setValue(35)

        enh_a_box, enh_a_lay = _make_group("3. Enhance audio (listening)")
        enh_a_lay.addWidget(self.chk_enhance_a)
        self._enh_a_nested, enh_a_nested_lay = _make_nested()
        self._enh_a_nested_checks = (self.chk_crossfeed,)
        self._enh_a_nested_checks_grid = QGridLayout()
        self._enh_a_nested_checks_grid.setSpacing(4)
        enh_a_nested_lay.addLayout(self._enh_a_nested_checks_grid)
        self._eq_curve_row = _labeled_row("EQ curve", self.eq_curve, _TIP_EQ_CURVE)
        self._image_mode_row = _labeled_row(
            "Playback", self.stereo_image_mode, _TIP_IMAGE_MODE
        )
        self._immersion_depth_row = _labeled_row(
            "Stage depth", self.immersion_depth, _TIP_IMMERSION_DEPTH
        )
        self._enh_a_setting_rows = (
            _labeled_row("EQ", self.eq_mode, _TIP_EQ),
            self._eq_curve_row,
            _labeled_row("Stereo width", self.stereo_image, _TIP_IMAGE),
            self._image_mode_row,
            _labeled_row("Immersion", self.immersion, _TIP_IMMERSION),
            self._immersion_depth_row,
        )
        self._enh_a_settings_grid = QGridLayout()
        self._enh_a_settings_grid.setSpacing(4)
        enh_a_nested_lay.addLayout(self._enh_a_settings_grid)
        enh_a_lay.addWidget(self._enh_a_nested)
        opts_layout.addWidget(enh_a_box)

        # --- 4. Enhance video ---
        self.chk_enhance_v = QCheckBox("Enhance video")
        self.chk_enhance_v.setToolTip(_TIP_ENHANCE_V)
        self.chk_sync = QCheckBox("Tighten A/V sync")
        self.chk_sync.setToolTip(_TIP_SYNC)
        self.chk_denoise = QCheckBox("Light video denoise")
        self.chk_denoise.setToolTip(_TIP_DENOISE)

        enh_v_box, enh_v_lay = _make_group("4. Enhance video")
        enh_v_lay.addWidget(self.chk_enhance_v)
        self._enh_v_nested, enh_v_nested_lay = _make_nested()
        self._enh_v_checks = (self.chk_sync, self.chk_denoise)
        self._enh_v_checks_grid = QGridLayout()
        self._enh_v_checks_grid.setSpacing(4)
        enh_v_nested_lay.addLayout(self._enh_v_checks_grid)
        enh_v_lay.addWidget(self._enh_v_nested)
        opts_layout.addWidget(enh_v_box)

        # --- 5. Output ---
        self.chk_compress = QCheckBox("Also write a smaller delivery MP4")
        self.chk_compress.setToolTip(_TIP_COMPRESS)
        self.chk_native_sr = QCheckBox("Keep source sample rate")
        self.chk_native_sr.setToolTip(_TIP_NATIVE_SR)
        self.container = QComboBox()
        _fill_combo(
            self.container,
            [
                ("MKV (best for lossless)", "mkv"),
                ("MP4 (broader playback)", "mp4"),
            ],
        )
        self.flac_level = QSpinBox()
        self.flac_level.setRange(0, 8)
        self.flac_level.setValue(5)
        self.compress_quality = QComboBox()
        _fill_combo(
            self.compress_quality,
            [
                ("Transparent (largest)", "transparent"),
                ("High", "high"),
                ("Balanced (smaller)", "balanced"),
            ],
        )

        out_box, out_lay = _make_group("5. Output")
        self._container_row = _labeled_row("Container", self.container, _TIP_CONTAINER)
        out_lay.addWidget(self._container_row)
        out_lay.addWidget(self.chk_compress)
        self._out_nested, out_nested_lay = _make_nested()
        self._out_nested_checks = (self.chk_native_sr,)
        self._out_nested_checks_grid = QGridLayout()
        self._out_nested_checks_grid.setSpacing(4)
        out_nested_lay.addLayout(self._out_nested_checks_grid)
        self._mp4q_row = _labeled_row(
            "Delivery quality", self.compress_quality, _TIP_MP4Q
        )
        self._out_setting_rows = (
            _labeled_row("FLAC compression", self.flac_level, _TIP_FLAC),
            self._mp4q_row,
        )
        self._out_settings_grid = QGridLayout()
        self._out_settings_grid.setSpacing(4)
        out_nested_lay.addLayout(self._out_settings_grid)
        out_lay.addWidget(self._out_nested)
        opts_layout.addWidget(out_box)

        self._checkboxes = (
            self.chk_repair_a,
            self.chk_repair_v,
            self.chk_up_a,
            self.chk_up_v,
            self.chk_ml,
            self.chk_native_sr,
            self.chk_compress,
            self.chk_enhance_a,
            self.chk_crossfeed,
            self.chk_enhance_v,
            self.chk_sync,
            self.chk_denoise,
        )
        self._combos = (
            self.strength,
            self.bits,
            self.dither,
            self.container,
            self.compress_quality,
            self.eq_mode,
            self.eq_curve,
            self.stereo_image_mode,
            self.immersion,
        )
        self._spins = (
            self.expand_iters,
            self.flac_level,
            self.stereo_image,
            self.immersion_depth,
        )
        self._option_grids = (
            (self._repair_checks_grid, self._repair_checks, self._repair_settings_grid, self._repair_setting_rows),
            (self._up_checks_grid, self._up_checks, self._up_settings_grid, self._up_setting_rows),
            (self._up_nested_checks_grid, self._up_nested_checks, None, ()),
            (self._enh_a_nested_checks_grid, self._enh_a_nested_checks, self._enh_a_settings_grid, self._enh_a_setting_rows),
            (self._enh_v_checks_grid, self._enh_v_checks, None, ()),
            (self._out_nested_checks_grid, self._out_nested_checks, self._out_settings_grid, self._out_setting_rows),
        )

        opts_scroll = QScrollArea()
        opts_scroll.setWidgetResizable(True)
        opts_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        opts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        opts_scroll.setWidget(opts_inner)
        opts_scroll.setMinimumHeight(160)
        opts_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._root_layout.addWidget(opts_scroll, stretch=3)

        for chk in self._checkboxes:
            chk.toggled.connect(self._on_user_option_changed)
        for combo in self._combos:
            combo.currentIndexChanged.connect(self._on_user_option_changed)
        for spin in self._spins:
            spin.valueChanged.connect(self._on_user_option_changed)

    def _build_output_folder(self) -> None:
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Save to:"))
        self.out_label = _wrap_label(str(Path("output").resolve()))
        self.out_label.setToolTip("Current output folder path.")
        self.out_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        out_btn = QPushButton("Folder…")
        out_btn.setToolTip("Choose the folder where outputs are written.")
        out_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        out_btn.clicked.connect(self.pick_output)
        out_row.addWidget(self.out_label, stretch=1)
        out_row.addWidget(out_btn)
        self._root_layout.addLayout(out_row)

    def _build_preview(self) -> None:
        box, lay = _make_group("Preview")
        self._preview_grid = QGridLayout()
        self._preview_grid.setSpacing(6)
        self.preview_btn = QPushButton("A/B Preview")
        self.preview_btn.setToolTip(
            "Build ~15s from the selected file with current audio settings, "
            "then compare Source ↔ Processed."
        )
        self.preview_btn.clicked.connect(self.start_preview)
        self.toggle_btn = QPushButton("Playing: Processed")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setToolTip("Switch A/B playback between Source and Processed.")
        self.toggle_btn.clicked.connect(self.toggle_ab)
        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.setToolTip("Play the current A/B preview clip.")
        self.play_btn.clicked.connect(self.play_preview)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Stop A/B preview playback.")
        self.stop_btn.clicked.connect(self.stop_preview)
        self._preview_btns = (
            self.preview_btn,
            self.toggle_btn,
            self.play_btn,
            self.stop_btn,
        )
        lay.addLayout(self._preview_grid)
        self.preview_status = _wrap_label("Select a file, then A/B Preview.")
        self.preview_status.setMaximumHeight(48)
        lay.addWidget(self.preview_status)
        self._root_layout.addWidget(box)

    def _build_run(self) -> None:
        self.run_btn = QPushButton("Run")
        self.run_btn.setDefault(True)
        self.run_btn.setMinimumHeight(36)
        font = self.run_btn.font()
        font.setBold(True)
        self.run_btn.setFont(font)
        self.run_btn.setToolTip(
            "Process every file in the queue with the current settings."
        )
        self.run_btn.clicked.connect(self.start)
        self._root_layout.addWidget(self.run_btn)

    def _build_log(self) -> None:
        box, lay = _make_group("Progress")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(48)
        self.log.setToolTip("Progress and results for preview and batch runs.")
        self.log.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self.log)
        self._log_box = box
        self._root_layout.addWidget(box, stretch=2)

    @Slot(bool)
    def _toggle_limits(self, on: bool) -> None:
        self._honesty_full.setVisible(on)
        self._limits_btn.setArrowType(
            Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow
        )

    @Slot(bool)
    def _on_advanced_toggled(self, on: bool) -> None:
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue("showAdvanced", on)
        self._sync_control_enablement()

    def _sync_ml_checkbox_availability(self) -> None:
        available = ml_available()
        self.chk_ml.setEnabled(available and self.chk_up_a.isChecked())
        if available:
            self.chk_ml.setToolTip(_TIP_ML)
            return
        blocked = self.chk_ml.blockSignals(True)
        self.chk_ml.setChecked(False)
        self.chk_ml.blockSignals(blocked)
        self.chk_ml.setToolTip(_TIP_ML_UNAVAILABLE)

    def _set_preset_combo(self, preset_id: str) -> None:
        idx = self.preset.findData(preset_id)
        if idx < 0:
            idx = self.preset.findData(CUSTOM_ID)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(max(0, idx))
        self.preset.blockSignals(False)

    def _field_bindings(self) -> dict[str, tuple]:
        """Map PRESET_OPTION_FIELDS -> (setter, getter) for GUI widgets."""
        return {
            "repair_audio": (self.chk_repair_a.setChecked, self.chk_repair_a.isChecked),
            "repair_video": (self.chk_repair_v.setChecked, self.chk_repair_v.isChecked),
            "upconvert_audio": (self.chk_up_a.setChecked, self.chk_up_a.isChecked),
            "upconvert_video": (self.chk_up_v.setChecked, self.chk_up_v.isChecked),
            "repair_strength": (
                lambda v: _set_combo_data(self.strength, v),
                lambda: self.strength.currentData(),
            ),
            "output_bits": (
                lambda v: _set_combo_data(self.bits, int(v)),
                lambda: int(self.bits.currentData()),
            ),
            "ml_upscaler": (self.chk_ml.setChecked, self.chk_ml.isChecked),
            "expand_iterations": (self.expand_iters.setValue, self.expand_iters.value),
            "dither": (
                lambda v: _set_combo_data(self.dither, v),
                lambda: self.dither.currentData(),
            ),
            "flac_level": (self.flac_level.setValue, self.flac_level.value),
            "container": (
                lambda v: _set_combo_data(self.container, v),
                lambda: self.container.currentData(),
            ),
            "compress_mp4": (self.chk_compress.setChecked, self.chk_compress.isChecked),
            "compress_quality": (
                lambda v: _set_combo_data(self.compress_quality, v),
                lambda: self.compress_quality.currentData(),
            ),
            "native_sample_rate": (
                self.chk_native_sr.setChecked,
                self.chk_native_sr.isChecked,
            ),
            "enhance_audio": (self.chk_enhance_a.setChecked, self.chk_enhance_a.isChecked),
            "enhance_video": (self.chk_enhance_v.setChecked, self.chk_enhance_v.isChecked),
            "eq_mode": (
                lambda v: _set_combo_data(self.eq_mode, v),
                lambda: self.eq_mode.currentData(),
            ),
            "eq_curve": (
                lambda v: _set_combo_data(self.eq_curve, v),
                lambda: self.eq_curve.currentData(),
            ),
            "stereo_image_strength": (self.stereo_image.setValue, self.stereo_image.value),
            "stereo_image_mode": (
                lambda v: _set_combo_data(self.stereo_image_mode, v),
                lambda: self.stereo_image_mode.currentData(),
            ),
            "immersion": (
                lambda v: _set_combo_data(self.immersion, v),
                lambda: self.immersion.currentData(),
            ),
            "immersion_depth": (
                lambda v: self.immersion_depth.setValue(int(round(float(v) * 100))),
                lambda: float(self.immersion_depth.value()) / 100.0,
            ),
            "crossfeed": (self.chk_crossfeed.setChecked, self.chk_crossfeed.isChecked),
            "video_sync_tighten": (self.chk_sync.setChecked, self.chk_sync.isChecked),
            "video_denoise": (self.chk_denoise.setChecked, self.chk_denoise.isChecked),
        }

    def _apply_preset(self, preset_id: str) -> None:
        if preset_id == CUSTOM_ID:
            self._set_preset_combo(CUSTOM_ID)
            self._update_summary()
            return
        p = get_preset(preset_id)
        self._applying_preset = True
        try:
            bindings = self._field_bindings()
            for field in PRESET_OPTION_FIELDS:
                setter, _getter = bindings[field]
                setter(getattr(p, field))
            self._set_preset_combo(preset_id)
            self._sync_ml_checkbox_availability()
            self._sync_control_enablement()
        finally:
            self._applying_preset = False
        self._update_summary()

    def _sync_control_enablement(self) -> None:
        """Hide nested knobs unless Advanced is on and the parent stage is on."""
        repair_on = self.chk_repair_a.isChecked()
        up_on = self.chk_up_a.isChecked()
        compress_on = self.chk_compress.isChecked()
        enh_a = self.chk_enhance_a.isChecked()
        enh_v = self.chk_enhance_v.isChecked()
        advanced = self.chk_advanced.isChecked()
        ml_ok = ml_available()

        self.chk_ml.setEnabled(up_on and ml_ok)
        self.chk_crossfeed.setEnabled(enh_a)
        self.eq_mode.setEnabled(enh_a)
        self.eq_curve.setEnabled(enh_a and self.eq_mode.currentData() == "target-curve")
        self.stereo_image.setEnabled(enh_a)
        self.stereo_image_mode.setEnabled(enh_a and self.stereo_image.value() > 0)
        self.immersion.setEnabled(enh_a)
        self.immersion_depth.setEnabled(
            enh_a and self.immersion.currentData() != "off"
        )
        self.chk_sync.setEnabled(enh_v)
        self.chk_denoise.setEnabled(enh_v)
        self.compress_quality.setEnabled(compress_on)
        self.strength.setEnabled(repair_on)
        self.bits.setEnabled(up_on)
        self.expand_iters.setEnabled(up_on)
        self.dither.setEnabled(up_on)

        self._repair_nested.setVisible(advanced and repair_on)
        self._up_nested.setVisible(advanced and up_on)
        self._enh_a_nested.setVisible(advanced and enh_a)
        self._enh_v_nested.setVisible(advanced and enh_v)
        self._out_nested.setVisible(advanced)
        self._eq_curve_row.setVisible(self.eq_mode.currentData() == "target-curve")
        self._image_mode_row.setVisible(self.stereo_image.value() > 0)
        self._immersion_depth_row.setVisible(self.immersion.currentData() != "off")
        self._mp4q_row.setVisible(compress_on)

    def _queue_paths(self) -> list[Path]:
        return [Path(self.list.item(i).text()) for i in range(self.list.count())]

    def _update_summary(self) -> None:
        if not hasattr(self, "_summary"):
            return
        custom = self.preset.currentData() == CUSTOM_ID
        self._custom_note.setVisible(bool(custom))
        pid = self.preset.currentData()
        if pid and pid != CUSTOM_ID:
            self._preset_desc.setText(get_preset(str(pid)).description)
        else:
            self._preset_desc.setText(
                "Custom — settings no longer match a named preset."
            )
        kinds = queue_media_kinds(self._queue_paths())
        self._summary.setText(summarize_pipeline(self._options(), queue_kinds=kinds))

    @Slot()
    def _on_user_option_changed(self) -> None:
        if self._applying_preset:
            return
        self._mark_custom_preset()
        self._sync_control_enablement()
        self._update_summary()

    @Slot()
    def _on_preset_chosen(self) -> None:
        if self._applying_preset:
            return
        pid = self.preset.currentData()
        if pid and pid != CUSTOM_ID:
            self._apply_preset(str(pid))

    @Slot()
    def _mark_custom_preset(self) -> None:
        if self._applying_preset:
            return
        if self.preset.currentData() != CUSTOM_ID:
            self._set_preset_combo(CUSTOM_ID)

    def _clear_grid(self, grid: QGridLayout) -> None:
        while grid.count():
            grid.takeAt(0)

    def _layout_metrics(self) -> tuple[int, int, int, bool]:
        """Return (check_cols, setting_cols, preview_cols, compact_height)."""
        w = self.width()
        h = self.height()
        short = h < 700
        if w < 560:
            check_cols = 1 if not short else 2
            setting_cols = 1
            preview_cols = 2
        elif w < 780:
            check_cols = 2
            setting_cols = 2
            preview_cols = 2
        else:
            check_cols = 2
            setting_cols = 2
            preview_cols = 4 if short else 2
        return check_cols, setting_cols, preview_cols, short

    def _reflow_layout(self, *, force: bool = False) -> None:
        check_cols, setting_cols, preview_cols, short = self._layout_metrics()
        key = (check_cols, setting_cols, preview_cols, short)
        if not force and key == self._layout_key:
            return
        self._layout_key = key

        self._root_layout.setSpacing(4 if short else 8)
        self._root_layout.setContentsMargins(
            6 if short else 8,
            4 if short else 8,
            6 if short else 8,
            4 if short else 8,
        )
        self.list.setMinimumHeight(36 if short else 56)
        self.log.setMinimumHeight(36 if short else 56)
        self.preview_status.setMaximumHeight(36 if short else 64)

        for checks_grid, checks, settings_grid, setting_rows in self._option_grids:
            self._clear_grid(checks_grid)
            for i, chk in enumerate(checks):
                checks_grid.addWidget(chk, i // check_cols, i % check_cols)
            if settings_grid is not None:
                self._clear_grid(settings_grid)
                for i, row in enumerate(setting_rows):
                    settings_grid.addWidget(row, i // setting_cols, i % setting_cols)

        self._clear_grid(self._file_btns_grid)
        file_cols = 3 if self.width() >= 560 else 1
        for i, btn in enumerate(self._file_btns):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._file_btns_grid.addWidget(btn, i // file_cols, i % file_cols)

        self._clear_grid(self._preview_grid)
        for i, btn in enumerate(self._preview_btns):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._preview_grid.addWidget(btn, i // preview_cols, i % preview_cols)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_layout()

    def add_files(self) -> None:
        filt = "Media (" + " ".join(f"*{s}" for s in sorted(ALL_SUFFIXES)) + ")"
        files, _ = QFileDialog.getOpenFileNames(self, "Add media", "", filt)
        for f in files:
            self.list.addItem(f)

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if not d:
            return
        for p in collect_inputs([Path(d)], recursive=True):
            self.list.addItem(str(p))

    def pick_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder")
        if d:
            self._output = Path(d)
            self.out_label.setText(d)

    def _options(self) -> ProcessOptions:
        bindings = self._field_bindings()
        kwargs = {field: getter() for field, (_setter, getter) in bindings.items()}
        return ProcessOptions(
            output_dir=self._output,
            keep_master=True,
            **kwargs,
        )

    def _selected_path(self) -> Path | None:
        item = self.list.currentItem()
        if item is None and self.list.count() == 1:
            item = self.list.item(0)
        if item is None:
            return None
        return Path(item.text())

    def start(self) -> None:
        paths = self._queue_paths()
        if not paths:
            QMessageBox.warning(self, "Nothing to do", "Add media files first.")
            return
        self.stop_preview()
        self.run_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.log.append(f"Starting {len(paths)} file(s)…")

        self._thread = QThread()
        self._worker = Worker(paths, self._options())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.log.append)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    @Slot(bool)
    def _on_done(self, ok: bool) -> None:
        self.run_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.log.append("Finished." if ok else "Finished with errors.")

    def start_preview(self) -> None:
        path = self._selected_path()
        if path is None:
            QMessageBox.warning(
                self,
                "Nothing selected",
                "Select a file in the list (or add a single file) for A/B preview.",
            )
            return
        if not path.is_file():
            QMessageBox.warning(self, "Missing file", f"Not found: {path}")
            return

        self.stop_preview()
        if self._preview_dir is not None:
            self._preview_dir.cleanup()
        self._preview_dir = tempfile.TemporaryDirectory(prefix="upconvert_ab_")
        self._source_wav = None
        self._processed_wav = None
        self.toggle_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        self.preview_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.preview_status.setText(f"Building preview for {path.name}…")
        self.log.append(f"A/B preview: {path.name}")

        opts = self._options()
        # Preview does not need batch output_dir; keep settings for audio DSP only.
        opts.compress_mp4 = False

        self._preview_thread = QThread()
        self._preview_worker = PreviewWorker(
            path, opts, Path(self._preview_dir.name)
        )
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.log.connect(self.log.append)
        self._preview_worker.finished.connect(self._on_preview_ready)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.finished.connect(self._preview_thread.quit)
        self._preview_worker.failed.connect(self._preview_thread.quit)
        self._preview_thread.start()

    @Slot(object)
    def _on_preview_ready(self, result: object) -> None:
        self.preview_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        if result is None:
            return
        self._source_wav = result.source_wav  # type: ignore[attr-defined]
        self._processed_wav = result.processed_wav  # type: ignore[attr-defined]
        self._playing_processed = True
        self.toggle_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.toggle_btn.setText("Playing: Processed")
        self.preview_status.setText(
            f"Ready: {result.start_sec:.1f}s–"
            f"{result.start_sec + result.duration_sec:.1f}s @ {result.sample_rate} Hz"
            f"  |  {result.description}"  # type: ignore[attr-defined]
        )
        self.log.append("A/B preview ready — Play, then toggle Source ↔ Processed.")
        self._set_player_source(self._processed_wav)
        self._player.play()

    @Slot(str)
    def _on_preview_failed(self, err: str) -> None:
        self.preview_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.preview_status.setText("A/B failed.")
        self.log.append(f"A/B ERR: {err}")
        QMessageBox.warning(self, "A/B Preview failed", err.split("\n", 1)[0])

    def _set_player_source(self, path: Path | None) -> None:
        if path is None:
            return
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))

    def toggle_ab(self) -> None:
        if self._source_wav is None or self._processed_wav is None:
            return
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        pos = self._player.position()
        self._playing_processed = not self._playing_processed
        wav = self._processed_wav if self._playing_processed else self._source_wav
        label = "Processed" if self._playing_processed else "Source"
        self.toggle_btn.setText(f"Playing: {label}")
        self.preview_status.setText(f"A/B: {label}")
        self._set_player_source(wav)
        self._player.setPosition(pos)
        if was_playing:
            self._player.play()

    def play_preview(self) -> None:
        if self._processed_wav is None:
            return
        if self._player.source().isEmpty():
            wav = self._processed_wav if self._playing_processed else self._source_wav
            self._set_player_source(wav)
        self._player.play()

    def stop_preview(self) -> None:
        self._player.stop()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_preview()
        if self._preview_dir is not None:
            self._preview_dir.cleanup()
            self._preview_dir = None
        super().closeEvent(event)


def run_gui_main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui_main())
