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
    with gr.Blocks(title="Pajau - Revisão rápida") as app:
        gr.Markdown("# Pajau\nEscolha um vídeo e avalie cada candidato com **Gostei** ou **Não quero**.")

        project_state = gr.State("")
        choices_state = gr.State([])
        accepted_state = gr.State([])
        index_state = gr.State(0)
        preview_state = gr.State({})

        video = gr.File(label="Vídeo original", file_types=[".mp4", ".mkv", ".mov", ".webm"])
        manual = gr.File(label="Momentos positivos opcionais", file_types=[".txt", ".csv"])
        ignore = gr.Textbox(label="Partes a ignorar, opcional", placeholder="Ex.: 0-600, 10800-11200")
        find_button = gr.Button("Encontrar candidatos", variant="primary")

        progress = gr.Markdown("Escolha um vídeo e clique em Encontrar candidatos.")
        gallery = gr.Gallery(label="Candidato atual", columns=3, height="auto")

        with gr.Row():
            reject_button = gr.Button("Não quero", size="lg")
            approve_button = gr.Button("Gostei", variant="primary", size="lg")

        export_button = gr.Button("Gerar vídeo com os gostados", variant="primary")
        result = gr.Textbox(label="Vídeo final", interactive=False)

        def run_analysis(video, manual, ignore):
            source = _file_path(video)
            if not source:
                return "Escolha um vídeo primeiro.", [], "", [], [], 0, {}

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
                input=source,
                url=None,
                chat=None,
                manual=_file_path(manual),
                preset="highlights_10min",
                target_duration=600,
                max_cuts=None,
                aspect="16:9",
                cache=str(Path("cache") / f"web-{run_id}"),
                output=str(output),
                review_only=True,
                ignore_intervals=ignore_intervals,
            )

            try:
                analyze(args)
                project_path = output / "project.json"
                project = json.loads(project_path.read_text(encoding="utf-8"))
                choices = []
                previews = {}

                for index, cut in enumerate(project["cuts"], 1):
                    choices.append(f"Corte {index:02d} — {_time_text(cut['start'])} a {_time_text(cut['end'])}")
                    previews[index - 1] = [
                        (str(output / "previews" / f"clip_{index:02d}_{position}.jpg"), position)
                        for position in ("start", "middle", "end")
                        if (output / "previews" / f"clip_{index:02d}_{position}.jpg").exists()
                    ]

                if not choices:
                    return "Nenhum candidato encontrado.", [], str(output), [], [], 0, {}

                return f"Candidato 1 de {len(choices)}", previews[0], str(output), choices, [], 0, previews
            except Exception as error:
                return f"Erro: {error}", [], "", [], [], 0, {}

        def decide(index, choices, accepted, previews, liked):
            if not choices:
                return "Nenhum candidato para avaliar.", [], choices, accepted, index, previews

            if liked:
                accepted = list(dict.fromkeys(accepted + [choices[index]]))

            next_index = index + 1
            if next_index >= len(choices):
                return f"Concluído — {len(accepted)} corte(s) gostado(s).", [], choices, accepted, next_index, previews

            return f"Candidato {next_index + 1} de {len(choices)}", previews.get(next_index, []), choices, accepted, next_index, previews

        def export_selected(project_dir, accepted):
            if not project_dir:
                return "Encontre os candidatos primeiro."

            output = Path(project_dir)
            project = json.loads((output / "project.json").read_text(encoding="utf-8"))
            accepted_cuts = []

            for index, cut in enumerate(project["cuts"]):
                label = f"Corte {index + 1:02d} — {_time_text(cut['start'])} a {_time_text(cut['end'])}"
                if label in accepted:
                    from ..models import Cut
                    accepted_cuts.append(Cut(start=cut["start"], end=cut["end"], score=cut["score"], contributions=cut.get("contributions", {})))

            if not accepted_cuts:
                return "Você ainda não marcou nenhum corte como Gostei."

            from ..export.ffmpeg import export_cuts, export_compilation
            clips = export_cuts(project["video_path"], accepted_cuts, output / "clips_gostados", "16:9", project["settings"]["export_mode"])
            compiled = export_compilation(clips, output / "compilation-gostados.mp4")
            return str(compiled)

        find_button.click(
            run_analysis,
            [video, manual, ignore],
            [progress, gallery, project_state, choices_state, accepted_state, index_state, preview_state],
        )

        approve_button.click(
            decide,
            [index_state, choices_state, accepted_state, preview_state, gr.State(True)],
            [progress, gallery, choices_state, accepted_state, index_state, preview_state],
        )
        reject_button.click(
            decide,
            [index_state, choices_state, accepted_state, preview_state, gr.State(False)],
            [progress, gallery, choices_state, accepted_state, index_state, preview_state],
        )
        export_button.click(export_selected, [project_state, accepted_state], result)

    return app
