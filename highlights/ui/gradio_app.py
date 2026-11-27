from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import gradio as gr

from ..ai.config import check_ai_ready, load_ai_settings
from ..ai.style import MOMENT_TYPES, ORDERS, VIDEO_TYPES, compose_briefing, load_style, save_style_text
from ..analysis.transcribe import transcription_enabled
from ..export.transitions import TRANSITIONS, make_preview
from ..export.covers import retext_cover, scene_candidates, scenes_sheet, use_scene
from ..export.shorts import CORNERS, LAYOUTS, load_settings, preview_frame, save_settings
from ..pipeline import (analysis_mode, export_plan, find_candidates, find_segments_with_map, load_candidates,
                        make_publication_covers, muted_warning, plan_with_ai, publication_text, video_path,
                        write_publication)

STEP = 5.0

# Visual: cartões, passos numerados, vídeos com altura máxima e barra de passos flutuante no rodapé.
CSS = """
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; padding-bottom: 120px !important; }
#pj-header { align-items: center; }
#pj-header h1 { margin: 0; font-size: 30px; }
#pj-ia { text-align: right; opacity: .85; font-size: 14px; }
.pj-card { border: 1px solid var(--border-color-primary); border-radius: 16px; padding: 18px !important;
           background: var(--block-background-fill); gap: 12px; }
.pj-step p { font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
             color: var(--color-accent); margin: 0; }
.pj-hint, .pj-hint p { font-size: 13px; opacity: .75; }
.pj-cta { border-color: var(--color-accent) !important; }
#pj-status { min-height: 90px; border-radius: 12px; padding: 10px 12px; background: var(--background-fill-secondary); }
.pj-big { min-height: 58px !important; font-size: 18px !important; }
#pj-review-video video, #pj-result video { max-height: 62vh; object-fit: contain; background: #000; }
#pj-short-preview img { max-height: 380px; object-fit: contain; }
#pj-covers img { object-fit: contain !important; }
#pj-scenes .thumbnail-item { cursor: pointer; }
#pajau-nav { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); z-index: 1000;
             width: min(760px, calc(100vw - 24px)); padding: 8px; border-radius: 16px; gap: 8px;
             background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
             box-shadow: 0 10px 34px rgba(0, 0, 0, .45); flex-wrap: nowrap !important; }
#pajau-nav button { min-width: 0 !important; }
@media (max-width: 720px) {
  .gradio-container { padding: 8px 8px 110px !important; }
  #pj-header h1 { font-size: 24px; }
  #pj-ia { text-align: left; }
  #pj-header { flex-direction: column; align-items: flex-start; gap: 4px; }
  #pajau-nav { bottom: 8px; padding: 6px; }
  #pajau-nav button { font-size: 13px !important; padding: 8px 4px !important; }
  .pj-card { padding: 12px !important; }
}
"""
SCROLL_TOPO = "() => window.scrollTo({top: 0, behavior: 'smooth'})"
SCROLL_GERAR = "() => document.getElementById('pajau-gerar')?.scrollIntoView({behavior: 'smooth', block: 'start'})"
# Depois do último trecho revisado, leva a pessoa até o "Gerar vídeo".
SCROLL_SE_ACABOU = ("() => { const t = document.querySelector('#pj-review-video')?.closest('.pj-card')?.innerText || '';"
                    " if (t.includes('Revisão concluída')) " + SCROLL_GERAR[6:] + "; }")


def windows_para_wsl(caminho: str) -> str:
    """No WSL, aceita o caminho do Windows colado (C:\\Users\\...) e troca por /mnt/c/Users/..."""
    if len(caminho) > 2 and caminho[1] == ":" and caminho[2] in "\\/" and Path("/mnt/c").exists():
        return f"/mnt/{caminho[0].lower()}/" + caminho[3:].replace("\\", "/")
    return caminho


def keep_upload(path: str, folder: Path = Path("data") / "lives") -> str:
    """O upload fica numa pasta temporária que o Gradio apaga ao fechar. Move a live para data/lives
    (na mesma partição é instantâneo), para dar para refazer o plano ou gerar de novo depois."""
    import shutil
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(path).name
    if not target.exists():
        shutil.move(path, target)
    return str(target.resolve())


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
    mode = "mapa da live inteira" if analysis_mode() == "mapa" else "picos de áudio"
    return f"IA: **{settings.label}** · análise: **{mode}** · transcrição: **{transcription}**"


