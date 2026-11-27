PY := .venv/bin/python
MIN ?= 10
PEDIDO ?=
IGNORAR ?=

.PHONY: instalar setup ui cortar plano testes

instalar: ## cria o ambiente e instala tudo
	test -d .venv || python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[transcricao]"
	test -f .env || cp .env.example .env
	$(PY) -m highlights.setup

setup: ## escolhe a IA (assinatura ou chave) e confere o que falta
	$(PY) -m highlights.setup

ui: ## abre a interface no navegador
	$(PY) main.py ui

cortar: ## make cortar VIDEO=live.mp4 PEDIDO="..." [MIN=10] [IGNORAR="..."]
	$(PY) main.py auto --input "$(VIDEO)" --minutes $(MIN) --briefing "$(PEDIDO)" --avoid "$(IGNORAR)"

plano: ## igual ao cortar, mas só mostra o plano da IA
	$(PY) main.py auto --input "$(VIDEO)" --minutes $(MIN) --briefing "$(PEDIDO)" --avoid "$(IGNORAR)" --plan-only

testes:
	$(PY) -m pytest -q
