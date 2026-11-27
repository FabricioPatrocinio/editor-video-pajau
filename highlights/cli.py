from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()

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
from .selection.deduplicate import deduplicate_cuts


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
    if getattr(args, "ignore_intervals", None):
        settings.ignore_intervals = args.ignore_intervals
    elif getattr(args, "ignore", None):
        settings.ignore_intervals = [list(interval) for interval in args.ignore]

    source = args.url if args.url else args.input
    if not source:
        raise ValueError("Informe --input ou --url")

    progress = getattr(args, "progress", None) or (lambda fraction, text: None)
    progress(0.02, "Lendo o vídeo...")
    video, info = download_media(source, cache / "downloads")
    duration = probe_video(video)["duration"]
    progress(0.08, "Extraindo o áudio...")
    wav = extract_mono_audio(video, cache / "audio" / "mono.wav")
    progress(0.2, "Medindo volume e mudanças de cena (é a parte mais demorada)...")

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
    progress(0.65, f"Gerando miniaturas de {len(cuts)} candidatos...")
    generate_cut_previews(video, cuts, output / "previews")
    cuts = deduplicate_cuts(cuts, output / "previews")
    project = Project(source=source, video_path=str(video), duration=duration, settings=settings, cuts=cuts)
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


def auto(args: argparse.Namespace) -> int:
    from .ai.config import check_ai_ready, load_ai_settings
    from .pipeline import export_plan, find_candidates, plan_with_ai

    settings = load_ai_settings()
    problem = check_ai_ready(settings)
    if problem:
        print(problem)
        return 1
    if not (args.input or args.url):
        print("Informe --input ou --url")
        return 1

    target = args.minutes * 60
    print("1/3 Procurando candidatos na live...")
    output, candidates = find_candidates(
        args.url or args.input, target, [list(item) for item in args.ignore or []], url=bool(args.url),
        progress=lambda fraction, text: print(f"    {text}"),
    )
    if not candidates:
        print("Nenhum candidato encontrado.")
        return 1

    print(f"2/3 {settings.label} analisando {len(candidates)} candidatos...")
    plan = plan_with_ai(output, candidates, args.briefing, args.avoid, target)
    print(f"\n{plan.summary}\n")
    for index, item in enumerate(plan.items, 1):
        print(f"  {index:02d}. {item.start:8.1f}s - {item.end:8.1f}s  [{item.kind}] ({item.transition}) {item.reason}")
    print(f"\nUso: {plan.usage}")
    print(f"Plano salvo em {output / 'ia-plan.json'}")

    if args.plan_only or not plan.items:
        return 0
    print("3/3 Exportando vídeo...")
    print(f"Vídeo final: {export_plan(output, plan.items, args.aspect)}")
    return 0


def preparar(args: argparse.Namespace) -> int:
    """Análise local + pedido pronto para o Claude Code ler (modo /cortar)."""
    from dataclasses import asdict

    from .ai.config import load_ai_settings
    from .ai.plan import prepare_request
    from .ai.prompt import SYSTEM_PROMPT
    from .ai.providers import write_request_file
    from .pipeline import find_candidates

    target = args.minutes * 60
    output, candidates = find_candidates(
        args.input, target, [list(item) for item in args.ignore or []],
        progress=lambda fraction, text: print(f"    {text}"),
    )
    if not candidates:
        print("Nenhum candidato encontrado.")
        return 1
    _, parts = prepare_request(candidates, args.briefing, target, args.avoid, load_ai_settings())
    request = write_request_file(SYSTEM_PROMPT, parts, output / "ia-pedido.md")
    (output / "ia-pedido.json").write_text(json.dumps(
        {"target_duration": target, "briefing": args.briefing, "ignorar": args.avoid}, ensure_ascii=False
    ), encoding="utf-8")
    print(f"PASTA={output}")
    print(f"PEDIDO={request}")
    print(f"RESPOSTA={output / 'ia-plan.json'}")
    return 0


def gerar(args: argparse.Namespace) -> int:
    """Exporta o vídeo a partir do ia-plan.json de uma pasta."""
    from dataclasses import asdict

    from .ai.plan import plan_from_result
    from .pipeline import export_plan, load_candidates

    folder = Path(args.pasta)
    meta_path = folder / "ia-pedido.json"
    target = json.loads(meta_path.read_text(encoding="utf-8"))["target_duration"] if meta_path.exists() else 3600.0
    result = json.loads((folder / "ia-plan.json").read_text(encoding="utf-8"))
    plan = plan_from_result(result, load_candidates(folder), target, "Claude Code", "")
    if not plan.items:
        print("O ia-plan.json não tem trechos válidos.")
        return 1
    for index, item in enumerate(plan.items, 1):
        print(f"  {index:02d}. {item.start:8.1f}s - {item.end:8.1f}s  [{item.kind}] ({item.transition}) {item.reason}")
    print(f"Vídeo final: {export_plan(folder, plan.items, args.aspect)}")
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
    analyze_parser.add_argument("--ignore", action="append", nargs=2, type=float, metavar=("START", "END"), help="Intervalo a ignorar em segundos")
    analyze_parser.set_defaults(func=analyze)

    auto_parser = sub.add_parser("auto", help="Live -> IA escolhe os trechos -> vídeo final, sem revisão")
    auto_parser.add_argument("--input", help="Arquivo de vídeo local")
    auto_parser.add_argument("--url", help="URL do YouTube")
    auto_parser.add_argument("--briefing", default="", help="Como você quer o vídeo (opcional se o seu estilo estiver salvo)")
    auto_parser.add_argument("--avoid", default="", help="O que a IA deve ignorar, em linguagem natural")
    auto_parser.add_argument("--minutes", type=float, default=10, help="Duração alvo do vídeo final")
    auto_parser.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    auto_parser.add_argument("--ignore", action="append", nargs=2, type=float, metavar=("START", "END"), help="Intervalo a ignorar em segundos")
    auto_parser.add_argument("--plan-only", action="store_true", help="Só gerar o plano da IA, sem exportar o vídeo")
    auto_parser.set_defaults(func=auto)

    prep_parser = sub.add_parser("preparar", help="Análise local + pedido para o Claude Code (modo /cortar)")
    prep_parser.add_argument("--input", required=True)
    prep_parser.add_argument("--briefing", default="")
    prep_parser.add_argument("--avoid", default="")
    prep_parser.add_argument("--minutes", type=float, default=10)
    prep_parser.add_argument("--ignore", action="append", nargs=2, type=float, metavar=("START", "END"))
    prep_parser.set_defaults(func=preparar)

    gen_parser = sub.add_parser("gerar", help="Gera o vídeo a partir do ia-plan.json de uma pasta")
    gen_parser.add_argument("--pasta", required=True)
    gen_parser.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    gen_parser.set_defaults(func=gerar)

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
