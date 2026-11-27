"""Configuração da IA lida do ambiente (.env).

A escolha do provedor é feita por uma única flag:

    PAJAU_USE_CLAUDE=true   -> Claude (Anthropic)
    PAJAU_USE_CLAUDE=false  -> OpenAI
"""
from __future__ import annotations

import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "sim", "yes", "on"}

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in TRUE_VALUES


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


@dataclass
class AISettings:
    provider: str
    model: str
    api_key: str
    effort: str
    daily_limit_usd: float
    max_candidates: int
    max_image_candidates: int

    @property
    def label(self) -> str:
        return f"{'Claude' if self.provider == 'claude' else 'OpenAI'} ({self.model})"

    @property
    def key_env(self) -> str:
        return "ANTHROPIC_API_KEY" if self.provider == "claude" else "OPENAI_API_KEY"


def load_ai_settings() -> AISettings:
    use_claude = env_flag("PAJAU_USE_CLAUDE", True)
    if use_claude:
        provider = "claude"
        model = os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_CLAUDE_MODEL
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    else:
        provider = "openai"
        model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        api_key = os.getenv("OPENAI_API_KEY", "").strip()

    return AISettings(
        provider=provider,
        model=model,
        api_key=api_key,
        effort=os.getenv("PAJAU_CLAUDE_EFFORT", "high").strip().lower(),
        daily_limit_usd=env_float("PAJAU_AI_DAILY_LIMIT_USD", 2.0),
        max_candidates=env_int("PAJAU_AI_MAX_CANDIDATES", 40),
        max_image_candidates=env_int("PAJAU_AI_MAX_IMAGE_CANDIDATES", 25),
    )


def check_ai_ready(settings: AISettings | None = None) -> str | None:
    """Retorna uma mensagem de erro amigável, ou None se a IA estiver pronta."""
    settings = settings or load_ai_settings()
    if not settings.api_key:
        flag = "true" if settings.provider == "claude" else "false"
        return (
            f"PAJAU_USE_CLAUDE={flag} escolhe {settings.label}, mas {settings.key_env} "
            "está vazio no arquivo `.env`."
        )
    return None
