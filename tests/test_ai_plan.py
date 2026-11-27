import json

import pytest

from highlights.ai import style, usage
from highlights.ai.config import load_ai_settings
from highlights.ai.plan import Candidate, build_review_plan
from highlights.ai.providers import ImagePart, TextPart
from highlights.ai.usage import Usage


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for name in ("PAJAU_USE_CLAUDE", "PAJAU_CLAUDE_VIA", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
                 "PAJAU_AI_DAILY_LIMIT_USD", "PAJAU_AI_MAX_CANDIDATES", "PAJAU_AI_MAX_IMAGE_CANDIDATES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(usage, "LEDGER", tmp_path / "ai-usage.json")
    monkeypatch.setattr(style, "STYLE_FILE", tmp_path / "estilo.json")


class FakeProvider:
    def __init__(self, result, cost=0.01):
        self.result = result
        self.cost = cost
        self.parts = None

    def generate_plan(self, system, parts):
        self.parts = parts
        return self.result, Usage(1000, 200, self.cost)


def _candidates():
    return [
        Candidate("evento-01", 10.0, 80.0, 0.9, []),
        Candidate("evento-02", 100.0, 170.0, 0.7, []),
        Candidate("evento-03", 300.0, 360.0, 0.5, []),
    ]


def test_flag_selects_provider(monkeypatch):
    assert load_ai_settings().provider == "claude-code"  # padrão: assinatura
    monkeypatch.setenv("PAJAU_CLAUDE_VIA", "api")
    assert load_ai_settings().provider == "claude"
    assert load_ai_settings().model == "claude-opus-5-5"
    monkeypatch.setenv("PAJAU_USE_CLAUDE", "false")
    assert load_ai_settings().provider == "openai"
    monkeypatch.setenv("PAJAU_USE_CLAUDE", "True")
    assert load_ai_settings().provider == "claude"


def test_missing_key_names_the_right_variable(monkeypatch):
    monkeypatch.setenv("PAJAU_CLAUDE_VIA", "api")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_review_plan(_candidates(), "Pegar vitória contra boss", 600.0)
    monkeypatch.setenv("PAJAU_USE_CLAUDE", "false")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_review_plan(_candidates(), "Pegar vitória contra boss", 600.0)


def test_plan_is_clamped_ordered_and_respects_duration():
    provider = FakeProvider({
        "summary": "ok",
        "approved": [
            {"id": "evento-02", "start": 90, "end": 200, "order": 1, "kind": "boss_vitoria", "reason": "a", "confidence": 2, "transition": "fade_preto"},
            {"id": "evento-01", "start": 20, "end": 60, "order": 2, "kind": "reacao", "reason": "b", "confidence": 0.8, "transition": "explosao"},
            {"id": "evento-01", "start": 20, "end": 60, "order": 3, "kind": "dup", "reason": "c", "confidence": 0.8},
            {"id": "inventado", "start": 0, "end": 10, "order": 4, "kind": "x", "reason": "d", "confidence": 0.8},
            {"id": "evento-03", "start": 300, "end": 360, "order": 5, "kind": "longo", "reason": "e", "confidence": 0.8},
        ],
        "rejected": [{"id": "evento-03", "reason": "repetido"}],
    })
    plan = build_review_plan(_candidates(), "boss", 40.0, provider=provider)  # trava = 3x o alvo

    assert [item.id for item in plan.items] == ["evento-02", "evento-01"]
    assert (plan.items[0].start, plan.items[0].end) == (100.0, 170.0)  # limitado ao candidato
    assert plan.items[0].confidence == 1.0
    assert [item.transition for item in plan.items] == ["fade_preto", "corte"]  # transição inválida vira corte
    assert plan.rejected == [{"id": "evento-03", "reason": "repetido"}]


def test_request_puts_fixed_part_first_and_briefing_last(tmp_path):
    from PIL import Image
    (tmp_path / "previews").mkdir()
    image = tmp_path / "previews" / "frame.jpg"
    Image.new("RGB", (480, 270), "red").save(image)
    candidates = [Candidate("evento-01", 10.0, 80.0, 0.9, [str(image)], transcript="consegui!")]
    provider = FakeProvider({"summary": "", "approved": [], "rejected": []})
    style.save_style_text("Canal de soulslike")

    build_review_plan(candidates, "Quero bosses", 600.0, avoid="menus", provider=provider)
    parts = provider.parts

    fixed = json.loads(parts[0].text)
    assert fixed["candidatos"][0]["transcricao"] == "consegui!"
    assert "briefing" not in fixed  # briefing fora da parte cacheada
    assert "evento-01" in parts[1].text and isinstance(parts[2], ImagePart)
    cache_marks = [i for i, part in enumerate(parts) if isinstance(part, TextPart) and part.cache]
    assert len(cache_marks) == 1
    after = " ".join(part.text for part in parts[cache_marks[0] + 1:])
    assert "Quero bosses" in after and "menus" in after
    assert "soulslike" in after and "recusou" not in after  # o aprendizado automático saiu


def test_compose_briefing_from_quick_fields():
    text = style.compose_briefing("Elden Ring", "Melhores momentos", ["Vitória em boss"], "Ordem da live", "foca na Malenia")
    assert text == ("Jogo/conteúdo: Elden Ring. Tipo de vídeo: Melhores momentos. Priorizar: Vitória em boss. "
                    "Ordem: Ordem da live. foca na Malenia")


def test_cache_tokens_are_cheaper():
    full = usage.estimate_cost("claude-opus-5-5", 20000, 0)
    cached = usage.estimate_cost("claude-opus-5-5", 1000, 0, cache_read=19000)
    assert cached < full * 0.2


def test_daily_limit_blocks_after_spending(monkeypatch):
    monkeypatch.setenv("PAJAU_AI_DAILY_LIMIT_USD", "0.05")
    provider = FakeProvider({"summary": "", "approved": [], "rejected": []}, cost=0.06)
    build_review_plan(_candidates(), "x", 600.0, provider=provider)
    with pytest.raises(RuntimeError, match="Limite diário"):
        build_review_plan(_candidates(), "x", 600.0, provider=provider)


def test_request_file_lists_images_for_claude_code(tmp_path):
    from highlights.ai.providers import write_request_file
    image = tmp_path / "folha.jpg"
    image.write_bytes(b"x")
    path = write_request_file("SISTEMA", [TextPart("dados"), ImagePart(image)], tmp_path / "pedido.md")
    text = path.read_text(encoding="utf-8")
    assert "SISTEMA" in text and "dados" in text and f"[imagem: {image.resolve()}]" in text


def test_same_segment_can_be_split_without_overlap():
    provider = FakeProvider({"summary": "", "rejected": [], "approved": [
        {"id": "evento-01", "start": 10, "end": 30, "order": 1, "kind": "a", "reason": "", "confidence": 1, "transition": "corte"},
        {"id": "evento-01", "start": 25, "end": 40, "order": 2, "kind": "b", "reason": "", "confidence": 1, "transition": "corte"},
        {"id": "evento-01", "start": 50, "end": 80, "order": 3, "kind": "c", "reason": "", "confidence": 1, "transition": "corte"},
    ]})
    plan = build_review_plan(_candidates(), "x", 600.0, provider=provider)
    assert [(i.start, i.end) for i in plan.items] == [(10, 30), (50, 80)]  # pula a morte no meio


def test_chapters_discount_transitions_and_publication_text():
    from highlights.pipeline import chapters, publication_text
    items = [
        {"start": 100, "end": 400, "transition": "corte", "chapter": "Boss 1"},
        {"start": 900, "end": 1000, "transition": "fade_preto", "chapter": "Benkei"},  # 0,8 s de sobreposição
        {"start": 2000, "end": 2100, "transition": "corte", "chapter": "Vitória"},
    ]
    assert chapters(items) == [(0.0, "Boss 1"), (299.2, "Benkei"), (399.2, "Vitória")]
    pub = {"titles": ["A", "B", "C"], "description": "Desc.", "hashtags": ["#onimusha"]}
    text = publication_text(pub, items, "16:9")
    assert "0:00 Boss 1" in text and "4:59 Benkei" in text and "#onimusha" in text
    assert "0:00" not in publication_text(pub, items, "9:16")  # Short não tem capítulos
