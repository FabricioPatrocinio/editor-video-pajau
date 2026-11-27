from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import gradio as gr

from ..ai.config import check_ai_ready, load_ai_settings
from ..ai.style import MOMENT_TYPES, ORDERS, VIDEO_TYPES, compose_briefing, load_style, record_feedback, save_style_text
from ..analysis.transcribe import transcription_enabled
from ..export.transitions import TRANSITIONS, make_preview
from ..pipeline import export_plan, find_candidates, load_candidates, plan_with_ai, video_path

STEP = 5.0


def _file_path(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("path")
    return getattr(value, "name", None) or str(value)


def _seconds(text: str) -> float:
    value = 0.0
    for part in text.strip().split(":"):
        value = value * 60 + float(part)
    return value


def _time_text(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _parse_intervals(text: str) -> list[list[float]]:
    intervals = []
    for item in (text or "").split(","):
        try:
            start, end = item.strip().split("-", 1)
            intervals.append([_seconds(start), _seconds(end)])
        except ValueError:
            pass
    return intervals


def _status_text() -> str:
    settings = load_ai_settings()
    problem = check_ai_ready(settings)
    if problem:
        return f"⚠️ {problem}"
    transcription = "ligada" if transcription_enabled() else "desligada"
    return f"IA: **{settings.label}** · transcrição: **{transcription}** · limite: **US$ {settings.daily_limit_usd:.2f}/dia**"


def _overview(plan: list[dict], accepted: list[str] | None = None) -> str:
    if not plan:
        return "Ainda não existe um plano."
    total = sum(item["end"] - item["start"] for item in plan)
    lines = [f"**{len(plan)} trechos · {_time_text(total)} de vídeo**\n"]
    for index, item in enumerate(plan, 1):
        mark = ("✅ " if item["id"] in accepted else "▫️ ") if accepted is not None else ""
        transition = "" if index == 1 else f" ⟶ _{item['transition']}_"
        lines.append(f"{index}. {mark}`{_time_text(item['start'])}–{_time_text(item['end'])}` **{item['kind']}**{transition} — {item['reason']}")
    return "\n".join(lines)


def _view(output: str, plan: list[dict], transcripts: dict, index: int):
    """Título, prévia em vídeo, motivo, transcrição e transição do trecho atual."""
    if not plan or index >= len(plan):
        return "### Revisão concluída. Gere o vídeo abaixo.", None, "", "", "corte"
    item = plan[index]
    title = f"### Trecho {index + 1} de {len(plan)} — {item['kind']} — {_time_text(item['start'])} a {_time_text(item['end'])} ({item['end'] - item['start']:.0f}s)"
    preview = None
    try:
        name = f"{item['id']}-{item['start']:.0f}-{item['end']:.0f}.mp4"
        preview = str(make_preview(video_path(Path(output)), item["start"], item["end"], Path(output) / "previas" / name))
    except Exception:
        pass
    return title, preview, item["reason"], transcripts.get(item["id"], ""), item.get("transition", "corte")


def build_app():
    style = load_style()

    with gr.Blocks(title="Pajau") as app:
        gr.Markdown("# Pajau\nDiga que vídeo você quer. A IA escolhe os trechos, você confere e gera.")
        gr.Markdown(_status_text())

        output_state = gr.State("")
        plan_state = gr.State([])
        transcripts_state = gr.State({})
        index_state = gr.State(0)
        accepted_state = gr.State([])

        with gr.Tab("1. Pedido"):
            with gr.Row():
                video = gr.File(label="Live", file_types=[".mp4", ".mkv", ".mov", ".webm"])
                video_text = gr.Textbox(label="ou cole o caminho do arquivo (melhor para lives grandes)",
                                        placeholder="/home/voce/Vídeos/live.mp4")
            with gr.Row():
                game = gr.Textbox(label="Jogo", placeholder="Ex.: Elden Ring")
                video_type = gr.Dropdown(VIDEO_TYPES, value=VIDEO_TYPES[0], label="Tipo de vídeo")
                duration = gr.Number(label="Minutos", value=10, minimum=1, maximum=60)
                aspect = gr.Radio(["16:9", "9:16"], value="16:9", label="Formato")
            moments = gr.CheckboxGroup(MOMENT_TYPES, value=MOMENT_TYPES[:3], label="Priorizar")
            order = gr.Radio(ORDERS, value=ORDERS[0], label="Ordem")
            extra = gr.Textbox(label="Algo mais? (opcional)", lines=2, placeholder="Ex.: foca na luta contra a Malenia")
            avoid = gr.Textbox(label="Ignorar", lines=2, placeholder="Ex.: tentativas repetidas, leitura de chat, loja e menus")

            gr.Examples(
                label="Exemplos — clique para preencher",
                inputs=[game, video_type, moments, order, extra, avoid, duration],
                examples=[
                    ["Elden Ring", "Só vitórias contra bosses", ["Vitória em boss", "Reação forte"], "Ordem da live",
                     "Só a tentativa que deu certo: uns 10s antes do golpe final até a comemoração.",
                     "tentativas que falharam, exploração sem ação, menus e inventário", 10],
                    ["Minecraft", "Engraçados", ["Morte engraçada", "Reação forte", "Papo com o chat"], "Mais forte primeiro",
                     "Ritmo rápido, trechos de 15 a 30s.", "leitura de doações, pausas, telas de loading", 8],
                    ["", "Short vertical", ["Reação forte", "Jogada difícil"], "IA decide",
                     "Um único momento de até 60s que se entenda sozinho.",
                     "trechos que dependem do que aconteceu antes", 1],
                    ["", "Resumo da live", ["Vitória em boss", "Jogada difícil", "Papo com o chat"], "Ordem da live",
                     "Conte a história da live do começo ao fim.", "conversa longa sem jogo, AFK, intervalo", 15],
                ],
            )
            with gr.Accordion("💡 Como pedir bem", open=False):
                gr.Markdown(
                    "- Diga **onde o corte começa e termina**: \"10s antes do golpe final até a comemoração\".\n"
                    "- No **Ignorar**, seja concreto: \"tentativas que falharam\" funciona melhor que \"partes chatas\".\n"
                    "- **Uma ideia por pedido.** Short e vídeo longo são pedidos separados.\n"
                    "- A IA vê **3 fotos por trecho** e a fala (com a transcrição ligada). Detalhes pequenos na tela podem escapar.\n"
                    "- O que vale para todo vídeo (seu ritmo, transições) vai no **Meu estilo**, não no pedido.\n"
                    "- Plano ruim? Ajuste o pedido e use **Refazer só o plano**, que sai bem mais barato."
                )

            with gr.Accordion("Mais opções", open=False):
                ignore =gr.Textbox(label="Pular estes tempos", placeholder="Ex.: 0:00-10:00, 2:30:00-2:32:00")
                my_style = gr.Textbox(
                    label="Meu estilo (vai em toda análise)", lines=3, value=style["estilo"],
                    placeholder="Ex.: Canal de soulslike. Gosto de cortes secos, ritmo rápido e de manter a reação depois da vitória.",
                )
                with gr.Row():
                    save_style = gr.Button("Salvar meu estilo", size="sm")
                    style_info = gr.Markdown(f"A IA já aprendeu com {len(style['aprendizado'])} decisões suas.")

            with gr.Row():
                analyze_button = gr.Button("Analisar com IA", variant="primary")
                replan_button = gr.Button("Refazer só o plano (mais barato)")
            status = gr.Markdown("")

        with gr.Tab("2. Revisar e gerar"):
            overview = gr.Markdown("Ainda não existe um plano.")
            accept_all = gr.Button("Aceitar tudo e gerar o vídeo", variant="primary")
            gr.Markdown("---")
            title = gr.Markdown("")
            preview = gr.Video(label="Prévia do trecho", height=360)
            reason = gr.Textbox(label="Por que a IA escolheu", lines=2, interactive=False)
            transcript = gr.Textbox(label="O que foi dito", lines=2, interactive=False)
            with gr.Row():
                start_earlier = gr.Button("⏪ Começa 5s antes", size="sm")
                start_later = gr.Button("Começa 5s depois ⏩", size="sm")
                end_earlier = gr.Button("⏪ Termina 5s antes", size="sm")
                end_later = gr.Button("Termina 5s depois ⏩", size="sm")
            transition = gr.Dropdown(list(TRANSITIONS), value="corte", label="Transição de entrada")
            with gr.Row():
                reject = gr.Button("Não quero", size="lg")
                approve = gr.Button("Gostei", variant="primary", size="lg")
            export_button = gr.Button("Gerar vídeo só com os que gostei", variant="primary")
            result = gr.Video(label="Vídeo final")
            result_path = gr.Markdown("")

        view_outputs = [title, preview, reason, transcript, transition]
        plan_outputs = [status, overview, *view_outputs, output_state, plan_state, transcripts_state, index_state, accepted_state]
        request_inputs = [game, video_type, moments, order, extra, avoid, duration]

        def _plan(output, candidates, game, vtype, moments, order, extra, avoid, minutes, progress):
            settings = load_ai_settings()
            progress(0.92, f"{settings.label} montando o plano...")
            briefing = compose_briefing(game or "", vtype or "", moments or [], order or "", extra or "")
            plan = plan_with_ai(Path(output), candidates, briefing, avoid or "", float(minutes or 10) * 60)
            data = [asdict(item) for item in plan.items]
            transcripts = {c.id: c.transcript for c in candidates}
            message = (
                f"✅ {len(candidates)} candidatos analisados, {len(data)} trechos escolhidos. Veja a aba **2. Revisar e gerar**.\n\n"
                f"{plan.summary}\n\n_{plan.usage}_"
            )
            return (message, _overview(data), *_view(str(output), data, transcripts, 0), str(output), data, transcripts, 0, [])

        def _fail(message, output=""):
            return (message, "Ainda não existe um plano.", "", None, "", "", "corte", output, [], {}, 0, [])

        def run_analysis(video_file, video_text, ignore_text, game, vtype, moments, order, extra, avoid, minutes, progress=gr.Progress()):
            source = (video_text or "").strip().strip("'\"") or _file_path(video_file)
            if source and not Path(source).exists():
                return _fail(f"Arquivo não encontrado: {source}")
            if not source:
                return _fail("Escolha a live primeiro.")
            problem = check_ai_ready()
            if problem:
                return _fail(problem)
            try:
                report = lambda fraction, text: progress(fraction * 0.9, desc=text)
                output, candidates = find_candidates(source, float(minutes or 10) * 60, _parse_intervals(ignore_text), progress=report)
                if not candidates:
                    return _fail("Nenhum candidato encontrado na live.", str(output))
                return _plan(output, candidates, game, vtype, moments, order, extra, avoid, minutes,
                             lambda f, t: progress(f, desc=t))
            except Exception as error:
                return _fail(f"Erro: {error}")

        def replan(output, game, vtype, moments, order, extra, avoid, minutes, progress=gr.Progress()):
            if not output:
                return _fail("Analise uma live primeiro; depois este botão refaz só o plano.")
            try:
                return _plan(Path(output), load_candidates(Path(output)), game, vtype, moments, order, extra, avoid,
                             minutes, lambda f, t: progress(f, desc=t))
            except Exception as error:
                return _fail(f"Erro: {error}", output)

        def adjust(output, plan, transcripts, index, field, delta):
            if not plan or index >= len(plan):
                return (*_view(output, plan, transcripts, index), plan, _overview(plan))
            item = dict(plan[index])
            item[field] = max(0.0, item[field] + delta)
            if item["end"] - item["start"] < 3:
                return (*_view(output, plan, transcripts, index), plan, _overview(plan))
            plan = list(plan)
            plan[index] = item
            return (*_view(output, plan, transcripts, index), plan, _overview(plan))

        def set_transition(plan, index, value):
            if plan and index < len(plan):
                plan = list(plan)
                plan[index] = {**plan[index], "transition": value}
            return plan

        def decide(output, plan, transcripts, index, accepted, liked):
            if not plan or index >= len(plan):
                return (*_view(output, plan, transcripts, index), index, accepted, _overview(plan, accepted))
            item = plan[index]
            accepted = [value for value in accepted if value != item["id"]] + ([item["id"]] if liked else [])
            record_feedback(item["kind"], item["reason"], liked)
            index += 1
            return (*_view(output, plan, transcripts, index), index, accepted, _overview(plan, accepted))

        def export(output, plan, aspect_value, only_ids, progress):
            if not output or not plan:
                return None, "Analise uma live primeiro."
            items = plan if only_ids is None else [item for item in plan if item["id"] in only_ids]
            if not items:
                return None, "Marque pelo menos um trecho com Gostei."
            progress(0.1, desc=f"Cortando {len(items)} trechos e aplicando transições...")
            try:
                path = export_plan(Path(output), items, aspect_value)
                return str(path), f"Salvo em `{path}`"
            except Exception as error:
                return None, f"Erro: {error}"

        def save_my_style(text):
            save_style_text(text or "")
            return f"Estilo salvo. A IA já aprendeu com {len(load_style()['aprendizado'])} decisões suas."

        analyze_button.click(run_analysis, [video, video_text, ignore, *request_inputs], plan_outputs)
        replan_button.click(replan, [output_state, *request_inputs], plan_outputs)
        save_style.click(save_my_style, my_style, style_info)

        for button, field, delta in (
            (start_earlier, "start", -STEP), (start_later, "start", STEP),
            (end_earlier, "end", -STEP), (end_later, "end", STEP),
        ):
            button.click(adjust, [output_state, plan_state, transcripts_state, index_state, gr.State(field), gr.State(delta)],
                         [*view_outputs, plan_state, overview])
        transition.input(set_transition, [plan_state, index_state, transition], plan_state)

        for button, liked in ((approve, True), (reject, False)):
            button.click(decide, [output_state, plan_state, transcripts_state, index_state, accepted_state, gr.State(liked)],
                         [*view_outputs, index_state, accepted_state, overview])

        def export_all(output, plan, aspect_value, progress=gr.Progress()):
            return export(output, plan, aspect_value, None, progress)

        def export_liked(output, plan, aspect_value, accepted, progress=gr.Progress()):
            return export(output, plan, aspect_value, accepted, progress)

        accept_all.click(export_all, [output_state, plan_state, aspect], [result, result_path])
        export_button.click(export_liked, [output_state, plan_state, aspect, accepted_state], [result, result_path])

    return app
