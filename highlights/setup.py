"""Assistente de configuração: `make setup`. Pergunta qual IA usar e grava no .env."""
from __future__ import annotations

import getpass
import shutil
import subprocess
from pathlib import Path

ENV = Path(".env")
EXAMPLE = Path(".env.example")

OPCOES = {
    "1": ("Claude pela assinatura (Pro/Max)", {"PAJAU_USE_CLAUDE": "true", "PAJAU_CLAUDE_VIA": "assinatura"}),
    "2": ("Claude com créditos de API", {"PAJAU_USE_CLAUDE": "true", "PAJAU_CLAUDE_VIA": "api"}),
    "3": ("OpenAI com créditos de API", {"PAJAU_USE_CLAUDE": "false"}),
}


def gravar(valores: dict[str, str]) -> None:
    if not ENV.exists():
        ENV.write_text(EXAMPLE.read_text() if EXAMPLE.exists() else "")
    linhas = ENV.read_text().splitlines()
    faltando = dict(valores)
    for i, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if chave in faltando and not linha.lstrip().startswith("#"):
            linhas[i] = f"{chave}={faltando.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in faltando.items()]
    ENV.write_text("\n".join(linhas) + "\n")


def ok(texto: str) -> None:
    print(f"  ✔ {texto}")


def falta(texto: str) -> None:
    print(f"  ✘ {texto}")


def checar_ffmpeg() -> bool:
    if shutil.which("ffmpeg"):
        ok("FFmpeg instalado")
        return True
    falta("FFmpeg não encontrado. Linux: sudo apt install ffmpeg | Mac: brew install ffmpeg")
    return False


def checar_claude_code() -> bool:
    if not shutil.which("claude"):
        falta("Claude Code não encontrado. Instale com:")
        print("      curl -fsSL https://claude.ai/install.sh | bash")
        print("    Depois rode `claude` uma vez e faça login com a sua conta.")
        return False
    teste = subprocess.run(["claude", "-p", "responda só: ok"], capture_output=True, text=True, timeout=120)
    if teste.returncode == 0:
        ok("Claude Code instalado e logado")
        return True
    falta("Claude Code instalado, mas sem login. Rode `claude` uma vez e entre com a sua conta.")
    return False


def pedir_chave(nome: str, link: str) -> None:
    print(f"\n  Crie a chave em: {link}")
    print("  (é preciso ter créditos pré-pagos na conta)")
    chave = getpass.getpass(f"  Cole a {nome} (não aparece na tela, Enter para pular): ").strip()
    if chave:
        gravar({nome: chave})
        ok(f"{nome} salva no .env (o .env não vai para o Git)")
    else:
        falta(f"Sem chave. Depois coloque {nome}= no arquivo .env")


def main() -> int:
    print("\nPajau — configuração\n")
    print("Qual IA você vai usar?")
    for numero, (nome, _) in OPCOES.items():
        print(f"  {numero}) {nome}")
    escolha = input("Escolha [1]: ").strip() or "1"
    if escolha not in OPCOES:
        print("Opção inválida.")
        return 1
    nome, valores = OPCOES[escolha]
    gravar(valores)
    print(f"\n{nome}:")

    tudo_ok = checar_ffmpeg()
    if escolha == "1":
        tudo_ok &= checar_claude_code()
    elif escolha == "2":
        pedir_chave("ANTHROPIC_API_KEY", "https://platform.claude.com/settings/keys")
    else:
        pedir_chave("OPENAI_API_KEY", "https://platform.openai.com/api-keys")

    print("\nPronto! Rode: make ui" if tudo_ok else "\nResolva o que está com ✘ e rode `make setup` de novo.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Rode `make setup` quando quiser.")
        raise SystemExit(1)
