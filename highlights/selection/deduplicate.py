from __future__ import annotations

from pathlib import Path

from ..models import Cut


def dhash(path: str | Path, size: int = 16) -> int:
    """Small perceptual hash; PIL is used so no ML model is required."""
    try:
        from PIL import Image
    except ImportError:
        return 0

    image = Image.open(path).convert("L").resize((size + 1, size), Image.Resampling.BILINEAR)
    pixels = list(image.getdata())
    width = size + 1
    value = 0
    for y in range(size):
        row = y * width
        for x in range(size):
            value <<= 1
            if pixels[row + x] > pixels[row + x + 1]:
                value |= 1
    return value


def deduplicate_cuts(cuts: list[Cut], preview_dir: str | Path, max_distance: int = 11) -> list[Cut]:
    """Remove visually repeated candidates without merging a likely final victory."""
    preview_dir = Path(preview_dir)
    kept: list[tuple[Cut, int]] = []

    for index, cut in enumerate(cuts, 1):
        hashes = []
        for position in ("start", "middle", "end"):
            path = preview_dir / f"clip_{index:02d}_{position}.jpg"
            if path.exists():
                hashes.append(dhash(path))

        if 0 in hashes:
            kept.append((cut, 0))
            continue

        duplicate = False
        for previous, previous_hash in kept:
            if previous_hash == 0:
                continue
            distance = bin(hashes[0] ^ previous_hash).count("1")
            if distance <= max_distance:
                duplicate = cut.score > previous.score
                if duplicate:
                    kept.remove((previous, previous_hash))
                    kept.append((cut, hashes[0]))
                break
        if not duplicate:
            kept.append((cut, hashes[0]))

    kept.sort(key=lambda item: item[0].start)
    return [cut for cut, _ in kept]
