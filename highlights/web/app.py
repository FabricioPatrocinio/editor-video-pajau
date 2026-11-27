"""Interface web do Pajau: FastAPI + Bootstrap + htmx (sem Node, tudo servido pelo Python).

Três telas, um botão principal em cada: Pedido → Conferir → Pronto.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..ai.style import load_style, save_style_text
from ..export.covers import COLORS, FONT_NAMES, FONTS, load_covers, restyle_cover, use_scene
from ..export.shorts import CORNERS, load_settings, preview_frame, save_settings
from ..export.transitions import TRANSITIONS, make_preview
from . import jobs
from .logic import (DURATION, LIVES_DIR, TRANSITION_NAMES, ai_label, briefing, clean_path, friendly_reason,
                    kept_items, load_review, parse_intervals, previous_analyses, project_dir, publication_parts,
                    safe_upload_name, save_review, target_seconds, time_text, total_seconds)

HERE = Path(__file__).resolve().parent
app = FastAPI(title="Pajau", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(time_text=time_text, quote=quote, friendly_reason=friendly_reason,
                             TRANSITION_NAMES=TRANSITION_NAMES, COLORS=COLORS, FONT_NAMES=FONT_NAMES)


def page(request: Request, template: str, **context) -> HTMLResponse:
    label, warning = ai_label()
    return templates.TemplateResponse(request, template, {"ai_label": label, "ai_warning": warning, **context})


def folder_of(name: str) -> Path:
    try:
        return project_dir(name)
    except FileNotFoundError:
        raise HTTPException(404, "Análise não encontrada.")


def file_url(folder: Path, path: str | Path) -> str:
    """Endereço de um arquivo da análise, com a data no fim para o navegador não usar cópia velha."""
    path = Path(path)
    relative = path.resolve().relative_to(folder)
    return f"/arquivo/{quote(folder.name)}/{quote(relative.as_posix())}?v={int(path.stat().st_mtime)}"


# ---------------- 1. Pedido ----------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return page(request, "pedido.html", step=1, recent=previous_analyses(), style=load_style()["estilo"],
                short=load_settings(), DURATION=DURATION, CORNERS=CORNERS)


@app.put("/enviar")
async def upload(request: Request, nome: str):
    """Recebe a live direto no disco (data/lives), aos pedaços: funciona com arquivos de vários GB."""
    LIVES_DIR.mkdir(parents=True, exist_ok=True)
    target = LIVES_DIR / safe_upload_name(nome)
    partial = target.with_suffix(target.suffix + ".parcial")
    with partial.open("wb") as out:
        async for chunk in request.stream():
            out.write(chunk)
    partial.replace(target)
    return JSONResponse({"caminho": str(target.resolve()), "nome": target.name})


def _shorts_from_form(form) -> dict:
    return {"layout": form.get("layout", "jogo"), "zoom": float(form.get("zoom") or 35),
            "follow": form.get("seguir") == "on", "subtitles": form.get("legenda") == "on",
            "corner": form.get("canto", CORNERS[0]), "camera_size": float(form.get("camera") or 25)}


@app.post("/previa-short", response_class=HTMLResponse)
async def short_preview(request: Request):
    form = await request.form()
    source = clean_path(form.get("caminho", ""))
    if not source or not Path(source).exists():
        return HTMLResponse('<p class="text-warning small mb-0">Escolha a live primeiro para ver a prévia.</p>')
    from ..download.youtube import probe_video
    out = Path("data") / "previa-short.jpg"
    preview_frame(source, probe_video(source)["duration"] / 3, _shorts_from_form(form), out)
    return HTMLResponse(f'<img src="/previa-short.jpg?v={int(out.stat().st_mtime)}" class="pj-short-preview">')


@app.get("/previa-short.jpg")
def short_preview_image():
    return FileResponse(Path("data") / "previa-short.jpg")


@app.post("/analisar")
async def analyze(request: Request):
    form = await request.form()
    source = clean_path(form.get("caminho", ""))
    aspect = "9:16" if form.get("formato") == "9:16" else "16:9"
    duration = form.get("duracao") or DURATION[aspect]["value"]
    request_text, game, avoid = form.get("pedido", ""), form.get("jogo", ""), form.get("ignorar", "")
    skip = parse_intervals(form.get("pular", ""))
    if form.get("estilo") is not None:
        save_style_text(form.get("estilo", ""))
    shorts = _shorts_from_form(form)
    save_settings({**load_settings(), **shorts, "aspect": aspect})

    def work(job: jobs.Job) -> str:
        from ..ai.config import check_ai_ready
        from ..pipeline import analysis_mode, find_candidates, find_segments_with_map, muted_warning, plan_with_ai
        if not source or not Path(source).exists():
            raise RuntimeError("Não achei a live. Envie o arquivo ou cole o caminho de novo.")
        problem = check_ai_ready()
        if problem:
            raise RuntimeError(problem)
        target, brief = target_seconds(duration, aspect), briefing(game, request_text, aspect, duration)
        if analysis_mode() == "mapa":
            output, candidates, summary = find_segments_with_map(
                source, brief, avoid, target, skip, progress=lambda f, t: job.report(f * 0.9, t))
            if not candidates:
                raise RuntimeError(f"A IA não achou trechos para o pedido. {summary}")
        else:
            output, candidates = find_candidates(source, target, skip, progress=lambda f, t: job.report(f * 0.9, t))
        job.report(0.92, "A IA está montando o vídeo…")
        plan = plan_with_ai(Path(output), candidates, brief, avoid, target, aspect)
        if not plan.items:
            raise RuntimeError(f"A IA não escolheu nenhum trecho. {plan.summary}")
        folder = Path(output).resolve()
        (folder / "revisao.json").unlink(missing_ok=True)
        review = load_review(folder)
        warning = muted_warning(folder)
        review.update(aspect=aspect, duration=duration, shorts=shorts, usage=plan.usage,
                      summary=(f"⚠️ {warning} " if warning else "") + plan.summary)
        save_review(folder, review)
        return f"/conferir/{quote(folder.name)}"

    job_id = jobs.start("Analisando a sua live", jobs.ANALYSIS_STEPS, work)
    return RedirectResponse(f"/progresso/{job_id}", status_code=303)


# ---------------- Progresso ----------------

@app.get("/progresso/{job_id}", response_class=HTMLResponse)
def progress_page(request: Request, job_id: str):
    job = jobs.JOBS.get(job_id)
    if not job:
        return RedirectResponse("/", status_code=303)
    return page(request, "progresso.html", step=1 if job.steps is jobs.ANALYSIS_STEPS else 2, job=job, job_id=job_id)


@app.get("/progresso/{job_id}/estado", response_class=HTMLResponse)
def progress_state(request: Request, job_id: str):
    job = jobs.JOBS.get(job_id)
    if job and job.done:
        return Response(headers={"HX-Redirect": job.result_url})
    return templates.TemplateResponse(request, "_progresso.html", {"job": job, "job_id": job_id})


# ---------------- 2. Conferir ----------------

def _review_context(folder: Path, review: dict, selected: int) -> dict:
    kept = kept_items(review)
    return {"name": folder.name, "review": review, "selected": selected, "kept_count": len(kept),
            "kept_time": time_text(total_seconds(kept)), "transitions": list(TRANSITIONS)}


@app.get("/conferir/{name}", response_class=HTMLResponse)
def review_page(request: Request, name: str):
    folder = folder_of(name)
    review = load_review(folder)
    from ..pipeline import video_path
    missing = not Path(video_path(folder)).exists()
    return page(request, "conferir.html", step=2, missing=missing, **_review_context(folder, review, 0))


@app.post("/conferir/{name}/religar")
def relink(name: str, caminho: str = Form("")):
    folder = folder_of(name)
    source = clean_path(caminho)
    if Path(source).exists():
        project = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        project["video_path"] = str(Path(source).resolve())
        (folder / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return RedirectResponse(f"/conferir/{quote(name)}", status_code=303)


@app.get("/conferir/{name}/miniatura/{index}.jpg")
def thumbnail(name: str, index: int):
    folder = folder_of(name)
    item = load_review(folder)["items"][index]
    path = folder / "miniaturas" / f"{index}-{item['start']:.0f}-{item['end']:.0f}.jpg"
    if not path.exists():
        from ..pipeline import video_path
        path.parent.mkdir(parents=True, exist_ok=True)
        middle = item["start"] + min(3.0, (item["end"] - item["start"]) / 2)
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-ss", f"{middle:.2f}", "-i",
                        video_path(folder), "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4", str(path)],
                       check=True)
    return FileResponse(path, headers={"Cache-Control": "max-age=3600"})


def _player(request: Request, folder: Path, review: dict, index: int) -> HTMLResponse:
    from ..pipeline import video_path
    item = review["items"][index]
    clip = folder / "previas" / f"{item['id']}-{item['start']:.0f}-{item['end']:.0f}.mp4"
    preview = make_preview(video_path(folder), item["start"], item["end"], clip)
    context = {**_review_context(folder, review, index), "item": item, "index": index,
               "preview_url": file_url(folder, preview)}
    return templates.TemplateResponse(request, "_player.html", context)


@app.get("/conferir/{name}/trecho/{index}", response_class=HTMLResponse)
def select_clip(request: Request, name: str, index: int):
    folder = folder_of(name)
    return _player(request, folder, load_review(folder), index)


@app.post("/conferir/{name}/trecho/{index}/alternar", response_class=HTMLResponse)
def toggle_clip(request: Request, name: str, index: int):
    folder = folder_of(name)
    review = load_review(folder)
    kept = set(review["kept"])
    kept.symmetric_difference_update({index})
    review["kept"] = sorted(kept)
    save_review(folder, review)
    context = {**_review_context(folder, review, index), "item": review["items"][index], "index": index}
    return templates.TemplateResponse(request, "_clip.html", {**context, "oob": True})


@app.post("/conferir/{name}/trecho/{index}/ajustar", response_class=HTMLResponse)
def adjust_clip(request: Request, name: str, index: int, campo: str = Form(""), delta: float = Form(0),
                transicao: str = Form("")):
    folder = folder_of(name)
    review = load_review(folder)
    item = review["items"][index]
    if campo in ("start", "end"):
        changed = {**item, campo: max(0.0, item[campo] + delta)}
        if changed["end"] - changed["start"] >= 3:
            review["items"][index] = changed
    if transicao in TRANSITIONS:
        review["items"][index]["transition"] = transicao
    save_review(folder, review)
    return _player(request, folder, review, index)


@app.post("/gerar/{name}")
def generate(name: str):
    folder = folder_of(name)

    def work(job: jobs.Job) -> str:
        from ..pipeline import export_plan, make_publication_covers, write_publication
        review = load_review(folder)
        items, aspect = kept_items(review), review.get("aspect", "16:9")
        if not items:
            raise RuntimeError("Todos os trechos estão desligados. Ligue pelo menos um.")
        notes: list[str] = []
        step = lambda done, total, text: job.report(0.85 * done / max(1, total),
                                                    f"{text}: trecho {min(done + 1, total)} de {total}")
        path = export_plan(folder, items, aspect, review.get("shorts") if aspect == "9:16" else None, notes, step)
        write_publication(folder, review.get("publication") or {}, items, aspect)
        job.report(0.9, "A IA está escolhendo as capas…")
        make_publication_covers(folder, review.get("publication") or {}, items, aspect, notes)
        job.report(0.98, "Finalizando…")
        (folder / "resultado.json").write_text(json.dumps({"video": str(path), "notes": notes}, ensure_ascii=False),
                                               encoding="utf-8")
        return f"/pronto/{quote(folder.name)}"

    job_id = jobs.start("Gerando o seu vídeo", jobs.EXPORT_STEPS, work)
    return RedirectResponse(f"/progresso/{job_id}", status_code=303)


# ---------------- 3. Pronto ----------------

def _covers_context(folder: Path, selected: int | None = None) -> dict:
    data = load_covers(folder / "capas")
    covers = [{**c, "url": file_url(folder, c["path"])} for c in data["covers"] if Path(c["path"]).exists()]
    if selected is None:
        selected = int(data.get("selected", 1))
    selected = max(1, min(selected, len(covers) or 1))
    try:
        scenes = json.loads((folder / "capas" / "cenas" / "cenas.json").read_text(encoding="utf-8"))
        scenes = [{**s, "url": file_url(folder, s["path"])} for s in scenes if Path(s["path"]).exists()]
    except (OSError, ValueError):
        scenes = []
    return {"name": folder.name, "covers": covers, "selected": selected, "aspect": data.get("aspect", "16:9"),
            "scenes": scenes, "fonts": list(FONTS)}


@app.get("/pronto/{name}", response_class=HTMLResponse)
def done_page(request: Request, name: str):
    folder = folder_of(name)
    review = load_review(folder)
    result = json.loads((folder / "resultado.json").read_text(encoding="utf-8"))
    items = kept_items(review)
    context = {**_covers_context(folder), "aspect": review.get("aspect", "16:9")}
    return page(request, "pronto.html", step=3, video_url=file_url(folder, result["video"]),
                video_name=Path(result["video"]).name, notes=result.get("notes", []),
                pub=publication_parts(review.get("publication") or {}, items, review.get("aspect", "16:9")), **context)


@app.post("/pronto/{name}/capa", response_class=HTMLResponse)
def cover_action(request: Request, name: str, n: int = Form(1), texto: str | None = Form(None),
                 fonte: str | None = Form(None), cor: str | None = Form(None), lado: str | None = Form(None),
                 cena: float | None = Form(None)):
    folder = folder_of(name)
    covers_dir = folder / "capas"
    data = load_covers(covers_dir)
    data["selected"] = n
    (covers_dir / "capas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if cena is not None:
        from ..pipeline import video_path
        use_scene(covers_dir, n, video_path(folder), cena)
    if any(v is not None for v in (texto, fonte, cor, lado)):
        restyle_cover(covers_dir, n, text=texto, font=fonte, color=cor, side=lado)
    return templates.TemplateResponse(request, "_capas.html", _covers_context(folder, n))


# ---------------- Arquivos da análise ----------------

@app.get("/arquivo/{name}/{path:path}")
def project_file(name: str, path: str):
    folder = folder_of(name)
    target = (folder / path).resolve()
    if folder not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


def run(host: str = "127.0.0.1", port: int = 7860, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    print(f"Pajau aberto em http://{host}:{port}  (Ctrl+C para fechar)")
    uvicorn.run(app, host=host, port=port, log_level="warning")
