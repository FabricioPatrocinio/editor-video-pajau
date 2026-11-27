# IA assistida para escolher cortes — guia prático

## Visão curta

É viável usar IA para selecionar momentos de uma live, mas não enviar o vídeo completo ao ChatGPT ou Claude. A ferramenta deve primeiro preparar dados pequenos:

1. analisar o áudio;
2. gerar transcrição e procurar emoção, risadas, frases fortes e mudanças de ritmo;
3. dividir o vídeo em candidatos;
4. gerar poucas imagens de cada candidato, em baixa resolução;
5. enviar ao modelo somente uma lista estruturada desses candidatos;
6. pedir uma decisão explicada em JSON;
7. mostrar os candidatos em uma revisão humana;
8. editar somente os trechos aprovados.

O modelo decide a importância. O FFmpeg continua responsável por cortes, recortes verticais e exportação.

## O fluxo recomendado

### 1. Entrada

A interface recebe:

- vídeo local ou URL;
- duração desejada, por exemplo 10 minutos;
- formato horizontal 16:9 ou vertical 9:16;
- quantidade aproximada de bosses e desafios comuns;
- instruções em linguagem natural;
- partes para ignorar;
- revisão automática ou humana.

Exemplo de ideia:

> Quero um vídeo de 10 minutos sobre a live de hoje. Priorize a vitória final contra cada boss. Se houver espaço, inclua uma ou duas mortes engraçadas e dois momentos bons enfrentando inimigos comuns. Remova loading, menus e momentos de repetição.

### 2. Preparação local

Não é necessário analisar todos os frames em alta resolução. Uma boa primeira versão pode usar:

- áudio extraído em WAV ou MP4;
- miniaturas a cada 10–20 segundos;
- uma amostra de 3 imagens por candidato;
- transcrição com timestamps;
- volume e silêncios;
- mudanças de cena;
- chat, quando disponível;
- timestamps fornecidos pelo usuário.

Para diminuir custo e processamento:

- candidatos já podem ter 20–90 segundos;
- frames usados pela IA podem ter cerca de 640 pixels de largura;
- segmentos muito semelhantes devem ser agrupados;
- trechos com loading, menu ou silêncio podem ser excluídos antes da IA;

Os sinais atuais do projeto já ajudam a localizar candidatos. A IA decide quais combinações são realmente interessantes e evita repetições.

### 3. Pedido à IA

Os dados enviados podem parecer com:

```json
{
  "duracao_alvo": 600,
  "formato": "16:9",
  "brifing": "Priorizar vitórias contra bosses e variedade; evitar mortes repetitivas.",
  "candidatos": [
    {
      "id": "candidato_12",
      "inicio": 10420,
      "fim": 10518,
      "transcricao": "Essa foi a última tentativa... consegui!",
      "audio": "pico de volume com aplausos",
      "mudanca_de_cena": true
    }
  ]
}

```

A resposta esperada também deve ser JSON:

```json
{
  "aprovados": [
    {
      "id": "candidato_12",
      "inicio": 10415,
      "fim": 10524,
      "motivo": "Vitória final clara contra um boss, com reação forte.",
      "confianca": 0.92,
      "tipo": "boss_vitoria"
    }
  ],
  "descartados": [
    {
      "id": "candidato_18",
      "motivo": "Tentativa repetitiva sem resolução ou reação interessante."
    }
  ],
  "observacao": "Inclua mais uma tentativa engraçada apenas se houver espaço após os bosses."
}
```

O usuário pode revisar o plano antes da exportação.

### 4. Revisão humana

Antes de gerar o vídeo final, a interface deve mostrar:

- miniaturas e áudio dos candidatos;
- início e fim sugeridos;
- motivo da escolha;
- nível de confiança;
- tipo do momento;
- botão Gostei, Não quero e Ajustar corte;
- plano da sequência em ordem ou por pontuação;
- duração acumulada;

Isso evita que um corte errado seja exportado automaticamente.

## Arquitetura proposta

```text
Vídeo/URL
  -> FFmpeg: áudio, imagens e trechos
  -> Whisper ou serviço equivalente: transcrição
  -> Analisadores locais: volume, cenas, silêncio e candidatos
  -> IA: ranking, contexto e justificativas
  -> Revisão humana
  -> FFmpeg: cortes horizontais ou verticais
  -> Vídeo compilado
```

Uma primeira versão pode manter tudo local:

- interface: Gradio;
- vídeo e thumbnails: FFmpeg;
- transcrição: Whisper local, se o equipamento permitir;
- sugestões: API de modelo externo;
- exportação: FFmpeg;
- cache: arquivos existentes em `cache/`;
- projeto: JSON existente em `output/`.

O arquivo original não precisa ser enviado para a API.

## Custo e uso de tokens

Envie texto e algumas imagens compactadas dos melhores candidatos. Não envie:

- o MP4 completo;
- todos os frames da live;
- transcrição inteira sem timestamps;
- áudio bruto longo;
- mais imagens do que o modelo precisa;

Uma maneira simples de controlar custo é processar em fases:

1. candidatos locais baratos;
2. transcrição local em áudio compacto;
3. ranking textual dos 50–100 melhores candidatos;
4. vision apenas nos 15–30 candidatos mais promissores;
5. revisão humana dos 8–12 candidatos finais.

Para uma live de três horas, a IA não precisa ver três horas de frames.

## Onde entra o plano gratuito

Planos e limites mudam. O projeto não deve depender de acesso gratuito ou de uma assinatura específica.

Para começar, use uma API própria, ambiente local ou um modelo aberto executado na máquina. Se a API estiver configurada com cobrança, um limite local deve bloquear gastos acima de um valor escolhido.

O projeto pode guardar o provedor e o modelo em configuração, por exemplo:

