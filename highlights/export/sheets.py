"""Folhas de contato: várias miniaturas numa imagem só, com o id de cada trecho escrito.

Uma folha com 5 trechos x 3 fotos gasta bem menos tokens do que 15 imagens soltas,
e o Claude Code precisa abrir só 1 arquivo em vez de 15.
"""
from __future__ import annotations

from pathlib import Path

FRAME_W, FRAME_H, LABEL_H = 360, 203, 24
PER_SHEET = 5


def build_sheets(candidates: list, output_dir: Path) -> list[tuple[str, Path]]:
    """Retorna [(descrição, caminho da folha)]. `candidates` precisa de .id, .start e .previews."""
    from PIL import Image, ImageDraw

    output_dir.mkdir(parents=True, exist_ok=True)
    usable = [c for c in candidates if any(Path(p).exists() for p in c.previews[:3])]
    sheets = []
    for offset in range(0, len(usable), PER_SHEET):
        group = usable[offset:offset + PER_SHEET]
        sheet = Image.new("RGB", (FRAME_W * 3, (FRAME_H + LABEL_H) * len(group)), "black")
        draw = ImageDraw.Draw(sheet)
        for row, candidate in enumerate(group):
            top = row * (FRAME_H + LABEL_H)
            minutes, seconds = divmod(int(candidate.start), 60)
            hours, minutes = divmod(minutes, 60)
            label = f"{candidate.id}  ({hours:02d}:{minutes:02d}:{seconds:02d})  inicio | meio | fim"
            draw.text((6, top + 5), label, fill="yellow")
            for column, preview in enumerate(candidate.previews[:3]):
                if Path(preview).exists():
                    frame = Image.open(preview).convert("RGB").resize((FRAME_W, FRAME_H))
                    sheet.paste(frame, (column * FRAME_W, top + LABEL_H))
        ids = ", ".join(c.id for c in group)
        path = output_dir / f"folha-{offset // PER_SHEET + 1:02d}.jpg"
        sheet.save(path, quality=80)
        sheets.append((f"Folha {offset // PER_SHEET + 1}: {ids} (cada linha = início, meio e fim do trecho)", path))
    return sheets


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def build_timeline_sheets(
    frames: list[tuple[float, Path]],
    output_dir: Path,
    title: str = "",
    cols: int = 6,
    rows: int = 8,
    thumb: tuple[int, int] = (256, 144),
) -> list[tuple[str, Path]]:
    """Grade de fotos com o segundo de cada uma (ex.: "t=5020 1:23:40"), em ordem de tempo."""
    from PIL import Image, ImageDraw

    output_dir.mkdir(parents=True, exist_ok=True)
    label_h = 16
    per_sheet = cols * rows
    sheets = []
    for offset in range(0, len(frames), per_sheet):
        group = frames[offset:offset + per_sheet]
        lines = (len(group) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * thumb[0], lines * (thumb[1] + label_h)), "black")
        draw = ImageDraw.Draw(sheet)
        for index, (second, path) in enumerate(group):
            x = (index % cols) * thumb[0]
            y = (index // cols) * (thumb[1] + label_h)
            draw.text((x + 4, y + 2), f"t={second:.0f}  {_clock(second)}", fill="yellow")
            if Path(path).exists():
                sheet.paste(Image.open(path).convert("RGB").resize(thumb), (x, y + label_h))
        number = offset // per_sheet + 1
        path = output_dir / f"{title or 'mapa'}-{number:02d}.jpg"
        sheet.save(path, quality=80)
        sheets.append((
            f"{title or 'Mapa'} folha {number}: de t={group[0][0]:.0f} ({_clock(group[0][0])}) "
            f"a t={group[-1][0]:.0f} ({_clock(group[-1][0])}), da esquerda para a direita, de cima para baixo",
            path,
        ))
    return sheets
