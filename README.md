# Pajau

**Transforma uma live longa em um vídeo de melhores momentos.**
Você diz em poucas palavras o que quer ("vitórias contra boss"), a IA escolhe os trechos, você confere e o vídeo sai pronto.

- Roda no seu computador: o vídeo nunca sai da sua máquina.
- Usa a sua assinatura do Claude, sem custo extra. Também funciona com chave de API do Claude ou da OpenAI.
- Aprende o seu gosto a cada "Gostei" e "Não quero".

## Instalar

Não precisa saber programar: é só copiar e colar os comandos, um de cada vez. Abra o guia do seu computador:

<details>
<summary><b>Windows</b></summary>

O Pajau roda no Windows pelo **WSL**, um Linux que a Microsoft oferece de graça dentro do Windows.

1. Clique no menu Iniciar, digite **PowerShell**, clique com o botão direito e escolha **Executar como administrador**.
2. Cole e aperte Enter:
   ```
   wsl --install
   ```
3. **Reinicie o computador.**
4. No menu Iniciar, abra **Ubuntu**. Na primeira vez ele pede um nome de usuário e uma senha (a senha não aparece enquanto você digita, é normal).
5. Na janela do Ubuntu, siga o guia **Linux** logo abaixo.

Para abrir o Pajau nas próximas vezes: abra o **Ubuntu** e rode `cd editor-video-pajau && make ui`.

</details>

<details>
<summary><b>Mac</b></summary>

1. Aperte <kbd>Cmd</kbd> + <kbd>Espaço</kbd>, digite **Terminal** e aperte Enter.
2. Instale o Homebrew (pode pedir a senha do Mac):
   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
   No final, ele mostra uns comandos em **Next steps**: copie e rode esses também.
3. Instale o que o Pajau usa:
   ```
   brew install git ffmpeg python
   ```
4. Baixe e instale o Pajau:
   ```
   git clone https://github.com/FabricioPatrocinio/editor-video-pajau.git
   cd editor-video-pajau
   make instalar
   ```

</details>

<details>
<summary><b>Linux</b> (e Windows pelo Ubuntu)</summary>

1. Instale o que o Pajau usa (pede a sua senha):
   ```
   sudo apt update && sudo apt install -y git make ffmpeg python3-venv
   ```
2. Baixe e instale o Pajau:
   ```
   git clone https://github.com/FabricioPatrocinio/editor-video-pajau.git
   cd editor-video-pajau
   make instalar
   ```

</details>

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

O navegador abre sozinho (se não abrir, acesse http://127.0.0.1:7860). Escolha o vídeo da live, escreva o que você quer e clique para analisar. Confira os trechos, marque "Gostei" ou "Não quero" e gere o vídeo.

## Quanto custa

- **Pela assinatura do Claude:** nada a mais. Só usa o limite do seu plano.
- **Por créditos de API:** centavos por live. A IA não assiste ao vídeo inteiro: o seu computador acha os melhores trechos e manda só fotos pequenas e textos.

## Deu problema?

- **"claude: command not found"**: instale o Claude Code com `curl -fsSL https://claude.ai/install.sh | bash`, feche e abra o terminal, rode `claude` uma vez para fazer login e depois `make setup`.
- **"ffmpeg not found"**: volte ao passo 1.
- **Outra coisa**: abra uma [issue](../../issues) contando o que apareceu na tela.

Configurações avançadas ficam no arquivo `.env`, com a explicação de cada uma em [`.env.example`](.env.example).

## Apoie

O Pajau é livre e gratuito. Se ele te poupou horas de edição, considere um Pix:

**Chave Pix:** `PIX_AQUI`

## Contribuir

Ideias e correções são bem-vindas: abra uma [issue](../../issues) ou um pull request.

Licença [MIT](LICENSE).
