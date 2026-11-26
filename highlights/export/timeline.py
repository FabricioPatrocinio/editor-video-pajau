from __future__ import annotations

from pathlib import Path

from ..models import Cut


def write_edl(cuts: list[Cut], source_name: str, path: str | Path) -> Path:
    path = Path(path)
    lines = ["TITLE: Highlights", "FCM: NON-DROP FRAME", ""]
    for index, cut in enumerate(cuts, 1):
        lines.append(f"{index:03d}  AX       V     C        {fmt_tc(cut.start)} {fmt_tc(cut.end)} {fmt_tc(cut.start)} {fmt_tc(cut.end)}")
        lines.append(f"* FROM CLIP NAME: {source_name}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def fmt_tc(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    frames = int(round((seconds - total) * 30))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def write_mlt_xml(source: str, cuts: list[Cut], path: str | Path) -> Path:
    path = Path(path)
    entries = []
    timeline = 0.0
    for index, cut in enumerate(cuts):
        entries.append(
            f'<entry producer="producer0" in="{int(cut.start * 25)}" out="{int(cut.end * 25)}" />'
        )
        timeline += cut.duration

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7">
  <profile description="HD 1080p 25 fps" width="1920" height="1080" progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" frame_rate_num="25" frame_rate_den="1" colorspace="709" />
  <producer id="producer0" in="0" out="{int(timeline * 25)}">
    <property name="resource">{source}</property>
  </producer>
  <playlist id="playlist0">
    {"".join(entries)}
  </playlist>
  <tractor id="tractor0" in="0" out="{int(timeline * 25)}">
    <track producer="playlist0" />
  </tractor>
</mlt>
'''
    path.write_text(xml, encoding="utf-8")
    return path
