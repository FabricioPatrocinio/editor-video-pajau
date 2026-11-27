import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from highlights.web import app as web
from highlights.web import logic


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """Uma análise falsa, com um vídeo de teste de 30 s."""
    monkeypatch.setattr(logic, "OUTPUT_DIR", tmp_path / "output")
    folder = tmp_path / "output" / "minha-live"
    folder.mkdir(parents=True)
    video = tmp_path / "live.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10", "-t", "30",
                    str(video)], check=True)
    (folder / "project.json").write_text(json.dumps({"video_path": str(video)}))
    items = [dict(id="a", start=2.0, end=8.0, accepted=True, reason="golpe em t=5", confidence=0.9, kind="luta",
                  transition="corte", chapter="Boss 1", focus=0.5),
             dict(id="a", start=12.0, end=18.0, accepted=True, reason="reação", confidence=0.9, kind="reacao",
                  transition="fade", chapter="Vitória", focus=0.5)]
    (folder / "ia-plan.json").write_text(json.dumps({"summary": "Teste.", "approved": items, "publication": {
        "titles": ["Título A"], "description": "Desc.", "hashtags": ["#teste"]}}))
    return folder


def test_pagina_inicial_abre():
    page = TestClient(web.app).get("/")
    assert page.status_code == 200 and "Analisar a live" in page.text


def test_envio_da_live_vai_para_o_disco(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "LIVES_DIR", tmp_path / "lives")
    answer = TestClient(web.app).put("/enviar?nome=../x.mp4", content=b"video").json()
    assert answer["nome"] == "x.mp4" and (tmp_path / "lives" / "x.mp4").read_bytes() == b"video"
    # Mandar a mesma live de novo (nome com outro símbolo) reaproveita o arquivo que já existe.
    client = TestClient(web.app)
    assert client.get("/enviar/existe", params={"nome": "x–.mp4", "tamanho": 5}).json()["nome"] == "x.mp4"
    assert client.get("/enviar/existe", params={"nome": "x.mp4", "tamanho": 6}).json() == {}


def test_conferir_liga_desliga_e_ajusta(project):
    client = TestClient(web.app)
    page = client.get("/conferir/minha-live")
    assert page.status_code == 200 and "Gerar vídeo · 2 trechos" in page.text
    # Os dois pedaços têm o mesmo id: desligar um não pode desligar o outro.
    toggled = client.post("/conferir/minha-live/trecho/0/alternar")
    assert "Gerar vídeo · 1 trecho " in toggled.text
    assert json.loads((project / "revisao.json").read_text())["kept"] == [1]
    player = client.post("/conferir/minha-live/trecho/1/ajustar", data={"campo": "start", "delta": "-5"})
    assert player.status_code == 200 and "7 → " in player.text
    assert client.get("/conferir/minha-live/trecho/0").status_code == 200
    assert client.get("/conferir/minha-live/miniatura/0.jpg").headers["content-type"] == "image/jpeg"


def test_pronto_mostra_video_capas_e_troca_estilo(project):
    from highlights.export.covers import make_covers
    from highlights.pipeline import video_path
    items = logic.load_review(project)["items"]
    make_covers(video_path(project), [{"time": 5, "text": "Ninguém esperava", "why": "luta"}], items,
                project / "capas", "16:9")
    final = project / "video-final.mp4"
    final.write_bytes(b"x")
    (project / "resultado.json").write_text(json.dumps({"video": str(final), "notes": []}))
    client = TestClient(web.app)
    page = client.get("/pronto/minha-live")
    assert page.status_code == 200 and "Baixar vídeo" in page.text and "Título A" in page.text
    changed = client.post("/pronto/minha-live/capa", data={"n": "1", "cor": "ciano", "fonte": "luckiest"})
    cover = json.loads((project / "capas" / "capas.json").read_text())["covers"][0]
    assert changed.status_code == 200 and cover["color"] == "ciano" and cover["font"] == "luckiest"


def test_arquivo_fora_da_analise_e_bloqueado(project):
    assert TestClient(web.app).get("/arquivo/minha-live/../../live.mp4").status_code == 404
    assert TestClient(web.app).get("/conferir/..%2F..").status_code == 404


def test_fluxo_completo_pedido_conferir_gerar_pronto(tmp_path, monkeypatch):
    """Do formulário ao vídeo pronto, com uma IA de mentira (não gasta tokens)."""
    import time
    from types import SimpleNamespace
    from highlights import pipeline
    from highlights.web import jobs

    monkeypatch.setattr(logic, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setenv("PAJAU_CAPA_IA", "false")
    monkeypatch.setenv("PAJAU_MODO", "picos")
    monkeypatch.setattr("highlights.ai.config.check_ai_ready", lambda *a: "")
    monkeypatch.setattr(web, "save_settings", lambda s: s)
    video = tmp_path / "live.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10", "-f", "lavfi",
                    "-i", "sine", "-t", "20", str(video)], check=True)
    folder = tmp_path / "output" / "live-teste"

    def fake_candidates(source, target, skip, progress):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "project.json").write_text(json.dumps({"video_path": str(video)}))
        progress(0.5, "lendo")
        return folder, []

    def fake_plan(output, candidates, brief, avoid, target, aspect):
        items = [dict(id="x", start=1.0, end=5.0, accepted=True, reason="ok", confidence=1, kind="luta",
                      transition="corte", chapter="Luta", focus=0.5)]
        (output / "ia-plan.json").write_text(json.dumps({"summary": "Resumo.", "approved": items,
                                                         "publication": {"titles": ["T"], "description": "D"}}))
        return SimpleNamespace(items=items, summary="Resumo.", usage="")

    monkeypatch.setattr(pipeline, "find_candidates", fake_candidates)
    monkeypatch.setattr(pipeline, "plan_with_ai", fake_plan)
    client = TestClient(web.app)

    def finish(response):
        assert response.status_code == 303
        job = jobs.JOBS[response.headers["location"].rsplit("/", 1)[1]]
        for _ in range(300):
            if job.done or job.error:
                break
            time.sleep(0.1)
        assert not job.error, job.error
        return job.result_url

    url = finish(client.post("/analisar", data={"caminho": str(video), "formato": "16:9", "duracao": "1",
                                                "pedido": "tudo"}, follow_redirects=False))
    assert url == "/conferir/live-teste--01" and "Gerar vídeo · 1 trecho" in client.get(url).text
    url = finish(client.post("/gerar/live-teste--01", follow_redirects=False))
    page = client.get(url)
    assert url == "/pronto/live-teste--01" and "Baixar vídeo" in page.text and "capa-1.jpg" in page.text

    # Segundo vídeo da mesma live: vira o corte 02, sem apagar o 01.
    url = finish(client.post("/analisar", data={"caminho": str(video), "formato": "9:16", "duracao": "30",
                                                "pedido": "outro boss"}, follow_redirects=False))
    assert url == "/conferir/live-teste--02" and (folder / "cortes" / "01" / "resultado.json").exists()
    home = client.get("/").text
    assert "Novo vídeo desta live" in home and "outro boss" in home and "📱" in home
    assert "♻️" in client.get("/?live=live-teste").text


def test_nomes_de_corte_nao_saem_da_pasta(project):
    for name in ["minha-live--../..", "minha-live--01/../../x", "..--01", "minha-live--abc"]:
        assert TestClient(web.app).get(f"/conferir/{name}").status_code == 404
