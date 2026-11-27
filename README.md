# Pajau

Transforma uma live longa em um vídeo de melhores momentos. Você diz o que quer, a IA escolhe os trechos e as transições, você confere e gera.

## Começar

```bash
sudo apt install ffmpeg python3-venv
make instalar
```

Coloque sua chave no `.env` (`ANTHROPIC_API_KEY=`). Crie a chave em https://platform.claude.com/settings/keys

## Usar

```bash
make ui                                                  # interface no navegador
make cortar VIDEO=live.mp4 PEDIDO="vitórias contra boss"  # direto para o vídeo final
make plano  VIDEO=live.mp4 PEDIDO="..."                   # só vê o plano, não gera vídeo
```

Na interface, salve uma vez o **Meu estilo**. Depois, cada pedido pode ser curto. Os seus "Gostei" e "Não quero" ensinam a IA.

## Como a IA escolhe

A IA **não** assiste à live. O seu computador faz o trabalho pesado:

1. O FFmpeg mede o volume e as mudanças de cena e acha uns 40–60 trechos candidatos.
2. Cada candidato vira 3 fotos pequenas (480px) e, opcionalmente, uma transcrição feita no seu PC.
3. Só isso vai para a IA: a lista, o texto e as fotos. Ela devolve quais trechos usar, em que ordem e com qual transição.

**Custo:** cerca de 25 mil tokens por análise, sendo metade das fotos. Com o Claude Opus, isso dá por volta de US$ 0,20–0,30. O "Refazer só o plano" reaproveita o que já foi enviado e sai bem mais barato. Mandar o vídeo inteiro custaria centenas de vezes mais.

## Configurar

Tudo fica no `.env`; os valores possíveis estão em `.env.example`. O principal:

| Variável | Para quê |
|---|---|
| `PAJAU_USE_CLAUDE` | `true` = Claude, `false` = OpenAI |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` (padrão) ou `claude-sonnet-5-5` (metade do preço) |
| `PAJAU_TRANSCRIBE` | `true` transcreve as falas (melhora muito as escolhas) |
| `PAJAU_AI_DAILY_LIMIT_USD` | trava de gasto por dia |
