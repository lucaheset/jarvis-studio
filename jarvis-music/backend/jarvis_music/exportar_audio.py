"""Exporta as faixas separadas (stems) e a mixagem atual em WAV ou MP3.

WAV sai em 24 bits, do jeito que a DAW gosta; MP3 sai em 320 kbps (LAME).
Se houver uma versão com outra velocidade/tom, dá para exportar ela também.
"""
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from . import ffmpeg


def _fonte(dir_analise, faixa, chave_variacao=None):
    if chave_variacao:
        p = Path(dir_analise) / "variacoes" / chave_variacao / f"{faixa}.flac"
        if p.exists():
            return p
    return Path(dir_analise) / f"{faixa}.wav"


def _gravar(y, sr, destino, formato):
    """y: (amostras, canais) float32."""
    destino = Path(destino)
    if formato == "wav":
        sf.write(destino, y, sr, subtype="PCM_24")
        return destino
    tmp = destino.with_suffix(".tmp.wav")
    sf.write(tmp, y, sr, subtype="PCM_24")
    exe = ffmpeg.garantir() or "ffmpeg"
    subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp),
                    "-codec:a", "libmp3lame", "-b:a", "320k", str(destino)], check=True)
    tmp.unlink(missing_ok=True)
    return destino


def exportar(dir_analise, faixas, formato="wav", modo="stems", ganhos=None,
             chave_variacao=None, nome_base="musica"):
    """modo 'stems': um arquivo por faixa, num .zip. modo 'mix': um arquivo só,
    somando as faixas com os volumes/mudos/solos atuais (ganhos {faixa: 0..1.4})."""
    formato = "mp3" if formato == "mp3" else "wav"
    saida = Path(dir_analise) / "exportar"
    saida.mkdir(exist_ok=True)
    sufixo = f"_{chave_variacao}" if chave_variacao else ""
    limpo = "".join(ch for ch in nome_base if ch.isalnum() or ch in " -_").strip()[:60] or "musica"

    if modo == "mix":
        soma, sr = None, 44100
        for f in faixas:
            g = float((ganhos or {}).get(f, 1.0))
            if g <= 0:
                continue
            y, sr = sf.read(_fonte(dir_analise, f, chave_variacao), dtype="float32", always_2d=True)
            if soma is None:
                soma = y * g
            else:
                n = min(len(soma), len(y))
                soma = soma[:n] + y[:n] * g
        if soma is None:
            raise ValueError("nenhuma faixa audível na mixagem (tudo mudo?)")
        pico = float(np.max(np.abs(soma)))
        if pico > 0.98:
            soma = soma * (0.98 / pico)
        return _gravar(soma, sr, saida / f"{limpo} - mix{sufixo}.{formato}", formato)

    zip_path = saida / f"{limpo} - stems{sufixo} ({formato}).zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as z:
        for f in faixas:
            fonte = _fonte(dir_analise, f, chave_variacao)
            if not fonte.exists():
                continue
            y, sr = sf.read(fonte, dtype="float32", always_2d=True)
            arq = _gravar(y, sr, saida / f"{f}.{formato}", formato)
            z.write(arq, f"{limpo} - {f}.{formato}")
            arq.unlink(missing_ok=True)
    return zip_path
