"""CLI for UpConvert All The Things."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .formats import collect_inputs
from .io_audio import ffmpeg_available
from .enhance import list_eq_curves
from .pipeline import ProcessOptions, process_file
from .presets import (
    PRESET_IDS,
    cli_field_explicit,
    pick_preset_option_values,
    preset_settings,
)


HONESTY = (
    "Repair and upconvert are best-effort. Lossy->lossless does not recover a studio "
    "master. Video repair cannot restore deleted frames. Enhance (EQ/image/immersion) "
    "is perceptual sweetening — not true WFS or holography recovery."
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="upconvert-all",
        description="Repair lossy audio / broken video, then selectively upconvert to lossless.",
    )
    p.add_argument("--gui", action="store_true", help="Launch the GUI")
    sub = p.add_subparsers(dest="cmd")

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("inputs", nargs="+", type=Path, help="Files or directories")
        sp.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory")
        sp.add_argument("-r", "--recursive", action="store_true", help="Recurse directories")
        sp.add_argument(
            "--preset",
            choices=list(PRESET_IDS),
            default=None,
            help=(
                "Apply a named settings preset; explicit flags after it still override "
                "(listen-better, rescue-video, archive-remux, master-mkv, immersive-listen)"
            ),
        )
        sp.add_argument("--repair-audio", action=argparse.BooleanOptionalAction, default=True)
        sp.add_argument("--repair-video", action=argparse.BooleanOptionalAction, default=True)
        sp.add_argument("--upconvert-audio", action=argparse.BooleanOptionalAction, default=True)
        sp.add_argument("--upconvert-video", action=argparse.BooleanOptionalAction, default=False)
        sp.add_argument("--repair-strength", choices=["light", "medium", "strong"], default="strong")
        sp.add_argument("--bits", type=int, choices=[20, 24], default=24)
        sp.add_argument(
            "--ml-upscaler",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Use spectral/ML prefer prior during expand (default on)",
        )
        sp.add_argument(
            "--upconvert-iterations",
            "--expand-iterations",
            type=int,
            default=5,
            dest="expand_iterations",
            help="Upconvert projection iterations (higher = smoother / more detail)",
        )
        sp.add_argument(
            "--dither",
            choices=["sbm", "tpdf", "none"],
            default="sbm",
            help="Post-expand dither: SBM noise-shaped TPDF (default), flat TPDF, or none",
        )
        sp.add_argument("--flac-level", type=int, default=5)
        sp.add_argument("--container", choices=["mkv", "mp4", "flac"], default="mkv")
        sp.add_argument("--ffmpeg", action="store_true", help="Force ffmpeg decode for audio")
        sp.add_argument(
            "--compress-mp4",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Post-process: write a delivery MP4/M4A (ALAC + high-quality H.264)",
        )
        sp.add_argument(
            "--compress-quality",
            choices=["transparent", "high", "balanced"],
            default="transparent",
            help="Delivery encode quality (transparent keeps ALAC audio + CRF 15)",
        )
        sp.add_argument(
            "--keep-master",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Keep the lossless/master output alongside the delivery MP4",
        )
        sp.add_argument(
            "--native-sample-rate",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Keep source sample rate (default). --no-native-sample-rate forces 44.1 kHz",
        )
        sp.add_argument(
            "--enhance-audio",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Perceptual listening enhance after repair/upconvert (not archival)",
        )
        sp.add_argument(
            "--enhance-video",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Enable video enhance filters (sync / denoise)",
        )
        sp.add_argument(
            "--eq-mode",
            choices=["none", "auto-clarity", "target-curve"],
            default="none",
            help="Enhance EQ mode",
        )
        sp.add_argument(
            "--eq-curve",
            choices=list(list_eq_curves()),
            default="flat",
            help="Target EQ curve when --eq-mode=target-curve (inspired multi-band profiles)",
        )
        sp.add_argument(
            "--stereo-image",
            type=int,
            default=0,
            dest="stereo_image_strength",
            metavar="0-100",
            help="Stereo image / holography-style strength (0=off)",
        )
        sp.add_argument(
            "--stereo-image-mode",
            choices=["speaker", "headphone"],
            default="speaker",
            help="Stereo image target (speaker uses mild XTC)",
        )
        sp.add_argument(
            "--immersion",
            choices=["off", "binaural", "speaker-wide"],
            default="off",
            help="WFS-inspired immersion (stereo/binaural only; not true WFS)",
        )
        sp.add_argument(
            "--immersion-depth",
            type=float,
            default=0.35,
            help="Immersion depth 0–1",
        )
        sp.add_argument(
            "--crossfeed",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Bauer-style headphone crossfeed",
        )
        sp.add_argument(
            "--video-sync-tighten",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Tighten A/V sync via aresample=async (needs --enhance-video)",
        )
        sp.add_argument(
            "--video-denoise",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Light hqdn3d denoise (needs --enhance-video; forces video encode)",
        )

    add_common(sub.add_parser("process", help="Process audio and/or video files"))
    add_common(sub.add_parser("repair", help="Alias: enable repair toggles"))
    add_common(sub.add_parser("upconvert", help="Alias: enable upconvert toggles"))
    return p


def _options_from_args(args: argparse.Namespace, argv: list[str]) -> ProcessOptions:
    preset = getattr(args, "preset", None)
    base = preset_settings(preset) if preset else {}

    def pick(field: str, arg_val):
        if preset and field in base and not cli_field_explicit(argv, field):
            return base[field]
        return arg_val

    kwargs = pick_preset_option_values(pick, args)
    if args.cmd == "repair":
        kwargs["repair_audio"] = True
        kwargs["repair_video"] = True
    if args.cmd == "upconvert":
        kwargs["upconvert_audio"] = True
    return ProcessOptions(
        output_dir=args.output,
        force_ffmpeg=args.ffmpeg,
        keep_master=args.keep_master,
        **kwargs,
    )

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ["--gui"] or (argv and argv[0] == "gui"):
        from .gui import run_gui_main

        return run_gui_main()

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.gui or args.cmd is None:
        from .gui import run_gui_main

        return run_gui_main()

    if not ffmpeg_available():
        print("Warning: ffmpeg not on PATH - video and many audio formats will fail.", file=sys.stderr)

    files = collect_inputs(args.inputs, recursive=args.recursive)
    if not files:
        print("No supported media found.", file=sys.stderr)
        return 2

    options = _options_from_args(args, argv)
    print(HONESTY)
    if args.preset:
        print(f"Preset: {args.preset}")
    print(f"Processing {len(files)} file(s) -> {options.output_dir}")
    failed = 0
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}")
        try:
            outs = process_file(
                path,
                options,
                progress=lambda msg, frac, name=path.name: print(f"  {int(frac*100):3d}% {msg}"),
            )
            for o in outs:
                print(f"  -> {o}")
        except Exception as exc:
            failed += 1
            print(f"  ERROR: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
