from pathlib import Path

from highlights.ui.gradio_app import windows_para_wsl


def test_converte_caminho_do_windows_no_wsl(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/mnt/c")
    assert windows_para_wsl(r"C:\Users\Ana\Videos\live 1.mp4") == "/mnt/c/Users/Ana/Videos/live 1.mp4"
    assert windows_para_wsl("/home/ana/live.mp4") == "/home/ana/live.mp4"


def test_upload_sai_da_pasta_temporaria(tmp_path):
    from highlights.ui.gradio_app import keep_upload
    upload = tmp_path / "gradio" / "live.mp4"
    upload.parent.mkdir()
    upload.write_bytes(b"x")
    kept = keep_upload(str(upload), tmp_path / "lives")
    assert Path(kept).read_bytes() == b"x" and not upload.exists()
