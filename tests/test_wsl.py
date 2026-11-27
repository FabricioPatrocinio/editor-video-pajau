from pathlib import Path

from highlights.ui.gradio_app import windows_para_wsl


def test_converte_caminho_do_windows_no_wsl(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/mnt/c")
    assert windows_para_wsl(r"C:\Users\Ana\Videos\live 1.mp4") == "/mnt/c/Users/Ana/Videos/live 1.mp4"
    assert windows_para_wsl("/home/ana/live.mp4") == "/home/ana/live.mp4"
