from __future__ import annotations

import argparse
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


def build_app():
    with gr.Blocks(title="Pajau - Highlights") as app:
        gr.Markdown("# Pajau\nGerador automático de melhores momentos sem IA/ML.")
        with gr.Tab("Analisar"):
            video = gr.File(label="Vídeo local", file_types=[".mp4", ".mkv", ".mov", ".webm"])
            url = gr.Textbox(label="Ou URL do YouTube", placeholder="https://youtube.com/watch?v=...")
            chat = gr.File(label="Replay do chat (JSON)", file_types=[".json"])
            manual = gr.File(label="Timestamps manuais (TXT/CSV)", file_types=[".txt", ".csv"])
            preset = gr.Dropdown(["highlights_10min", "shorts_60s_vertical", "react_compilation"], value="highlights_10min", label="Preset")
            target = gr.Number(value=600, label="Duração final em segundos")
            aspect = gr.Radio(["16:9", "9:16"], value="16:9", label="Formato")
            run = gr.Button("Analisar", variant="primary")

            status = gr.JSON(label="Resultado")
            figure = gr.Image(label="Curva de pontuação")

            def run_analysis(video, url, chat, manual, preset, target, aspect):
                source = _file_path(video)
                if not source:
                    source = url.strip() if url else ""
                if not source:
                    return {"erro": "Selecione um vídeo local ou informe uma URL"}, None

                run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
                output = Path("output") / f"web-{run_id}"
                output.mkdir(parents=True, exist_ok=True)

                args = argparse.Namespace(
                    input=source if not source.startswith(("http://", "https://")) else None,
                    url=source if source.startswith(("http://", "https://")) else None,
                    chat=_file_path(chat),
                    manual=_file_path(manual),
                    preset=preset,
                    target_duration=float(target),
                    max_cuts=None,
                    aspect=aspect,
                    cache=str(Path("cache") / f"web-{run_id}"),
                    output=str(output),
                    review_only=False,
                )

                try:
                    analyze(args)
                    project = output / "project.json"
                    return {
                        "ok": True,
                        "cortes": str(project),
                        "compilado": str(output / "compilation.mp4"),
                        "prévias": str(output / "previews"),
                        "csv": str(output / "cuts.csv"),
                    }, str(output / "score.png")
                except Exception as error:
                    return {"erro": str(error)}, None

            run.click(run_analysis, [video, url, chat, manual, preset, target, aspect], [status, figure])

        with gr.Tab("Sobre"):
            gr.Markdown("A seleção usa áudio, chat, heatmap, cenas, silêncio e timestamps manuais. Nenhum modelo de IA decide os cortes.")
    return app
