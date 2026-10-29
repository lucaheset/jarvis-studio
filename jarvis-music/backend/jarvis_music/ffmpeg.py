"""Garante um ffmpeg disponível (o audio-separator e o yt-dlp precisam dele).

Se o ffmpeg não estiver no PATH, usa o binário que vem no pacote imageio-ffmpeg:
copia como bin/ffmpeg.exe e põe essa pasta no PATH deste processo.
"""
import os
import shutil
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "bin"


def garantir():
    """Devolve o caminho do ffmpeg, ou None se não houver como conseguir um."""
    existente = shutil.which("ffmpeg")
    if existente:
        return existente
    try:
        import imageio_ffmpeg
        origem = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not destino.exists() or destino.stat().st_size != origem.stat().st_size:
        shutil.copy2(origem, destino)
    os.environ["PATH"] = str(PASTA) + os.pathsep + os.environ.get("PATH", "")
    return str(destino)
