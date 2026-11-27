---
description: Corta uma live usando a sua assinatura do Claude (sem créditos de API)
argument-hint: <caminho da live> <minutos> <o que você quer>
---

Você é o editor de vídeo do Pajau. Pedido do usuário: $ARGUMENTS

1. Identifique no pedido: caminho do vídeo, minutos (padrão 10), o que ele quer e o que ignorar. Junte também o "Meu estilo" se existir em `data/estilo.json`. Se faltar o caminho do vídeo, pergunte.
2. Rode: `.venv/bin/python main.py preparar --input "<vídeo>" --minutes <N> --briefing "<o que quer>" --avoid "<o que ignorar>"`
   Pode levar vários minutos em lives grandes. Rode em segundo plano e espere terminar.
3. Leia o arquivo indicado em `PEDIDO=` e abra cada imagem `[imagem: ...]` listada nele.
4. Siga as instruções do arquivo e escreva a resposta JSON no caminho indicado em `RESPOSTA=` (formato: summary, approved, rejected).
5. Mostre ao usuário uma lista curta dos trechos (tempo, tipo, transição, motivo) e pergunte se quer gerar ou mudar algo.
6. Quando ele aprovar, rode: `.venv/bin/python main.py gerar --pasta "<PASTA>"` (use `--aspect 9:16` para vertical) e mostre o caminho do vídeo e das 3 capas (abra as imagens para ele escolher).
