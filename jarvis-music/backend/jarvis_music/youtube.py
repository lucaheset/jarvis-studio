"""Baixa o áudio de um link (YouTube e outros sites que o yt-dlp aceita)."""
import shutil
from pathlib import Path

from . import ffmpeg


def link_valido(url):
    return isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))


def baixar(url, pasta, progresso=None):
    """Baixa só o áudio, converte para WAV e devolve (caminho, título)."""
    import yt_dlp

    pasta = Path(pasta)

    def gancho(d):
        if not progresso:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progresso(f"Baixando o áudio {int(d.get('downloaded_bytes', 0) * 100 / total)}%")
        elif d.get("status") == "finished":
            progresso("Convertendo o áudio")

    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": str(pasta / "original.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ffmpeg_location": ffmpeg.garantir(),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "progress_hooks": [gancho],
    }
    # o YouTube às vezes exige um interpretador de JavaScript; usa o Node se existir
    if shutil.which("node"):
        opcoes["js_runtimes"] = {"node": {}}

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info = ydl.extract_info(url.strip(), download=True)
    if info.get("entries"):
        info = info["entries"][0]

    caminho = pasta / "original.wav"
    if not caminho.exists():
        raise RuntimeError("o download terminou mas o áudio não foi encontrado")
    titulo = info.get("title") or "áudio do link"
    autor = info.get("artist") or info.get("uploader")
    return caminho, (f"{autor} - {titulo}" if autor and autor not in titulo else titulo)
