"""Adaptadores de provedores de IA.

Todos recebem o mesmo pedido (prompt de sistema + partes de texto e imagem) e devolvem
o mesmo resultado: um dicionário no formato de `prompt.PLAN_SCHEMA` e o uso de tokens.
Para adicionar outro provedor, basta criar uma classe com o método `generate_plan`.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import AISettings
from .prompt import JSON_INSTRUCTION, PLAN_SCHEMA
from .usage import Usage, estimate_cost


@dataclass
class TextPart:
    text: str
    # Marca o fim da parte fixa do pedido: tudo até aqui é reaproveitado do cache
    # quando você refaz o plano com outro briefing.
    cache: bool = False


@dataclass
class ImagePart:
    path: Path
    media_type: str = "image/jpeg"

    def b64(self) -> str:
        return base64.b64encode(self.path.read_bytes()).decode("ascii")


Part = TextPart | ImagePart


class AIProvider(Protocol):
    settings: AISettings

    def generate_plan(self, system: str, parts: list[Part], schema: dict = PLAN_SCHEMA,
                      json_hint: str = JSON_INSTRUCTION) -> tuple[dict, Usage]: ...


def _decode_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


# Modelos que aceitam o fallback automático do servidor quando um filtro de segurança
# recusa o pedido (raro aqui, mas evita uma análise perdida).
_CLAUDE_FALLBACK_MODELS = {
    "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
}


class ClaudeProvider:
    def __init__(self, settings: AISettings):
        import anthropic

        self.settings = settings
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.api_key, max_retries=3)

    def _content(self, parts: list[Part]) -> list[dict]:
        content: list[dict] = []
        for part in parts:
            if isinstance(part, TextPart):
                block: dict = {"type": "text", "text": part.text}
                if part.cache:
                    block["cache_control"] = {"type": "ephemeral"}
                content.append(block)
            else:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": part.media_type, "data": part.b64()},
                })
        return content

    def generate_plan(self, system: str, parts: list[Part], schema: dict = PLAN_SCHEMA,
                      json_hint: str = JSON_INSTRUCTION) -> tuple[dict, Usage]:
        anthropic = self._anthropic
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if self.settings.effort:
            output_config["effort"] = self.settings.effort

        request = dict(
            model=self.settings.model,
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": self._content(parts)}],
            output_config=output_config,
        )

        try:
            if self.settings.model in _CLAUDE_FALLBACK_MODELS:
                stream = self.client.beta.messages.stream(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
                )
            else:
                stream = self.client.messages.stream(**request)
            with stream as active:
                message = active.get_final_message()
        except anthropic.AuthenticationError as error:
            raise RuntimeError("ANTHROPIC_API_KEY inválida ou revogada. Gere outra em platform.claude.com.") from error
        except anthropic.PermissionDeniedError as error:
            raise RuntimeError(f"A chave não tem acesso ao modelo {self.settings.model}.") from error
        except anthropic.NotFoundError as error:
            raise RuntimeError(f"Modelo não encontrado: {self.settings.model}. Revise ANTHROPIC_MODEL.") from error
        except anthropic.RateLimitError as error:
            raise RuntimeError("Limite de uso da API Claude atingido (429). Aguarde um pouco e tente de novo.") from error
        except anthropic.BadRequestError as error:
            text = str(error)
            if "credit balance" in text.lower():
                raise RuntimeError(
                    "Sem créditos na API Claude. Adicione créditos em platform.claude.com > Billing."
                ) from error
            raise RuntimeError(f"Pedido recusado pela API Claude: {text[:400]}") from error
        except anthropic.APIStatusError as error:
            raise RuntimeError(f"Erro da API Claude ({error.status_code}): {str(error)[:300]}") from error
        except anthropic.APIConnectionError as error:
            raise RuntimeError(f"Não foi possível acessar a API Claude: {error}") from error

        usage = Usage(
            input_tokens=message.usage.input_tokens or 0,
            output_tokens=message.usage.output_tokens or 0,
            cache_read=getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            cache_write=getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
        )
        usage.cost_usd = estimate_cost(
            self.settings.model, usage.input_tokens, usage.output_tokens, usage.cache_read, usage.cache_write
        )

        if message.stop_reason == "refusal":
            raise RuntimeError("O Claude recusou o pedido. Revise o briefing e tente novamente.")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("A resposta da IA foi cortada (max_tokens). Reduza PAJAU_AI_MAX_CANDIDATES.")

        text = "".join(block.text for block in message.content if block.type == "text")
        if not text.strip():
            raise RuntimeError("A IA não retornou texto utilizável.")
        return _decode_json(text), usage


class OpenAIProvider:
    def __init__(self, settings: AISettings):
        self.settings = settings

    def generate_plan(self, system: str, parts: list[Part], schema: dict = PLAN_SCHEMA,
                      json_hint: str = JSON_INSTRUCTION) -> tuple[dict, Usage]:
        import httpx

        content: list[dict] = []
        for part in parts:
            if isinstance(part, TextPart):
                content.append({"type": "input_text", "text": part.text})
            else:
                content.append({"type": "input_image", "image_url": f"data:{part.media_type};base64,{part.b64()}"})
        content.append({"type": "input_text", "text": json_hint})

        endpoint = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/") + "/responses"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.settings.model,
                    "input": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                },
                timeout=180.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = error.response.text
            if error.response.status_code == 429:
                try:
                    code = error.response.json().get("error", {}).get("code")
                except ValueError:
                    code = None
                if code in ("credit_balance_exhausted", "insufficient_quota"):
                    raise RuntimeError("Sem créditos na API OpenAI. Adicione créditos em platform.openai.com.") from error
            raise RuntimeError(f"Erro da API OpenAI ({error.response.status_code}): {detail[:300]}") from error
        except httpx.RequestError as error:
            raise RuntimeError(f"Não foi possível acessar a API OpenAI: {error}") from error

        data = response.json()
        texts = [
            item.get("text", "")
            for output in data.get("output", []) if output.get("type") == "message"
            for item in output.get("content", []) if item.get("type") in ("output_text", "text")
        ]
        if not texts:
            raise RuntimeError("A IA não retornou texto utilizável.")
        raw_usage = data.get("usage", {})
        usage = Usage(raw_usage.get("input_tokens", 0), raw_usage.get("output_tokens", 0))
        return _decode_json("".join(texts)), usage


def write_request_file(system: str, parts: list[Part], path: Path, json_hint: str = JSON_INSTRUCTION) -> Path:
    """Pedido completo em Markdown, com os caminhos das imagens. Usado pelo Claude Code."""
    lines = [system, "", "## Dados", ""]
    for part in parts:
        if isinstance(part, TextPart):
            lines += [part.text, ""]
        else:
            lines += [f"[imagem: {part.path.resolve()}]", ""]
    lines += ["## Resposta", "", json_hint]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class ClaudeCodeProvider:
    """Usa o Claude Code (`claude -p`) logado na sua conta: o uso sai dos limites da assinatura."""

    def __init__(self, settings: AISettings):
        self.settings = settings

    def generate_plan(self, system: str, parts: list[Part], schema: dict = PLAN_SCHEMA,
                      json_hint: str = JSON_INSTRUCTION) -> tuple[dict, Usage]:
        import shutil
        import subprocess
        import tempfile

        images = [part.path for part in parts if isinstance(part, ImagePart)]
        folder = images[0].resolve().parent if images else Path(tempfile.mkdtemp(prefix="pajau-"))
        name = "ia-mapa.md" if schema is not PLAN_SCHEMA else "ia-pedido.md"
        request = write_request_file(system, parts, folder / name, json_hint)

        command = [
            shutil.which("claude") or "claude", "-p",
            f"Leia o arquivo {request} e abra cada imagem listada nele com a ferramenta Read. "
            "Depois responda exatamente o que o arquivo pede, no formato JSON do schema.",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--allowedTools", "Read",
            "--add-dir", str(folder),
        ]
        if self.settings.model:
            command += ["--model", self.settings.model]
        # Sem ANTHROPIC_API_KEY no ambiente, o Claude Code usa o login da assinatura.
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        try:
            run = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("O Claude Code demorou mais de 30 minutos. Tente de novo.") from error

        try:
            data = json.loads(run.stdout)
        except ValueError as error:
            detail = (run.stderr or run.stdout).strip()[:400]
            raise RuntimeError(f"O Claude Code não respondeu como esperado: {detail}") from error
        if data.get("is_error"):
            message = str(data.get("result", ""))[:400]
            if "limit" in message.lower():
                raise RuntimeError(f"Limite da assinatura atingido: {message}")
            raise RuntimeError(f"Erro do Claude Code: {message}")

        result = data.get("structured_output") or _decode_json(str(data.get("result", "")))
        raw = data.get("usage", {})
        usage = Usage(
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            cache_read=raw.get("cache_read_input_tokens", 0),
            cache_write=raw.get("cache_creation_input_tokens", 0),
            subscription=True,
            equivalent_usd=data.get("total_cost_usd"),
        )
        return result, usage


def get_provider(settings: AISettings) -> AIProvider:
    if settings.provider == "claude-code":
        return ClaudeCodeProvider(settings)
    if settings.provider == "claude":
        return ClaudeProvider(settings)
    return OpenAIProvider(settings)