# Durações sugeridas por formato (veja o README: "Quanto tempo deve ter o vídeo").
DURATION = {
    "16:9": dict(label="Duração (minutos)", value=10, minimum=1, maximum=60,
                 info="Sugestão: 8 a 12 min. A partir de 8 min o YouTube libera anúncios no meio do vídeo."),
    "9:16": dict(label="Duração (segundos)", value=45, minimum=5, maximum=180,
                 info="Sugestão: 30 a 60 s. Shorts podem ter até 3 min, mas os curtos são vistos até o fim com mais frequência."),
}
TRANSITION_NAMES = [("Corte seco (padrão)", "corte"), ("Dissolver", "fade"),
                    ("Escurecer (mudou de assunto)", "fade_preto"), ("Deslizar", "deslizar")]


def target_seconds(duration, aspect: str) -> float:
    """A duração vem em segundos no Short e em minutos no vídeo horizontal."""
    value = float(duration or DURATION.get(aspect, DURATION["16:9"])["value"])
    return value if aspect == "9:16" else value * 60


def friendly_reason(text: str) -> str:
    """Troca os "t=544" que a IA escreve pelo horário da live (9:04)."""
    return re.sub(r"\bt=(\d+(?:\.\d+)?)", lambda m: _time_text(float(m.group(1))), text or "")


def _overview(plan: list[dict], kept: list[int] | None = None) -> str:
    if not plan:
        return "Ainda não existe um plano."
    lines = []
    for index, item in enumerate(plan):
        mark = ("✅" if index in kept else "❌") if kept is not None else "•"
        lines.append(f"{mark} **{index + 1}. {item.get('chapter') or item['kind']}** · "
                     f"{_time_text(item['start'])}–{_time_text(item['end'])} — {friendly_reason(item['reason'])}")
    return "\n\n".join(lines)


LAYOUT_NAMES = {code: name for name, code in LAYOUTS.items()}


def _shorts(layout_name, zoom, corner, size, follow, subtitles) -> dict:
    return {"layout": LAYOUTS.get(layout_name, "jogo"), "zoom": zoom, "corner": corner, "camera_size": size,
            "follow": bool(follow), "subtitles": bool(subtitles)}


OUTPUT_DIR = Path("output")


