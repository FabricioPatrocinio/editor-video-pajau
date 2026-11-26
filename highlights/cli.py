from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .analysis.audio import extract_mono_audio
from .analysis.signals import build_signal_bundle
from .config import load_preset
from .download.youtube import download_media, probe_video
from .export.ffmpeg import export_compilation, export_cuts
from .export.previews import generate_cut_previews
from .export.reports import plot_score, write_csv, write_json, write_project
from .export.timeline import write_edl, write_mlt_xml
from .models import Cut, Project
from .scoring.scoring import combine_signals
from .selection.selection import select_cuts


def analyze(args: argparse.Namespace) -> int:
    output = Path(args.output)
    cache = Path(args.cache)
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    settings = load_preset(args.preset)
    if args.target_duration:
        settings.target_duration = args.target_duration
    if args.max_cuts:
        settings.max_cuts = args.max_cuts
    if args.aspect:
        settings.aspect = args.aspect

    source = args.url if args.url else args.input
    if not source:
        raise ValueError("Informe --input ou --url")

    video, info = download_media(source, cache / "downloads")
    duration = probe_video(video)["duration"]
    wav = extract_mono_audio(video, cache / "audio" / "mono.wav")

    chat_path = args.chat
    manual_path = args.manual
    signals = build_signal_bundle(
        str(video), duration, str(wav), chat_path, manual_path, info,
        settings.chat_offset, settings.chat_keywords,
    )

    available_weights = {name: curve for name, curve in signals.items()}
    score = combine_signals(available_weights, settings.weights)
    np.savez(cache / "signals.npz", score=score, **signals)

    cuts = select_cuts(
        score,
        target_duration=settings.target_duration,
        min_cut=settings.min_cut,
        max_cut=settings.max_cut,
        max_cuts=settings.max_cuts,
        padding_before=settings.padding_before,
        padding_after=settings.padding_after,
        min_distance=settings.min_distance,
        ignore_intervals=settings.ignore_intervals,
    )
    for cut in cuts:
        cut.contributions = {
            name: float(np.asarray(curve[max(0, int(cut.start)):min(len(curve), int(cut.end))]).mean())
            for name, curve in signals.items()
        }

    project = Project(source=source, video_path=str(video), duration=duration, settings=settings, cuts=cuts)
    generate_cut_previews(video, cuts, output / "previews")
    write_project(project, output / "project.json")
    write_csv(cuts, output / "cuts.csv")
    write_json(cuts, output / "cuts.json")
    plot_score(score, cuts, output / "score.png")
    write_edl(cuts, video.name, output / "timeline.edl")
    write_mlt_xml(str(video.resolve()), cuts, output / "kdenlive.mlt")

    if args.review_only:
        print(f"{len(cuts)} cortes encontrados para revisão")
        print(f"Projeto: {output / 'project.json'}")
        print(f"Prévias: {output / 'previews'}")
        return 0

    clips = export_cuts(video, cuts, output / "clips", settings.aspect, settings.export_mode)
    export_compilation(clips, output / "compilation.mp4")
    print(f"{len(cuts)} cortes encontrados")
    print(f"Projeto: {output / 'project.json'}")
    print(f"Compilado: {output / 'compilation.mp4'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pajau", description="Gerador open-source de cortes de lives")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_parser = sub.add_parser("analyze", help="Analisar vídeo local ou URL")
    analyze_parser.add_argument("--input", help="Arquivo de vídeo local")
    analyze_parser.add_argument("--url", help="URL do YouTube")
    analyze_parser.add_argument("--chat", help="Arquivo JSON do replay do chat")
    analyze_parser.add_argument("--manual", help="Arquivo TXT/CSV de timestamps")
    analyze_parser.add_argument("--preset", default="highlights_10min")
    analyze_parser.add_argument("--target-duration", type=float)
    analyze_parser.add_argument("--max-cuts", type=int)
    analyze_parser.add_argument("--aspect", choices=["16:9", "9:16"])
    analyze_parser.add_argument("--cache", default="cache")
    analyze_parser.add_argument("--output", default="output")
    analyze_parser.add_argument("--review-only", action="store_true", help="Gerar cortes e prévias sem criar o compilado")
    analyze_parser.set_defaults(func=analyze)

    ui_parser = sub.add_parser("ui", help="Abrir interface Gradio")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=7860)
    ui_parser.set_defaults(func=lambda args: launch_ui(args.host, args.port))
    return parser


def launch_ui(host: str, port: int) -> int:
    from .ui.gradio_app import build_app
    app = build_app()
    app.launch(server_name=host, server_port=port)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))
