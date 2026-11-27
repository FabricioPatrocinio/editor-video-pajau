from highlights.ui.gradio_app import _nav

PLANO = [{"id": "a"}, {"id": "b"}, {"id": "c"}]


def test_sem_plano_so_o_pedido_fica_liberado():
    pedido, revisar, gerar, tela_pedido, tela_revisar = _nav(1)
    assert pedido.variant == "primary" and not revisar.interactive and not gerar.interactive
    assert tela_pedido.visible and not tela_revisar.visible


def test_revisar_mostra_progresso_e_troca_de_tela():
    pedido, revisar, gerar, tela_pedido, tela_revisar = _nav(2, PLANO, 1)
    assert revisar.value == "② Revisar (1/3)" and revisar.variant == "primary"
    assert gerar.interactive and not tela_pedido.visible and tela_revisar.visible


def test_duracao_em_segundos_no_short_e_minutos_no_horizontal():
    from highlights.ui.gradio_app import target_seconds
    assert target_seconds(45, "9:16") == 45 and target_seconds(10, "16:9") == 600
    assert target_seconds(None, "9:16") == 45


def test_motivo_mostra_horario_da_live_no_lugar_de_t():
    from highlights.ui.gradio_app import friendly_reason
    assert friendly_reason("contra-ataque em t=544 e golpe em t=3725") == "contra-ataque em 09:04 e golpe em 01:02:05"


def test_pedido_do_short_avisa_a_ia_desde_o_mapa():
    from highlights.ui.gradio_app import _briefing
    assert "Short vertical de até 45 s" in _briefing("Onimusha", "Melhores momentos", [], "", "", "9:16", 45)
    assert "Short" not in _briefing("Onimusha", "Melhores momentos", [], "", "", "16:9", 10)


def test_formato_fica_salvo_sem_perder_o_resto(tmp_path, monkeypatch):
    from highlights.export import shorts
    monkeypatch.setattr(shorts, "SETTINGS_FILE", tmp_path / "shorts.json")
    shorts.save_settings({**shorts.load_settings(), "zoom": 60})
    shorts.save_settings({**shorts.load_settings(), "aspect": "9:16"})
    assert shorts.load_settings()["aspect"] == "9:16" and shorts.load_settings()["zoom"] == 60
