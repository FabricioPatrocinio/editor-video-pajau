from highlights.web.jobs import ANALYSIS_STEPS, Job
from highlights.web.logic import briefing, friendly_reason, target_seconds


def test_duracao_em_segundos_no_short_e_minutos_no_horizontal():
    assert target_seconds(45, "9:16") == 45 and target_seconds(10, "16:9") == 600
    assert target_seconds(None, "9:16") == 45


def test_motivo_mostra_horario_da_live_no_lugar_de_t():
    assert friendly_reason("contra-ataque em t=544 e golpe em t=3725") == "contra-ataque em 9:04 e golpe em 1:02:05"


def test_pedido_do_short_avisa_a_ia_desde_o_mapa():
    assert "Short vertical de até 45 s" in briefing("Onimusha", "só bosses", "9:16", 45)
    assert "Short" not in briefing("Onimusha", "só bosses", "16:9", 10)


def test_etapas_do_progresso():
    job = Job("Analisando", ANALYSIS_STEPS)
    job.report(0.4, "Zoom no trecho 1")
    states = [state for _, state in job.step_states()]
    assert states == ["feito", "feito", "agora", "falta", "falta"]
