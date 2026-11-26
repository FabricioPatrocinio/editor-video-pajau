# Pajau

Pajau é uma ferramenta open-source para encontrar melhores momentos em lives longas usando sinais de vídeo e áudio, sem IA/ML/LLM.

## Recursos

- Arquivos locais MP4/MKV/MOV/WEBM ou URL opcional do YouTube
- Sinais de áudio, chat, heatmap, cenas, silêncio e timestamps manuais
- Redistribuição automática de pesos para sinais indisponíveis
- Clips separados, compilado, CSV/JSON, gráfico e timeline MLT/EDL
- CLI e interface Gradio básica
- Cache dos sinais extraídos

## Pré-requisitos

```bash
sudo apt update
sudo apt install ffmpeg python3 python3-venv
```

## Instalação

```bash
cd ~/Documentos/editor-video-pajau
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

## Uso por arquivo local

```bash
python main.py analyze --input /caminho/live.mp4 --preset highlights_10min
```

Arquivo local é recomendado para controlar qualidade e evitar o download da plataforma.

## Exemplo para Shorts verticais

```bash
python main.py analyze --input /caminho/live.mp4 --preset shorts_60s_vertical --aspect 9:16
```

## URL do YouTube

```bash
python main.py analyze --url "https://youtube.com/watch?v=ID" --preset highlights_10min
```

A qualidade de download e os formatos de vídeo são definidos pelo yt-dlp. Antes de uma interface completa, configure o formato em `highlights/download/youtube.py`.

## Interface

```bash
python main.py ui --host 127.0.0.1 --port 7860
```

## Saídas

A saída padrão fica em `output/`:

- `clips/clip_*.mp4`
- `compilation.mp4`
- `project.json`
- `cuts.csv` e `cuts.json`
- `score.png`
- `kdenlive.mlt`
- `timeline.edl`

O cache fica em `cache/signals.npz` e permite reajustar a combinação de sinais sem repetir toda a extração.

## Testes

```bash
pip install pytest
pytest -q
```
