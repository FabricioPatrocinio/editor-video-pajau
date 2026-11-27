"""Controle local de gasto diário com a API de IA.

O limite é uma proteção extra: configure também o limite de gasto no painel do provedor.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LEDGER = Path("cache") / "ai-usage.json"

# Preço em USD por 1 milhão de tokens (entrada, saída). Modelos fora da tabela
# não têm o custo estimado; o limite diário não consegue protegê-los.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5-2": (8.00, 40.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    cache_read: int = 0
    cache_write: int = 0
    subscription: bool = False
    equivalent_usd: float | None = None  # quanto custaria na API (informado pelo Claude Code)

    @property
    def text(self) -> str:
        if self.subscription:
            cost = "pela assinatura, sem custo extra"
            if self.equivalent_usd:
                cost += f" (equivale a ~US$ {self.equivalent_usd:.2f} na API)"
        else:
            cost = f"~US$ {self.cost_usd:.3f}" if self.cost_usd is not None else "custo não estimado"
        number = lambda value: f"{value:,}".replace(",", ".")
        total_in = self.input_tokens + self.cache_read + self.cache_write
        cached = f" ({number(self.cache_read)} do cache)" if self.cache_read else ""
        return f"{number(total_in)} tokens de entrada{cached} e {number(self.output_tokens)} de saída, {cost}"


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float | None:
    price = PRICES_PER_MTOK.get(model)
    if not price:
        return None
    # Leitura de cache custa 10% da entrada; escrita (cache de 5 min) custa 125%.
    billed_input = input_tokens + cache_read * 0.1 + cache_write * 1.25
    return (billed_input * price[0] + output_tokens * price[1]) / 1_000_000


def _read() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def spent_today() -> float:
    return float(_read().get(date.today().isoformat(), 0.0))


def ensure_budget(limit_usd: float) -> None:
    if limit_usd <= 0:
        return
    spent = spent_today()
    if spent >= limit_usd:
        raise RuntimeError(
            f"Limite diário de IA atingido: US$ {spent:.2f} de US$ {limit_usd:.2f}. "
            "Aumente PAJAU_AI_DAILY_LIMIT_USD no .env ou tente amanhã."
        )


def record(usage: Usage) -> None:
    if usage.cost_usd is None:
        return
    data = _read()
    today = date.today().isoformat()
    data[today] = round(float(data.get(today, 0.0)) + usage.cost_usd, 6)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data, indent=2), encoding="utf-8")
