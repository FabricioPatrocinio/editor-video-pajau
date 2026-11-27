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
