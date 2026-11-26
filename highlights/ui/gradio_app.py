from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import gradio as gr

from ..cli import analyze


def _file_path(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("path")
    return getattr(value, "name", None) or str(value)


def _seconds(text: str) -> float:
    text = text.strip()
    if ":" not in text:
        return float(text)
    value = 0.0
    for part in text.split(":"):
        value = value * 60 + float(part)
    return value


def _time_text(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def build_app():
    with gr.Blocks(title="Pajau - Revisão") as app:
        gr.Markdown("# Pajau\nAnalise, revise miniaturas e escolha somente os cortes desejados.")
        project_state = gr.State("")

        with gr.Tab("1. Analisar"):
            video = gr.File(label="Vídeo local", file_types=[".mp4", ".mkv", ".mov", ".webm"])
            url = gr.Textbox(label="Ou URL do YouTube", placeholder="https://youtube.com/watch?v=...")
            manual = gr.File(label="Timestamps positivos (vitória, boss vencido)", file_types=[".txt", ".csv"])
            ignore = gr.Textbox(label="Intervalos a ignorar", placeholder="0-600, 10800-11200")
            preset = gr.Dropdown(["highlights_10min", "shorts_60s_vertical", "react_compilation"], value="highlights_10min")
            target = gr.Number(value=600, label="Duração final em segundos")
            aspect = gr.Radio(["16:9", "9:16"], value="16:9")
            analyze_button = gr.Button("Gerar candidatos para revisão", variant="primary")
            status = gr.JSON(label="Resultado")

        with gr.Tab("2. Revisar"):
            gallery = gr.Gallery(label="Início, meio e fim dos cortes", columns=3, height="auto")
            accepted = gr.CheckboxGroup(label="Cortes aceitos", choices=[])
            selected = gr.Dropdown(label="Corte selecionado", choices=[])
            new_start = gr.Textbox(label="Novo início")
            new_end = gr.Textbox(label="Novo fim")
            export_button = gr.Button("Exportar cortes aceitos", variant="primary")
            export_status = gr.JSON(label="Exportação")

        def run_analysis(video, url, manual, ignore, preset, target, aspect):
            source = _file_path(video) or (url.strip() if url else "")
            if not source:
                return {"erro": "Selecione um vídeo local ou informe uma URL"}, [], [], "", []

            run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = Path("output") / f"web-{run_id}"
            output.mkdir(parents=True, exist_ok=True)

            ignore_intervals = []
            for item in (ignore or "").split(","):
                try:
                    start, end = item.split("-", 1)
                    ignore_intervals.append([_seconds(start), _seconds(end)])
                except ValueError:
                    pass

            args = argparse.Namespace(
                input=source if not source.startswith(("http://", "https://")) else None,
                url=source if source.startswith(("http://", "https://")) else None,
                chat=None,
                manual=_file_path(manual),
                preset=preset,
                target_duration=float(target),
                max_cuts=None,
                aspect=aspect,
                cache=str(Path("cache") / f"web-{run_id}"),
                output=str(output),
                review_only=True,
                ignore_intervals=ignore_intervals,
            )

            try:
                analyze(args)
                project_path = output / "project.json"
                project = json.loads(project_path.read_text(encoding="utf-8"))
                project["ignore_intervals"] = ignore_intervals
                project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

                choices = []
                gallery_items = []
                for index, cut in enumerate(project["cuts"], 1):
                    label = f"{index:02d}  {_time_text(cut['start'])}–{_time_text(cut['end'])}  score={cut['score']:.2f}"
                    choices.append(label)
                    for position in ("start", "middle", "end"):
                        image = output / "previews" / f"clip_{index:02d}_{position}.jpg"
                        if image.exists():
                            gallery_items.append((str(image), label))

                return {"ok": True, "projeto": str(project_path)}, gallery_items, choices, str(output), choices
            except Exception as error:
                return {"erro": str(error)}, [], [], "", []

        def export_selected(project_dir, choices_selected):
            if not project_dir:
                return {"erro": "Gere os candidatos primeiro"}
            output = Path(project_dir)
            project = json.loads((output / "project.json").read_text(encoding="utf-8"))

            accepted_cuts = []
            for index, raw in enumerate(project["cuts"]):
                label = f"{index + 1:02d}  {_time_text(raw['start'])}–{_time_text(raw['end'])}  score={raw['score']:.2f}"
                if label in (choices_selected or []):
                    from ..models import Cut
                    accepted_cuts.append(Cut(start=raw["start"], end=raw["end"], score=raw["score"], contributions=raw.get("contributions", {})))

            if not accepted_cuts:
                return {"erro": "Nenhum corte aceito"}

            from ..export.ffmpeg import export_cuts, export_compilation
            clips = export_cuts(project["video_path"], accepted_cuts, output / "clips_approved", project["settings"]["aspect"], project["settings"]["export_mode"])
            compiled = export_compilation(clips, output / "compilation-approved.mp4")
            return {"ok": True, "clips": len(clips), "compilado": str(compiled)}

        analyze_button.click(run_analysis, [video, url, manual, ignore, preset, target, aspect], [status, gallery, accepted, project_state, selected])
        export_button.click(export_selected, [project_state, accepted], export_status)

        with gr.Tab("Sobre"):
            gr.Markdown("A revisão humana vem primeiro. Depois será possível ativar uma classificação visual local opcional.")

    return app