```yaml
ia:
  provedor: openai
  modelo: modelo-escolhido
  limite_gasto_dia: 2.00
  enviar_frames: false
  transcricao_local: true
```

Para o ChatGPT gratuito ou assinaturas do produto ChatGPT: verifique no site oficial se a conta oferece API. O acesso ao chat do site normalmente não é o mesmo que acesso programático. Não coloque credenciais no código ou no Git.

### Alternativa recomendada: OpenAI API

1. Abra o portal oficial de API da OpenAI.
2. Entre na sua conta.
3. Configure faturamento ou limite de gastos, quando exigido pelo tipo de conta.
4. Crie uma chave da API em `API Keys`.
5. Copie a chave somente uma vez e guarde em segredo.

Uma implementação local pode ler, por exemplo:

```bash
export OPENAI_API_KEY="sua-chave"
export OPENAI_MODEL="modelo-escolhido"
python main.py ui
```

Se aparecerem `quota exceeded`, `insufficient_quota` ou `429`, a solução pode ser limite de conta, cobrança não configurada ou limite da API; não significa necessariamente que o ChatGPT gratuito foi usado pela aplicação.

### Segurança da chave

- não use `OPENAI_API_KEY=...` dentro de arquivos versionados;
- use uma variável de ambiente ou um arquivo `.env` ignorado pelo Git;
- adicione `.env` ao `.gitignore`;
- nunca cole a chave no chat, em prints ou em `project.json`;
- permita revogar e criar outra chave imediatamente;
- adicione limites de uso no provedor.

## Suporte a outros provedores

Claude ou ChatGPT podem ser integrados pela mesma interface, desde que tenham API disponível para a conta utilizada. O núcleo do projeto não deve depender diretamente de uma marca:

```text
provedor
  -> adaptador de texto
  -> adaptador de imagem
  -> resposta JSON comum
```

Isso permite trocar de modelo sem reescrever a aplicação.

## Evolução em fases

### Fase 1 — candidatos e revisão

- adicionar briefing em texto;
- adicionar duração e formato na interface;
- manter os candidatos atuais;
- enviar ranking textual à IA;
- mostrar motivo e permitir Gostei/Não quero.

### Fase 2 — contexto visual

- gerar 3 frames por candidato;
- pedir a visão do modelo sobre vitória, derrota, reação e repetição;
- ajustar início e fim com base no contexto.

### Fase 3 — sequência inteligente

- respeitar duração total;
- diversificar bosses e inimigos comuns;
- evitar mortes repetitivas;
- evitar longos períodos sem ação;
- sugerir uma ordem narrativa;
- permitir pedir outra versão.

### Fase 4 — vertical

- selecionar momentos com ação no centro;
- detectar pessoas ou boss na área principal;
- recortar 9:16 com rastreamento simples;
- permitir abrir shorts individuais além do compilado.

## Prompt inicial de revisão

Use este pedido como primeira versão:

> Analise os candidatos de uma live de jogo. O objetivo é produzir um vídeo curto com momentos claros e variados. Priorize vitórias contra bosses, tentativas com reação intensa e momentos engraçados ou executados com habilidade. Inclua no máximo um ou dois momentos contra inimigos comuns. Evite repetição de mortes, loading, menus e períodos sem ação. Responda somente em JSON, explique cada escolha em uma frase e respeite a duração máxima.

## Limitação realista

A IA não deve converter o vídeo inteiro em uma ação perfeita de uma vez. Ela pode errar bosses, ações rápidas e contexto narrativo. A melhor primeira versão será semiautomática:

- algoritmo prepara candidatos;
- IA cria um plano explicado;
- usuário aprova antes da exportação;
- FFmpeg produz o resultado.

Isso reduz custo, permite corrigir erros e aproveita melhor o conhecimento real do canal.

## Estado atual da implementação

- Provedor escolhido por `PAJAU_USE_CLAUDE=true|false` no `.env` (Claude por padrão; OpenAI continua disponível).
- Código em `highlights/ai/`: `config.py` (variáveis), `prompt.py` (prompt e formato JSON comuns), `providers.py` (um adaptador por provedor), `plan.py` (monta o pedido e valida a resposta), `usage.py` (limite diário de gasto).
- Com Claude, a resposta usa saída estruturada (JSON garantido pelo schema), raciocínio adaptativo com `PAJAU_CLAUDE_EFFORT` e fallback automático no servidor em caso de recusa.
- A análise local encontra cerca de 4× mais candidatos que a duração final, para a IA ter opções de verdade.
- `PAJAU_TRANSCRIBE=true` transcreve localmente só os candidatos (faster-whisper, CPU) e envia o texto à IA.
- A IA recebe briefing, "o que ignorar", duração alvo, sinais e transcrição de até 40 candidatos, e 3 miniaturas rotuladas de até 25 deles.
- A resposta só pode usar trechos dentro dos candidatos; o plano é salvo em `ia-plan.json` e passa por revisão na interface (ou exportação direta com `python main.py auto`).
- O gasto estimado do dia fica em `cache/ai-usage.json`; acima de `PAJAU_AI_DAILY_LIMIT_USD` novas análises são bloqueadas.
- A IA também escolhe a transição de entrada de cada trecho (`corte`, `fade`, `fade_preto`, `deslizar`); o FFmpeg aplica com `xfade`/`acrossfade` (`highlights/export/transitions.py`).
- O pedido à IA é montado com a parte fixa primeiro (candidatos e imagens, com cache da API) e o briefing por último, para "Refazer só o plano" sair barato.
- A análise local fica salva por vídeo em `output/<nome>-<hash>/` e é reaproveitada.
- "Meu estilo" e o histórico de Gostei/Não quero ficam em `data/estilo.json` e vão em toda análise.
