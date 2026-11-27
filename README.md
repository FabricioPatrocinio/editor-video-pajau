# Pajau

Transforma uma live longa em um vídeo de melhores momentos. Você diz o que quer, a IA escolhe os trechos e as transições, você confere e gera.

## Começar

```bash
sudo apt install ffmpeg python3-venv   # Mac: brew install ffmpeg
make instalar
```

O `make instalar` pergunta qual IA você vai usar e confere o que falta. Para trocar depois: `make setup`.

| Opção | Precisa de |
|---|---|
| Claude pela assinatura (padrão) | Plano Pro ou Max e o [Claude Code](https://claude.com/claude-code) logado. Sem custo extra. |
| Claude por API | Chave e créditos em [platform.claude.com](https://platform.claude.com/settings/keys) |
| OpenAI por API | Chave e créditos em [platform.openai.com](https://platform.openai.com/api-keys) |

Tudo roda no seu computador: o vídeo nunca sai da sua máquina.

## Usar

```bash
make ui                                                  # interface no navegador
make cortar VIDEO=live.mp4 PEDIDO="vitórias contra boss"  # direto para o vídeo final
make plano  VIDEO=live.mp4 PEDIDO="..."                   # só vê o plano, não gera vídeo
```

Ou converse comigo no Claude Code: `/cortar /caminho/live.mp4 10 vitórias contra boss`

Na interface, salve uma vez o **Meu estilo**. Depois, cada pedido pode ser curto. Os seus "Gostei" e "Não quero" ensinam a IA.

## Como a IA escolhe

A IA **não** assiste à live. O seu computador faz o trabalho pesado:

1. O FFmpeg mede o volume e as mudanças de cena e acha uns 40–60 trechos candidatos.
2. Cada candidato vira 3 fotos pequenas (480px) e, opcionalmente, uma transcrição feita no seu PC.
3. Só isso vai para a IA: a lista, o texto e as fotos. Ela devolve quais trechos usar, em que ordem e com qual transição.

As fotos vão juntas em "folhas de contato" (5 trechos por imagem), que gastam menos.

**Custo:** pela assinatura, não tem custo extra; só consome o limite do seu plano. Pela API, cada análise sai por uns US$ 0,20 com o Opus. Mandar o vídeo inteiro custaria centenas de vezes mais.

## Configurar

Tudo fica no `.env`; os valores possíveis estão em `.env.example`. O principal:

| Variável | Para quê |
|---|---|
| `PAJAU_USE_CLAUDE` | `true` = Claude, `false` = OpenAI |
| `PAJAU_CLAUDE_VIA` | `assinatura` (padrão, sem custo extra) ou `api` (créditos) |
| `PAJAU_TRANSCRIBE` | `true` transcreve as falas (melhora muito as escolhas) |
| `PAJAU_AI_DAILY_LIMIT_USD` | trava de gasto por dia |

## Apoie

O Pajau é livre e gratuito. Se ele te poupou horas de edição, considere um Pix:

**Chave Pix:** `PIX_AQUI`

## Contribuir

Achou um bug ou tem uma ideia? Abra uma [issue](../../issues). Pull requests são bem-vindos.

Licença [MIT](LICENSE).
