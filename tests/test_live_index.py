import json
from pathlib import Path

from highlights import pipeline


def _setup(tmp_path, monkeypatch, index):
    monkeypatch.chdir(tmp_path)
    video = tmp_path / "live.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr("highlights.download.youtube.probe_video", lambda path: {"duration": 600.0})
    monkeypatch.setattr(pipeline, "_fingerprint", lambda path: "abc123abc123")
    monkeypatch.setattr(pipeline, "transcription_enabled", lambda: False)
    monkeypatch.setattr("highlights.analysis.frames.sample_frames", lambda *a, **k: [])
    output = Path("output") / "live-abc123abc1"
    output.mkdir(parents=True)
    (output / "mudo.json").write_text("[]")
    if index:
        (output / "mapa.json").write_text(json.dumps(index))
    return video, output


def test_live_mapeada_usa_o_indice_sem_olhar_fotos(tmp_path, monkeypatch):
    index = {"resumo": "Dois bosses.", "segmentos": [{"start": 100, "end": 200, "descricao": "boss 1", "usar": True},
                                                       {"start": 300, "end": 400, "descricao": "boss 2", "usar": False}]}
    video, output = _setup(tmp_path, monkeypatch, index)
    calls = []
    monkeypatch.setattr("highlights.ai.plan.build_map_from_index", lambda idx, *a: (calls.append("indice") or (
        {"resumo": "ok", "segmentos": [{"start": 300, "end": 400, "descricao": "boss 2", "usar": True}]}, "uso")))
    monkeypatch.setattr("highlights.ai.plan.build_live_map", lambda *a: calls.append("fotos"))
    _, candidates, _ = pipeline.find_segments_with_map(str(video), "o outro boss", "", 60)
    assert calls == ["indice"] and candidates[0].start == 280
    assert json.loads((output / "mapa.json").read_text()) == index  # o índice completo não é trocado


def test_indice_sem_o_pedido_olha_a_live_de_novo(tmp_path, monkeypatch):
    video, output = _setup(tmp_path, monkeypatch, {"resumo": "", "segmentos": [{"start": 1, "end": 2, "usar": False}]})
    calls = []
    monkeypatch.setattr("highlights.ai.plan.build_map_from_index",
                        lambda *a: (calls.append("indice") or ({"resumo": "", "segmentos": []}, "uso")))
    monkeypatch.setattr("highlights.ai.plan.build_live_map", lambda *a: (calls.append("fotos") or (
        {"resumo": "novo", "segmentos": [{"start": 50, "end": 90, "descricao": "papo", "usar": True}]}, "uso")))
    _, candidates, _ = pipeline.find_segments_with_map(str(video), "papo com o chat", "", 60)
    assert calls == ["indice", "fotos"] and len(candidates) == 1
