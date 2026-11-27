"""Regras da interface, sem nada de HTML: caminhos, durações, estado da revisão e textos para publicar."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from ..ai.config import check_ai_ready, load_ai_settings
from ..ai.plan import PlanItem
from ..ai.style import compose_briefing
from ..pipeline import publication_text, video_path

OUTPUT_DIR = Path("output")
LIVES_DIR = Path("data") / "lives"

# Durações sugeridas por formato (fontes no README: "Quanto tempo deve ter o vídeo").
DURATION = {
    "16:9": {"unit": "min", "value": 10, "min": 1, "max": 60,
             "hint": "Sugestão: 8 a 12 min. A partir de 8 min o YouTube libera anúncios no meio do vídeo."},
    "9:16": {"unit": "s", "value": 45, "min": 5, "max": 180,
             "hint": "Sugestão: 30 a 60 s. Shorts curtos são vistos até o fim com mais frequência."},
}
TRANSITION_NAMES = {"corte": "Corte seco", "fade": "Dissolver", "fade_preto": "Escurecer", "deslizar": "Deslizar"}


def time_text(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def windows_para_wsl(caminho: str) -> str:
    """No WSL, aceita o caminho do Windows colado (C:\\Users\\...) e troca por /mnt/c/Users/..."""
    if len(caminho) > 2 and caminho[1] == ":" and caminho[2] in "\\/" and Path("/mnt/c").exists():
        return f"/mnt/{caminho[0].lower()}/" + caminho[3:].replace("\\", "/")
    return caminho


def clean_path(text: str) -> str:
    return windows_para_wsl((text or "").strip().strip("'\""))


def safe_upload_name(name: str) -> str:
    """Nome do arquivo enviado, sem pastas nem caracteres que atrapalhem."""
    name = Path(name or "live.mp4").name
    name = re.sub(r"[^\w.\- ()À-ÿ]", "_", name).strip() or "live.mp4"
    return name if Path(name).suffix.lower() in {".mp4", ".mkv", ".mov", ".webm"} else name + ".mp4"


def target_seconds(duration, aspect: str) -> float:
    """A duração vem em segundos no Short e em minutos no vídeo horizontal."""
    value = float(duration or DURATION.get(aspect, DURATION["16:9"])["value"])
    return value if aspect == "9:16" else value * 60


def briefing(game: str, request: str, aspect: str, duration) -> str:
    """Pedido para a IA. No Short ela já sabe, desde o mapa da live, que é um vídeo vertical curto."""
    text = compose_briefing(game or "", "", [], "", request or "")
    if aspect == "9:16":
        text += (f" Formato: Short vertical de até {target_seconds(duration, aspect):.0f} s. Prefira um momento forte"
                 " que se entenda sozinho e comece direto na ação.")
    return text


def friendly_reason(text: str) -> str:
    """Troca os "t=544" que a IA escreve pelo horário da live (9:04)."""
    return re.sub(r"\bt=(\d+(?:\.\d+)?)", lambda m: time_text(float(m.group(1))), text or "")


def parse_intervals(text: str) -> list[list[float]]:
    def seconds(part: str) -> float:
        value = 0.0
        for piece in part.strip().split(":"):
            value = value * 60 + float(piece)
        return value

    intervals = []
    for item in (text or "").split(","):
        try:
            start, end = item.strip().split("-", 1)
            intervals.append([seconds(start), seconds(end)])
        except ValueError:
            pass
    return intervals


def ai_label() -> tuple[str, str]:
    """Rótulo da IA para o topo da tela e um aviso, se ela não estiver pronta."""
    settings = load_ai_settings()
    names = {"claude-code": "Claude · assinatura", "claude": "Claude · API", "openai": "OpenAI · API"}
    return names.get(settings.provider, settings.provider), check_ai_ready(settings) or ""


# ---------------- Análises salvas ----------------

# Cada live tem uma pasta (fotos, áudio e o índice ficam lá) e cada vídeo feito dela é um "corte":
# output/<live>/cortes/01, 02... Na tela, o corte se chama "<live>--01". Análises antigas ficam na raiz da live.

def web_name(folder: Path) -> str:
    return f"{folder.parent.parent.name}--{folder.name}" if folder.parent.name == "cortes" else folder.name


def live_dir(name: str) -> Path:
    folder = (OUTPUT_DIR / name).resolve()
    if folder.parent != OUTPUT_DIR.resolve() or not (folder / "project.json").exists():
        raise FileNotFoundError(name)
    return folder


def project_dir(name: str) -> Path:
    """Pasta de uma análise (corte), sem deixar sair de output/."""
    live, _, cut = name.partition("--")
    folder = live_dir(live)
    if cut:
        folder = (folder / "cortes" / cut).resolve()
        if folder.parent.parent != live_dir(live) or not cut.isdigit():
            raise FileNotFoundError(name)
    if not (folder / "ia-plan.json").exists():
        raise FileNotFoundError(name)
    return folder


def new_cut(live: Path, info: dict) -> Path:
    """Pasta nova para mais um vídeo da mesma live."""
    cuts = live / "cortes"
    cuts.mkdir(exist_ok=True)
    number = 1 + max([int(p.name) for p in cuts.iterdir() if p.name.isdigit()] or [0])
    folder = cuts / f"{number:02d}"
    folder.mkdir()
    for name in ("project.json", "mudo.json"):
        if (live / name).exists():
            shutil.copy(live / name, folder / name)
    (folder / "pedido.json").write_text(json.dumps({**info, "quando": datetime.now().isoformat(timespec="minutes")},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


def _readable(brief: str) -> str:
    """Análises antigas guardam o pedido montado ("Jogo/conteúdo: ... Ordem: ..."); mostra só o que a pessoa escreveu."""
    text = re.sub(r"(Jogo/conteúdo|Tipo de vídeo|Priorizar|Ordem):[^.]*\.\s*", "", brief or "")
    text = re.sub(r"Formato: Short vertical.*$", "", text).strip()
    return text or (re.search(r"Tipo de vídeo: ([^.]*)", brief or "") or [None, ""])[1]


def _cut_info(folder: Path) -> dict:
    when = datetime.fromtimestamp((folder / "ia-plan.json").stat().st_mtime)
    try:
        asked = json.loads((folder / "pedido.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        asked = {}
    label = asked.get("pedido") or _readable(json.loads((folder / "ia-plan.json").read_text(encoding="utf-8"))
                                             .get("briefing", ""))
    aspect = asked.get("aspect") or load_review(folder).get("aspect", "16:9")
    return {"name": web_name(folder), "label": (label.strip() or "Melhores momentos")[:70],
            "icon": "📱" if aspect == "9:16" else "🖥️", "when": when.strftime("%d/%m %H:%M"), "sort": when}


def previous_lives(limit: int = 6) -> list[dict]:
    """Lives já analisadas, cada uma com os vídeos feitos dela (o mais novo primeiro)."""
    lives = []
    for live in OUTPUT_DIR.glob("*/project.json"):
        live = live.parent
        cuts = [live] if (live / "ia-plan.json").exists() else []
        cuts += [c.parent for c in (live / "cortes").glob("*/ia-plan.json")]
        if not cuts:
            continue
        try:
            video = Path(video_path(live))
        except (OSError, ValueError, KeyError):
            continue
        info = sorted((_cut_info(c) for c in cuts), key=lambda c: c["sort"], reverse=True)
        lives.append({"name": live.name, "title": video.stem[:80], "video_ok": video.exists(),
                      "has_map": (live / "mapa.json").exists(), "cuts": info[:5], "sort": info[0]["sort"]})
    return sorted(lives, key=lambda l: l["sort"], reverse=True)[:limit]


def _plan_item(raw: dict) -> dict:
    names = {f.name for f in fields(PlanItem)}
    return asdict(PlanItem(**{k: v for k, v in raw.items() if k in names}))


def load_review(folder: Path) -> dict:
    """Estado da conferência: trechos (com ajustes), quais estão ligados e o formato escolhido."""
    path = folder / "revisao.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    plan = json.loads((folder / "ia-plan.json").read_text(encoding="utf-8"))
    items = [_plan_item(raw) for raw in plan.get("approved", [])]
    review = {"items": items, "kept": list(range(len(items))), "aspect": "16:9", "duration": 10, "shorts": {},
              "summary": plan.get("summary", ""), "usage": plan.get("usage", ""),
              "publication": plan.get("publication") or {}}
    save_review(folder, review)
    return review


def save_review(folder: Path, review: dict) -> None:
    (folder / "revisao.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")


def kept_items(review: dict) -> list[dict]:
    return [review["items"][i] for i in sorted(review["kept"]) if i < len(review["items"])]


def total_seconds(items: list[dict]) -> float:
    return sum(item["end"] - item["start"] for item in items)


def publication_parts(publication: dict, items: list[dict], aspect: str) -> dict:
    """Títulos separados e a descrição pronta (com capítulos e hashtags), para copiar com um clique."""
    text = publication_text(publication, items, aspect)
    description = text.split("## Descrição", 1)[1] if "## Descrição" in text else ""
    description = description.split("## Ideias de capa", 1)[0].strip()
    return {"titles": [t for t in (publication or {}).get("titles", []) if t], "description": description}
