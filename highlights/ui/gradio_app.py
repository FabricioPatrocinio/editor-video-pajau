from __future__ import annotations

from pathlib import Path

import gradio as gr


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

            def placeholder(video, url, chat, manual, preset, target, aspect):
                source = video if video is not None else url
                if not source:
                    return {"erro": "Selecione um vídeo local ou informe uma URL"}, None
                return {
                    "aviso": "Use o comando CLI para processar agora.",
                    "fonte": str(source),
                    "preset": preset,
                    "duracao": target,
                    "aspecto": aspect,
                }, None

            run.click(placeholder, [video, url, chat, manual, preset, target, aspect], [status, figure])

        with gr.Tab("Sobre"):
            gr.Markdown("A seleção usa áudio, chat, heatmap, cenas, silêncio e timestamps manuais. Nenhum modelo de IA decide os cortes.")
    return app
