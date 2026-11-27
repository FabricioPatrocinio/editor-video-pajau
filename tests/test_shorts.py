from highlights.ai.plan import _focus
from highlights.export.shorts import _ass_time, _chunks, camera_rect, vertical_graph


def test_recorte_segue_o_foco_sem_sair_da_imagem():
    assert "crop=1012:1800:0:0" in vertical_graph(3200, 1800, {"layout": "cheio"}, 0.0)
    assert "crop=1012:1800:2188:0" in vertical_graph(3200, 1800, {"layout": "cheio"}, 1.0)
    assert "crop=404:720:438:0" in vertical_graph(1280, 720, {"layout": "cheio"}, 0.5)


def test_camera_no_canto_certo():
    assert camera_rect(1920, 1080, "inferior direito", 25) == (1440, 810, 480, 270)
    assert camera_rect(1920, 1080, "superior esquerdo", 25) == (0, 0, 480, 270)
    assert "vstack" in vertical_graph(1920, 1080, {"layout": "camera", "corner": "superior esquerdo"}, 0.5)


def test_legenda_quebra_na_pontuacao_e_em_blocos_curtos():
    words = [(0.0, 0.2, "Nós,"), (0.2, 0.4, "né?"), (0.4, 0.6, "Só"), (0.6, 0.8, "falamos"), (0.8, 1.0, "a"),
             (1.0, 1.2, "língua")]
    assert [[w[2] for w in c] for c in _chunks(words)] == [["Nós,"], ["né?"], ["Só", "falamos", "a"], ["língua"]]
    assert _ass_time(3725.5) == "1:02:05.50"


def test_foco_da_ia_sempre_entre_0_e_1():
    assert _focus(1.7) == 1.0 and _focus(-2) == 0.0 and _focus(None) == 0.5 and _focus("0.3") == 0.3