def previous_analyses() -> list[tuple[str, str]]:
    """Análises já feitas (com plano da IA), da mais nova para a mais antiga."""
    from datetime import datetime
    plans = sorted(OUTPUT_DIR.glob("*/ia-plan.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [(f"{p.parent.name[:60]} · {datetime.fromtimestamp(p.stat().st_mtime):%d/%m %H:%M}", p.parent.name)
            for p in plans]


def _plan_item(raw: dict):
    from dataclasses import fields
    from ..ai.plan import PlanItem
    names = {f.name for f in fields(PlanItem)}
    return PlanItem(**{k: v for k, v in raw.items() if k in names})


def _gallery(covers: list[dict]):
    """As 3 capas, cada uma num quadro próprio (inteira, sem cortar, com botão de baixar)."""
    updates = []
    for number in range(1, 4):
        cover = covers[number - 1] if number <= len(covers) else None
        label = f"Capa {number}" + (f" · {cover['why'][:60]}" if cover and cover.get("why") else "")
        updates.append(gr.Image(value=cover["path"] if cover else None, label=label, visible=cover is not None))
    return tuple(updates)


def _nav(step: int, plan: list[dict] | None = None, index: int = 0):
    """Destaca o passo atual na barra e mostra a tela certa (1 = pedido, 2 = revisar, 3 = gerar)."""
    total = len(plan or [])
    review = f"② Revisar ({min(index, total)}/{total})" if total else "② Revisar"
    variant = lambda number: "primary" if step == number else "secondary"
    return (gr.Button(variant=variant(1)),
            gr.Button(value=review, variant=variant(2), interactive=bool(total)),
            gr.Button(variant=variant(3), interactive=bool(total)),
            gr.Column(visible=step == 1), gr.Column(visible=step != 1))


def _view(output: str, plan: list[dict], transcripts: dict, index: int):
    """Título, prévia em vídeo, motivo e transição do trecho atual."""
    if not plan or index >= len(plan):
        return "### ✅ Revisão concluída! Gere o vídeo logo abaixo.", None, "", "corte"
    item = plan[index]
    title = (f"### Trecho {index + 1} de {len(plan)} · {item.get('chapter') or item['kind']}\n"
             f"<small>{_time_text(item['start'])} → {_time_text(item['end'])} · {item['end'] - item['start']:.0f}s</small>")
    preview = None
    try:
        name = f"{item['id']}-{item['start']:.0f}-{item['end']:.0f}.mp4"
        preview = str(make_preview(video_path(Path(output)), item["start"], item["end"], Path(output) / "previas" / name))
    except Exception:
        pass
    return title, preview, f"**Por que entrou:** {friendly_reason(item['reason'])}", item.get("transition", "corte")


def build_app():
    style = load_style()
    short = load_settings()

    with gr.Blocks(title="Pajau") as app:
        with gr.Row(elem_id="pj-header"):
            gr.Markdown("# 🎬 Pajau\nDiga que vídeo você quer. A IA escolhe os trechos, você confere e gera.")
            gr.Markdown(_status_text(), elem_id="pj-ia")

        with gr.Row(elem_id="pajau-nav"):
            go_request = gr.Button("① Pedido", variant="primary")
            go_review = gr.Button("② Revisar", interactive=False)
            go_export = gr.Button("③ Gerar vídeo", interactive=False)

        output_state = gr.State("")
        plan_state = gr.State([])
        transcripts_state = gr.State({})
        index_state = gr.State(0)
        accepted_state = gr.State([])
        publication_state = gr.State({})

        # ---------------- 1. Pedido ----------------
        with gr.Column() as request_screen:
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, min_width=340):
                    with gr.Column(elem_classes="pj-card"):
                        gr.Markdown("1 · Sua live", elem_classes="pj-step")
                        video = gr.File(label="Arraste a live aqui", file_types=[".mp4", ".mkv", ".mov", ".webm"],
                                        height=150)
                        video_text = gr.Textbox(label="ou cole o caminho do arquivo (melhor para lives grandes)",
                                                placeholder="/home/voce/Vídeos/live.mp4")
                        with gr.Accordion("📂 Abrir uma análise anterior (sem gastar IA)", open=False):
                            with gr.Row():
                                previous = gr.Dropdown([], label="Análises", scale=4)
                                open_button = gr.Button("Abrir", scale=1, min_width=90)
                            gr.Markdown("_Se o vídeo mudou de lugar, cole o caminho novo acima antes de abrir._",
                                        elem_classes="pj-hint")

                    with gr.Column(elem_classes="pj-card"):
                        gr.Markdown("2 · O que você quer", elem_classes="pj-step")
                        with gr.Row():
                            game = gr.Textbox(label="Jogo", placeholder="Ex.: Elden Ring", min_width=160)
                            video_type = gr.Dropdown(VIDEO_TYPES, value=VIDEO_TYPES[0], label="Tipo de vídeo",
                                                     min_width=160)
                            duration = gr.Number(**DURATION["16:9"], min_width=130)
                        moments = gr.CheckboxGroup(MOMENT_TYPES, value=MOMENT_TYPES[:3], label="Priorizar")
                        order = gr.Radio(ORDERS, value=ORDERS[0], label="Ordem")
                        extra = gr.Textbox(label="Algo mais? (opcional)", lines=2,
                                           placeholder="Ex.: foca na luta contra a Malenia")
                        avoid = gr.Textbox(label="Ignorar", lines=2,
                                           placeholder="Ex.: tentativas repetidas, leitura de chat, loja e menus")
                        with gr.Accordion("✨ Exemplos de pedido", open=False):
                            gr.Examples(
                                label="Clique para preencher",
                                inputs=[game, video_type, moments, order, extra, avoid],
                                examples=[
                                    ["Elden Ring", "Só vitórias contra bosses", ["Vitória em boss", "Reação forte"],
                                     "Ordem da live", "Só a tentativa que deu certo: uns 10s antes do golpe final "
                                     "até a comemoração.", "tentativas que falharam, exploração sem ação, menus"],
                                    ["Minecraft", "Engraçados", ["Morte engraçada", "Reação forte", "Papo com o chat"],
                                     "Mais forte primeiro", "Ritmo rápido, trechos de 15 a 30s.",
                                     "leitura de doações, pausas, telas de loading"],
                                    ["", "Short vertical", ["Reação forte", "Jogada difícil"], "IA decide",
                                     "Um único momento de até 60s que se entenda sozinho.",
                                     "trechos que dependem do que aconteceu antes"],
                                ],
                            )
                        with gr.Accordion("💡 Como pedir bem", open=False):
                            gr.Markdown(
                                "- Diga **onde o corte começa e termina**: \"10s antes do golpe final até a comemoração\".\n"
                                "- No **Ignorar**, seja concreto: \"tentativas que falharam\" funciona melhor que \"partes chatas\".\n"
                                "- **Uma ideia por pedido.** Short e vídeo longo são pedidos separados.\n"
                                "- O que vale para todo vídeo vai no **Meu estilo** (em Mais opções).\n"
                                "- Plano ruim? Ajuste o pedido e use **Refazer só o plano**, que sai bem mais barato."
                            )
                        with gr.Accordion("⚙️ Mais opções", open=False):
                            ignore = gr.Textbox(label="Pular estes tempos", placeholder="Ex.: 0:00-10:00, 2:30:00-2:32:00")
                            my_style = gr.Textbox(
                                label="Meu estilo (vai em toda análise)", lines=3, value=style["estilo"],
                                placeholder="Ex.: Canal de soulslike. Gosto de cortes secos e de manter a reação depois da vitória.",
                            )
                            with gr.Row():
                                save_style = gr.Button("Salvar meu estilo", size="sm")
                                style_info = gr.Markdown("Vai junto em toda análise.", elem_classes="pj-hint")

                with gr.Column(scale=2, min_width=300):
                    with gr.Column(elem_classes="pj-card"):
                        gr.Markdown("3 · Formato", elem_classes="pj-step")
                        aspect = gr.Radio([("🖥️ Horizontal 16:9", "16:9"), ("📱 Short 9:16", "9:16")], value="16:9",
                                          show_label=False)
                        with gr.Column(visible=False) as short_box:
                            short_layout = gr.Radio(list(LAYOUTS), value=LAYOUT_NAMES[short["layout"]], label="Layout")
                            short_zoom = gr.Slider(0, 100, value=short["zoom"], step=5, visible=short["layout"] == "jogo",
                                                   label="Zoom no jogo", info="0 = vídeo inteiro · 100 = tela cheia")
                            with gr.Column(visible=short["layout"] == "camera") as camera_row:
                                short_corner = gr.Dropdown(CORNERS, value=short["corner"],
                                                           label="Onde fica a sua câmera na live")
                                short_size = gr.Slider(10, 50, value=short["camera_size"], step=1,
                                                       label="Largura da câmera (% da tela)")
                            short_follow = gr.Checkbox(value=short["follow"], label="🎯 Seguir a ação automaticamente")
                            short_subtitles = gr.Checkbox(value=short["subtitles"], label="💬 Legenda palavra a palavra")
                            short_preview_button = gr.Button("👀 Ver como fica", size="sm")
                            short_info = gr.Markdown("", elem_classes="pj-hint")
                            short_preview = gr.Image(show_label=False, height=380, visible=False, interactive=False,
                                                     elem_id="pj-short-preview")
                            gr.Markdown("_Tudo do Short é feito no seu PC, sem gastar IA._", elem_classes="pj-hint")

                    with gr.Column(elem_classes="pj-card pj-cta"):
                        gr.Markdown("4 · Analisar", elem_classes="pj-step")
                        analyze_button = gr.Button("🚀 Analisar com IA", variant="primary", size="lg")
                        replan_button = gr.Button("Refazer só o plano (mais barato)", size="sm")
                        status = gr.Markdown("_Leva de 2 a 10 minutos em lives longas. A revisão abre sozinha no final._",
                                             elem_id="pj-status")

        # ---------------- 2. Revisar ----------------
        # Tudo entra por padrão; a pessoa só tira o que não quer.
        with gr.Column(visible=False) as review_screen:
            with gr.Row(elem_classes="pj-card", equal_height=False):
                review_head = gr.Markdown("", scale=4)
                accept_all = gr.Button("🎬 Gerar vídeo agora", variant="primary", scale=1, min_width=200)

            with gr.Column(elem_classes="pj-card"):
                title = gr.Markdown("")
                preview = gr.Video(show_label=False, height=420, elem_id="pj-review-video", autoplay=True)
                reason = gr.Markdown("")
                with gr.Row():
                    reject = gr.Button("❌ Tirar este", variant="stop", size="lg", elem_classes="pj-big")
                    approve = gr.Button("✅ Manter e ver o próximo", variant="primary", size="lg", elem_classes="pj-big")
                with gr.Accordion("✂️ Ajustar este trecho", open=False):
                    with gr.Row():
                        start_earlier = gr.Button("⏪ Começar 5s antes", size="sm", min_width=120)
                        start_later = gr.Button("Começar 5s depois ⏩", size="sm", min_width=120)
                        end_earlier = gr.Button("⏪ Terminar 5s antes", size="sm", min_width=120)
                        end_later = gr.Button("Terminar 5s depois ⏩", size="sm", min_width=120)
                    transition = gr.Dropdown(TRANSITION_NAMES, value="corte", label="Como este trecho entra")

            with gr.Accordion("📋 Todos os trechos", open=False):
                overview = gr.Markdown("Ainda não existe um plano.")

        # ---------------- 3. Gerar ----------------
            with gr.Column(elem_classes="pj-card", elem_id="pajau-gerar"):
                gr.Markdown("③ Gerar vídeo", elem_classes="pj-step")
                export_button = gr.Button("🎬 Gerar vídeo", variant="primary", size="lg")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=2, min_width=300):
                        result = gr.Video(show_label=False, height=520, elem_id="pj-result")
                        result_path = gr.Markdown("", elem_classes="pj-hint")
                    with gr.Column(scale=3, min_width=300):
                        publication_box = gr.Textbox(label="📣 Título e descrição para publicar", lines=14,
                                                     buttons=["copy"], interactive=False)
                gr.Markdown("🖼️ Capas — use a setinha de cada uma para baixar", elem_classes="pj-step")
                with gr.Row(elem_id="pj-covers"):
                    covers_gallery = [gr.Image(label=f"Capa {n}", height=320, interactive=False, visible=False,
                                               min_width=200) for n in range(1, 4)]
                with gr.Row():
                    cover_number = gr.Radio([1, 2, 3], value=1, label="Capa", scale=1, min_width=160)
                    cover_text = gr.Textbox(label="Texto da capa", placeholder="Ex.: ELE NÃO ACREDITOU", scale=3)
                    cover_button = gr.Button("Trocar texto (sem IA)", scale=1, min_width=160)
                gr.Markdown("🎞️ Cenas mais fortes do vídeo — clique numa para usar na capa marcada acima",
                            elem_classes="pj-step")
                scenes_gallery = gr.Gallery(show_label=False, columns=6, height=230, object_fit="cover",
                                            allow_preview=False, interactive=False, elem_id="pj-scenes")
                with gr.Row():
                    ai_cover_button = gr.Button("🤖 Deixar a IA escolher as 3 melhores cenas e textos", min_width=260)
                    cover_info = gr.Markdown("_A IA olha uma imagem só com estas cenas. O uso real aparece aqui._",
                                             elem_classes="pj-hint")
                scenes_state = gr.State([])

        view_outputs = [title, preview, reason, transition]
        plan_outputs = [status, review_head, overview, *view_outputs, output_state, plan_state, transcripts_state,
                        index_state, accepted_state, publication_state, publication_box]
        request_inputs = [game, video_type, moments, order, extra, avoid, duration, aspect]
        short_inputs = [short_layout, short_zoom, short_corner, short_size, short_follow, short_subtitles]

        def _loaded(output, data, transcripts, summary, usage, publication, aspect_value, status_text):
            head = (f"### {len(data)} trechos · {_time_text(sum(i['end'] - i['start'] for i in data))} de vídeo\n"
                    f"{summary}" + (f"\n\n<small>{usage}</small>" if usage else ""))
            text = publication_text(publication, data, aspect_value)
            kept = list(range(len(data)))
            return (status_text, head, _overview(data, kept), *_view(str(output), data, transcripts, 0), str(output),
                    data, transcripts, 0, kept, publication, text)

        def _plan(output, candidates, game, vtype, moments, order, extra, avoid, minutes, aspect_value, progress):
            settings = load_ai_settings()
            progress(0.92, f"{settings.label} montando o plano...")
            briefing = compose_briefing(game or "", vtype or "", moments or [], order or "", extra or "")
            plan = plan_with_ai(Path(output), candidates, briefing, avoid or "", target_seconds(minutes, aspect_value),
                                aspect_value)
            data = [asdict(item) for item in plan.items]
            warning = muted_warning(Path(output))
            summary = (f"**{warning}**\n\n" if warning else "") + plan.summary
            return _loaded(output, data, {c.id: c.transcript for c in candidates}, summary, plan.usage,
                           plan.publication, aspect_value, f"✅ Pronto: {len(data)} trechos escolhidos.")

        def _fail(message, output=""):
            return (f"⚠️ {message}", "", "Ainda não existe um plano.", "", None, "", "corte", output, [], {}, 0, [],
                    {}, "")

        def run_analysis(video_file, video_text, ignore_text, game, vtype, moments, order, extra, avoid, minutes,
                         aspect_value, progress=gr.Progress()):
            source = windows_para_wsl((video_text or "").strip().strip("'\"")) or _file_path(video_file)
            if source and not Path(source).exists():
                return _fail(f"Arquivo não encontrado: {source}")
            if not source:
                return _fail("Escolha a live primeiro.")
            if not (video_text or "").strip():
                source = keep_upload(source)
            problem = check_ai_ready()
            if problem:
                return _fail(problem)
            try:
                report = lambda fraction, text: progress(fraction * 0.9, desc=text)
                target = target_seconds(minutes, aspect_value)
                if analysis_mode() == "mapa":
                    briefing = compose_briefing(game or "", vtype or "", moments or [], order or "", extra or "")
                    output, candidates, summary = find_segments_with_map(
                        source, briefing, avoid or "", target, _parse_intervals(ignore_text), progress=report)
                    if not candidates:
                        return _fail(f"A IA não achou trechos para o pedido no mapa da live. {summary}", str(output))
                else:
                    output, candidates = find_candidates(source, target, _parse_intervals(ignore_text), progress=report)
                    if not candidates:
                        return _fail("Nenhum candidato encontrado na live.", str(output))
                return _plan(output, candidates, game, vtype, moments, order, extra, avoid, minutes, aspect_value,
                             lambda f, t: progress(f, desc=t))
            except Exception as error:
                return _fail(f"Erro: {error}")

        def replan(output, game, vtype, moments, order, extra, avoid, minutes, aspect_value, progress=gr.Progress()):
            if not output:
                return _fail("Analise uma live primeiro; depois este botão refaz só o plano.")
            try:
                return _plan(Path(output), load_candidates(Path(output)), game, vtype, moments, order, extra, avoid,
                             minutes, aspect_value, lambda f, t: progress(f, desc=t))
            except Exception as error:
                return _fail(f"Erro: {error}", output)

        def open_previous(name, video_text, aspect_value):
            if not name:
                return _fail("Escolha uma análise na lista.")
            output = OUTPUT_DIR / name
            try:
                data = json.loads((output / "ia-plan.json").read_text(encoding="utf-8"))
                if not Path(video_path(output)).exists():
                    new_path = windows_para_wsl((video_text or "").strip().strip("'\""))
                    if not new_path or not Path(new_path).exists():
                        return _fail(f"O vídeo desta análise não está mais em `{video_path(output)}`. "
                                     "Cole o caminho atual da live no campo de cima e clique em Abrir de novo.")
                    project = json.loads((output / "project.json").read_text(encoding="utf-8"))
                    project["video_path"] = str(Path(new_path).resolve())
                    (output / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
                items = [asdict(_plan_item(raw)) for raw in data.get("approved", [])]
                try:
                    transcripts = {c.id: c.transcript for c in load_candidates(output)}
                except Exception:
                    transcripts = {}
                return _loaded(output, items, transcripts, data.get("summary", ""), "", data.get("publication") or {},
                               aspect_value, f"📂 Análise aberta: {len(items)} trechos, sem gastar IA.")
            except Exception as error:
                return _fail(f"Não deu para abrir: {error}")

        def adjust(output, plan, transcripts, index, kept, field, delta):
            if not plan or index >= len(plan):
                return (*_view(output, plan, transcripts, index), plan, _overview(plan, kept))
            item = dict(plan[index])
            item[field] = max(0.0, item[field] + delta)
            if item["end"] - item["start"] < 3:
                return (*_view(output, plan, transcripts, index), plan, _overview(plan, kept))
            plan = list(plan)
            plan[index] = item
            return (*_view(output, plan, transcripts, index), plan, _overview(plan, kept))

        def set_transition(plan, index, value):
            if plan and index < len(plan):
                plan = list(plan)
                plan[index] = {**plan[index], "transition": value}
            return plan

        def decide(output, plan, transcripts, index, kept, keep):
            if not plan or index >= len(plan):
                return (*_view(output, plan, transcripts, index), index, kept, _overview(plan, kept))
            kept = sorted(set(kept) | {index}) if keep else [i for i in kept if i != index]
            index += 1
            return (*_view(output, plan, transcripts, index), index, kept, _overview(plan, kept))

        def export(output, plan, aspect_value, only_ids, publication, shorts, progress):
            if not output or not plan:
                return None, "Analise uma live primeiro.", *[gr.skip()] * 7
            items = [plan[i] for i in sorted(only_ids) if i < len(plan)]
            if not items:
                return (None, "⚠️ Todos os trechos foram tirados. Mantenha pelo menos um.", *[gr.skip()] * 7)
            progress(0.05, desc=f"Preparando {len(items)} trechos...")
            try:
                notes: list[str] = []
                step = lambda done, total, text: progress(0.05 + 0.85 * done / max(1, total),
                                                          desc=f"{text}: trecho {min(done + 1, total)} de {total}")
                path = export_plan(Path(output), items, aspect_value, shorts if aspect_value == "9:16" else None,
                                   notes, step)
                # Capítulos refeitos com os trechos que realmente entraram no vídeo.
                text = write_publication(Path(output), publication, items, aspect_value)
                progress(0.95, desc="Montando as capas...")
                covers = make_publication_covers(Path(output), publication, items, aspect_value)
                first = covers[0]["text"] if covers else ""
                progress(0.97, desc="Separando as cenas mais fortes...")
                try:
                    scenes = scene_candidates(video_path(Path(output)), items, Path(output) / "capas" / "cenas")
                except Exception:
                    scenes = []
                warning = "".join(f"\n\n⚠️ {note}" for note in notes)
                return (str(path), f"✅ Salvo em `{path}`{warning}", text, *_gallery(covers), first,
                        [s["path"] for s in scenes], scenes)
            except Exception as error:
                return None, f"⚠️ Erro: {error}", *[gr.skip()] * 7

        def change_cover_text(output, number, text):
            try:
                return _gallery(retext_cover(Path(output) / "capas", int(number), text or ""))
            except Exception:
                return (gr.skip(),) * 3

        def pick_cover(output, number):
            try:
                covers = json.loads((Path(output) / "capas" / "capas.json").read_text(encoding="utf-8"))["covers"]
                return covers[int(number) - 1]["text"]
            except Exception:
                return gr.skip()

        def save_my_style(text):
            save_style_text(text or "")
            return "✅ Estilo salvo. Vai junto em toda análise."

        # Feedback na hora do clique: o botão muda e o painel mostra que começou.
        def busy(message):
            return (f"⏳ **{message}**\n\nPode deixar esta aba aberta. A barra abaixo mostra cada etapa.",
                    gr.Button(value="⏳ Analisando…", interactive=False), gr.Button(interactive=False))

        def idle():
            return gr.Button(value="🚀 Analisar com IA", interactive=True), gr.Button(interactive=True)

        nav_outputs = [go_request, go_review, go_export, request_screen, review_screen]
        after_plan = lambda plan, index: _nav(2 if plan else 1, plan, index)
        buttons = [analyze_button, replan_button]

        analyze_button.click(lambda: busy("Analisando a live…"), None, [status, *buttons], queue=False).then(
            run_analysis, [video, video_text, ignore, *request_inputs], plan_outputs, show_progress="full").then(
            idle, None, buttons).then(after_plan, [plan_state, index_state], nav_outputs).then(None, js=SCROLL_TOPO)
        replan_button.click(lambda: busy("Refazendo o plano…"), None, [status, *buttons], queue=False).then(
            replan, [output_state, *request_inputs], plan_outputs, show_progress="full").then(
            idle, None, buttons).then(after_plan, [plan_state, index_state], nav_outputs).then(None, js=SCROLL_TOPO)
        open_button.click(open_previous, [previous, video_text, aspect], plan_outputs).then(
            after_plan, [plan_state, index_state], nav_outputs).then(None, js=SCROLL_TOPO)
        def refresh_previous():
            choices = previous_analyses()
            return gr.Dropdown(choices=choices, value=choices[0][1] if choices else None)

        app.load(refresh_previous, None, previous)

        go_request.click(lambda plan, index: _nav(1, plan, index), [plan_state, index_state], nav_outputs).then(
            None, js=SCROLL_TOPO)
        go_review.click(lambda plan, index: _nav(2, plan, index), [plan_state, index_state], nav_outputs).then(
            None, js=SCROLL_TOPO)
        go_export.click(lambda plan, index: _nav(3, plan, index), [plan_state, index_state], nav_outputs).then(
            None, js=SCROLL_GERAR)
        save_style.click(save_my_style, my_style, style_info)

        for button, field, delta in (
            (start_earlier, "start", -STEP), (start_later, "start", STEP),
            (end_earlier, "end", -STEP), (end_later, "end", STEP),
        ):
            button.click(adjust, [output_state, plan_state, transcripts_state, index_state, accepted_state,
                                  gr.State(field), gr.State(delta)], [*view_outputs, plan_state, overview])
        transition.input(set_transition, [plan_state, index_state, transition], plan_state)

        for button, liked in ((approve, True), (reject, False)):
            button.click(decide, [output_state, plan_state, transcripts_state, index_state, accepted_state, gr.State(liked)],
                         [*view_outputs, index_state, accepted_state, overview]).then(
                lambda plan, index: _nav(3 if index >= len(plan) else 2, plan, index), [plan_state, index_state],
                nav_outputs).then(None, js=SCROLL_SE_ACABOU)

        def export_liked(output, plan, aspect_value, accepted, publication, layout, zoom, corner, size, follow,
                         subtitles, progress=gr.Progress()):
            return export(output, plan, aspect_value, accepted, publication,
                          _shorts(layout, zoom, corner, size, follow, subtitles), progress)

        aspect.change(lambda value: (gr.Column(visible=value == "9:16"), gr.Number(**DURATION[value])), aspect,
                      [short_box, duration])
        short_layout.change(lambda name: (gr.Column(visible=LAYOUTS.get(name) == "camera"),
                                          gr.Slider(visible=LAYOUTS.get(name) == "jogo")),
                            short_layout, [camera_row, short_zoom])
        for control in short_inputs:
            control.change(lambda *values: save_settings(_shorts(*values)) and None, short_inputs, None)

        def show_short_preview(output, plan, video_file, video_text, layout, zoom, corner, size, follow, subtitles):
            settings = _shorts(layout, zoom, corner, size, follow, subtitles)
            try:
                if output and plan:
                    item = plan[0]
                    source, seconds, focus = video_path(Path(output)), (item["start"] + item["end"]) / 2, item.get("focus", 0.5)
                else:
                    from ..download.youtube import probe_video
                    source = windows_para_wsl((video_text or "").strip().strip("'\"")) or _file_path(video_file)
                    if not source or not Path(source).exists():
                        return gr.Image(visible=False), "⚠️ Escolha a live primeiro."
                    seconds, focus = probe_video(source)["duration"] / 3, 0.5
                frame = preview_frame(source, seconds, settings, Path("data") / "previa-short.jpg", focus)
                hint = "" if output and plan else " Depois da análise, a prévia usa o primeiro trecho escolhido."
                return gr.Image(value=str(frame), visible=True), "Assim fica o Short." + hint
            except Exception as error:
                return gr.Image(visible=False), f"⚠️ Erro na prévia: {error}"

        short_preview_button.click(show_short_preview, [output_state, plan_state, video, video_text, *short_inputs],
                                   [short_preview, short_info])

        export_outputs = [result, result_path, publication_box, *covers_gallery, cover_text, scenes_gallery, scenes_state]

        def choose_scene(output, number, scenes, event: gr.SelectData):
            try:
                scene = scenes[event.index]
                covers = use_scene(Path(output) / "capas", int(number), video_path(Path(output)), scene["time"])
                return (*_gallery(covers), f"Capa {number} agora usa a cena de {_time_text(scene['time'])}.")
            except Exception as error:
                return (*[gr.skip()] * 3, f"⚠️ {error}")

        def ai_covers(output, scenes, publication, plan, aspect_value, progress=gr.Progress()):
            if not output or not scenes:
                return (*[gr.skip()] * 4, "⚠️ Gere o vídeo primeiro.")
            from ..ai.covers_ai import pick_covers
            from ..export.covers import make_covers
            try:
                progress(0.2, desc="A IA está olhando as cenas...")
                folder = Path(output) / "capas"
                sheet = scenes_sheet(scenes, folder / "cenas" / "folha.jpg")
                titles = (publication or {}).get("titles") or []
                ideas, usage = pick_covers(sheet, scenes, titles[0] if titles else "")
                if not ideas:
                    return (*[gr.skip()] * 4, "⚠️ A IA não devolveu capas. Tente de novo.")
                progress(0.8, desc="Montando as capas...")
                covers = make_covers(video_path(Path(output)), ideas, plan, folder, aspect_value)
                return (*_gallery(covers), covers[0]["text"], f"✅ Capas escolhidas pela IA. <small>{usage}</small>")
            except Exception as error:
                return (*[gr.skip()] * 4, f"⚠️ {error}")

        scenes_gallery.select(choose_scene, [output_state, cover_number, scenes_state], [*covers_gallery, cover_info])
        ai_cover_button.click(ai_covers, [output_state, scenes_state, publication_state, plan_state, aspect],
                              [*covers_gallery, cover_text, cover_info])
        accept_all.click(None, js=SCROLL_GERAR).then(
            export_liked, [output_state, plan_state, aspect, accepted_state, publication_state, *short_inputs],
            export_outputs)
        export_button.click(export_liked, [output_state, plan_state, aspect, accepted_state, publication_state,
                                           *short_inputs], export_outputs)
        cover_number.change(pick_cover, [output_state, cover_number], cover_text)
        cover_button.click(change_cover_text, [output_state, cover_number, cover_text], covers_gallery)

    return app
