"""Tarefas longas (analisar, gerar) rodando em segundo plano, com o progresso para a tela acompanhar."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable

# Etapas mostradas na tela e a partir de que ponto do progresso (0 a 1) cada uma começa.
ANALYSIS_STEPS = [("Tirando fotos da live no seu PC", 0.0), ("A IA está olhando a live inteira", 0.13),
                  ("Separando os melhores trechos", 0.31), ("Ouvindo o que foi falado", 0.62),
                  ("A IA está montando o vídeo", 0.9)]
EXPORT_STEPS = [("Cortando os trechos", 0.0), ("Juntando com as transições", 0.85),
                ("A IA está escolhendo as capas", 0.9), ("Finalizando", 0.98)]


@dataclass
class Job:
    title: str
    steps: list[tuple[str, float]]
    fraction: float = 0.0
    message: str = "Começando…"
    started: float = field(default_factory=time.monotonic)
    done: bool = False
    error: str = ""
    result_url: str = ""

    def report(self, fraction: float, message: str) -> None:
        self.fraction = max(self.fraction, min(0.99, float(fraction)))
        self.message = message

    @property
    def elapsed(self) -> str:
        seconds = int(time.monotonic() - self.started)
        return f"{seconds // 60}min {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"

    def step_states(self) -> list[tuple[str, str]]:
        """Cada etapa como feita, atual ou a fazer."""
        current = max(i for i, (_, start) in enumerate(self.steps) if self.fraction >= start)
        return [(name, "feito" if i < current or self.done else "agora" if i == current else "falta")
                for i, (name, _) in enumerate(self.steps)]


JOBS: dict[str, Job] = {}


def start(title: str, steps: list[tuple[str, float]], work: Callable[[Job], str]) -> str:
    """Roda `work` numa thread. Ela devolve o endereço da próxima tela."""
    job_id = uuid.uuid4().hex[:12]
    job = JOBS[job_id] = Job(title, steps)

    def run() -> None:
        try:
            job.result_url = work(job)
            job.fraction, job.done = 1.0, True
        except Exception as error:  # a tela mostra o erro; o detalhe vai para o terminal
            traceback.print_exc()
            job.error = str(error) or error.__class__.__name__

    threading.Thread(target=run, daemon=True).start()
    return job_id
