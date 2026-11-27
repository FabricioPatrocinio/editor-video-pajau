import json
import subprocess

from PIL import Image

from highlights.export.covers import _scene_time, make_covers, retext_cover
from highlights.pipeline import publication_text

ITEMS = [{"start": 1.0, "end": 3.0, "chapter": "Boss 1", "reason": "vitória"},
         {"start": 4.0, "end": 5.0, "chapter": "Boss 2", "reason": "reação"}]


def test_segundo_fora_do_video_cai_no_meio_do_primeiro_trecho():
    assert _scene_time(2.5, ITEMS) == 2.5
    assert _scene_time(99, ITEMS) == 2.0
    assert _scene_time("lixo", ITEMS) == 2.0


def test_gera_capas_e_troca_o_texto(tmp_path):
    video = tmp_path / "live.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10",
                    "-t", "6", str(video)], check=True)
    ideas = [{"time": 2, "text": "Ele não acreditou", "why": "reação"}]
    covers = make_covers(video, ideas, ITEMS, tmp_path / "capas", "16:9")
    assert len(covers) == 1 and Image.open(covers[0]["path"]).size == (1280, 720)

    # Sem ideias da IA: usa os trechos com o nome do capítulo.
    fallback = make_covers(video, [], ITEMS, tmp_path / "capas2", "9:16")
    assert [c["text"] for c in fallback] == ["Boss 1", "Boss 2"]
    assert Image.open(fallback[0]["path"]).size == (1080, 1920)

    retext_cover(tmp_path / "capas", 1, "Novo texto")
    assert json.loads((tmp_path / "capas" / "capas.json").read_text())["covers"][0]["text"] == "Novo texto"


def test_ideias_de_capa_vao_no_fim_do_texto():
    pub = {"titles": ["A"], "description": "D", "hashtags": ["#x"],
           "covers": [{"time": 1, "text": "UAU", "why": "porque sim"}]}
    text = publication_text(pub, ITEMS, "9:16")
    assert text.endswith("1. **UAU** — porque sim") and text.index("#x") < text.index("Ideias de capa")
