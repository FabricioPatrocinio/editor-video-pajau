from pathlib import Path

from highlights.web.logic import safe_upload_name, windows_para_wsl


def test_converte_caminho_do_windows_no_wsl(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/mnt/c")
    assert windows_para_wsl(r"C:\Users\Ana\Videos\live 1.mp4") == "/mnt/c/Users/Ana/Videos/live 1.mp4"
    assert windows_para_wsl("/home/ana/live.mp4") == "/home/ana/live.mp4"


def test_nome_do_arquivo_enviado_nao_sai_da_pasta():
    assert safe_upload_name("../../etc/passwd") == "passwd.mp4"
    assert safe_upload_name("Minha Live – Parte 1.mp4") == "Minha Live _ Parte 1.mp4"
