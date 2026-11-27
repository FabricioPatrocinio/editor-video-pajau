# Pajau

**Transforma uma live longa em um vídeo de melhores momentos.**
Você diz em poucas palavras o que quer ("vitórias contra boss"), a IA escolhe os trechos, você confere e o vídeo sai pronto.

- Roda no seu computador: o vídeo nunca sai da sua máquina.
- Usa a sua assinatura do Claude, sem custo extra. Também funciona com chave de API do Claude ou da OpenAI.
- Aprende o seu gosto a cada "Gostei" e "Não quero".

## Instalar

Funciona em **Linux** e **Mac**. No Windows, use o [WSL](https://learn.microsoft.com/pt-br/windows/wsl/install) (ainda não testado).

**1. Instale o básico** (só na primeira vez)

```bash
# Linux (Ubuntu/Debian)
sudo apt install git make ffmpeg python3-venv

# Mac
brew install git ffmpeg python
```

**2. Baixe e instale o Pajau**

```bash
git clone https://github.com/FabricioPatrocinio/editor-video-pajau.git
cd editor-video-pajau
make instalar
```

No final ele pergunta qual IA você vai usar. Escolha uma:

| Opção | O que você precisa |
|---|---|
| **1. Assinatura do Claude** (recomendado) | Plano Pro ou Max e o [Claude Code](https://claude.com/claude-code) instalado e logado |
| 2. Claude com créditos | Uma chave em [platform.claude.com](https://platform.claude.com/settings/keys) |
| 3. OpenAI com créditos | Uma chave em [platform.openai.com](https://platform.openai.com/api-keys) |

Mudou de ideia? Rode `make setup` para escolher de novo.

## Usar

```bash
make ui
```

O navegador abre sozinho. Escolha o vídeo da live, escreva o que você quer e clique para analisar. Confira os trechos, marque "Gostei" ou "Não quero" e gere o vídeo.

## Quanto custa

- **Pela assinatura do Claude:** nada a mais. Só usa o limite do seu plano.
- **Por créditos de API:** centavos por live. A IA não assiste ao vídeo inteiro: o seu computador acha os melhores trechos e manda só fotos pequenas e textos.

## Deu problema?

- **"claude: command not found"**: instale o [Claude Code](https://claude.com/claude-code), rode `claude` uma vez para fazer login e depois `make setup`.
- **"ffmpeg not found"**: volte ao passo 1.
- **Outra coisa**: abra uma [issue](../../issues) contando o que apareceu na tela.

Configurações avançadas ficam no arquivo `.env`, com a explicação de cada uma em [`.env.example`](.env.example).

## Apoie

O Pajau é livre e gratuito. Se ele te poupou horas de edição, considere um Pix:

**Chave Pix:** `PIX_AQUI`

## Contribuir

Ideias e correções são bem-vindas: abra uma [issue](../../issues) ou um pull request.

Licença [MIT](LICENSE).
