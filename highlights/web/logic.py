"""Regras da interface, sem nada de HTML: caminhos, durações, estado da revisão e textos para publicar."""
from __future__ import annotations

import json
import re
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

def project_dir(name: str) -> Path:
    """Pasta de uma análise, sem deixar sair de output/."""
    folder = (OUTPUT_DIR / name).resolve()
    if folder.parent != OUTPUT_DIR.resolve() or not (folder / "ia-plan.json").exists():
        raise FileNotFoundError(name)
    return folder


def previous_analyses(limit: int = 8) -> list[dict]:
    plans = sorted(OUTPUT_DIR.glob("*/ia-plan.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    result = []
    for plan in plans:
        try:
            title = Path(video_path(plan.parent)).stem
        except (OSError, ValueError, KeyError):
            title = plan.parent.name
        result.append({"name": plan.parent.name, "title": title[:70],
                       "when": datetime.fromtimestamp(plan.stat().st_mtime).strftime("%d/%m %H:%M")})
    return result


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
