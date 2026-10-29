"""Separação de instrumentos.

Motor principal: BS-RoFormer SW (6 stems, 1º no ranking de guitarra do MVSEP),
via pacote `audio-separator`. Reserva: Demucs htdemucs_6s.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import librosa

from .audio import carregar, salvar, SR

MODELO_PRINCIPAL = "BS-Roformer-SW.ckpt"

# palavra no nome do arquivo -> id da faixa
STEMS = {
    "vocals": "voz", "vocal": "voz",
    "guitar": "guitarra",
    "bass": "baixo",
    "drums": "bateria", "drum": "bateria",
    "piano": "piano",
    "other": "outros", "instrumental": "outros",
}


def _identificar(nome):
    n = nome.lower()
    for chave, id_ in STEMS.items():
        if f"({chave})" in n or f"_{chave}" in n or n.startswith(chave):
            return id_
    return None


def _com_audio_separator(entrada, saida, modelos_dir, aviso):
    from audio_separator.separator import Separator  # import tardio: pesado
    from . import gpu

    with gpu.uso("separação"):
        sep = Separator(output_dir=str(saida), model_file_dir=str(modelos_dir),
                        output_format="WAV", use_autocast=True,
                        mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                                     "batch_size": 1, "overlap": None, "pitch_shift": 0})
        aviso("Carregando BS-RoFormer SW")
        sep.load_model(model_filename=MODELO_PRINCIPAL)
        aviso("Separando instrumentos (BS-RoFormer SW)")
        try:
            arquivos = sep.separate(str(entrada))
        finally:
            # o modelo sai da placa assim que a separação acaba
            for nome in ("model_instance", "model"):
                if hasattr(sep, nome):
                    setattr(sep, nome, None)
            del sep
    return [Path(saida) / Path(a).name if not Path(a).is_absolute() else Path(a) for a in arquivos]


def _com_demucs(entrada, saida, aviso):
    aviso("Separando instrumentos (Demucs 6s)")
    tmp = Path(saida) / "_demucs"
    from . import gpu
    cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "-o", str(tmp), str(entrada)]
    if gpu.dispositivo() == "cpu":
        cmd[3:3] = ["-d", "cpu"]
    with gpu.uso("separação"):
        # processo filho com prioridade baixa; o processo termina e devolve toda a VRAM
        subprocess.run(cmd, check=True, creationflags=gpu.flags_subprocesso())
    return list(tmp.rglob("*.wav"))


def separar(entrada, saida, modelos_dir, aviso=print, motor="auto"):
    """Separa `entrada` em stems dentro de `saida`. Retorna {id: caminho_wav}."""
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    arquivos, erro = [], None
    if motor in ("auto", "roformer"):
        try:
            arquivos = _com_audio_separator(entrada, saida, modelos_dir, aviso)
        except Exception as e:  # sem pacote, sem GPU, sem rede...
            erro = e
            aviso(f"BS-RoFormer indisponível ({e.__class__.__name__}); usando Demucs")
    if not arquivos:
        try:
            arquivos = _com_demucs(entrada, saida, aviso)
        except Exception as e:
            raise RuntimeError(f"Nenhum separador funcionou: {erro or ''} {e}") from e

    stems = {}
    for a in arquivos:
        id_ = _identificar(a.name)
        if id_ and id_ not in stems:
            destino = saida / f"{id_}.wav"
            shutil.move(str(a), destino)
            stems[id_] = destino
    shutil.rmtree(saida / "_demucs", ignore_errors=True)
    return stems


def dividir_por_panorama(caminho, saida, limiar=0.35):
    """Divide uma faixa estéreo em Esquerda / Centro / Direita (máscara de panorama
    no espectrograma, método de Avendano). Guitarras de base costumam ser gravadas
    dobradas e abertas em L/R; o solo costuma ficar no centro.

    Retorna {id: caminho} só das partes com energia relevante.
    """
    y = carregar(caminho)
    if np.allclose(y[0], y[1], atol=1e-4):
        return {}  # mono: nada a dividir
    L = librosa.stft(y[0], n_fft=4096, hop_length=1024)
    R = librosa.stft(y[1], n_fft=4096, hop_length=1024)
    aL, aR = np.abs(L), np.abs(R)
    # índice de similaridade (1 = centro) e lado
    sim = 2 * np.abs(L * np.conj(R)) / (aL ** 2 + aR ** 2 + 1e-12)
    lado = np.sign(aR - aL)
    pan = (1 - sim) * lado  # -1 esquerda ... +1 direita
    suave = lambda m: np.clip(m, 0, 1)
    mascaras = {
        "esquerda": suave((-pan - limiar) / (1 - limiar) * 3),
        "direita": suave((pan - limiar) / (1 - limiar) * 3),
    }
    mascaras["centro"] = np.clip(1 - mascaras["esquerda"] - mascaras["direita"], 0, 1)
    energia_total = float((aL ** 2 + aR ** 2).sum()) + 1e-12
    partes = {}
    for nome, m in mascaras.items():
        yl = librosa.istft(L * m, hop_length=1024, length=y.shape[1])
        yr = librosa.istft(R * m, hop_length=1024, length=y.shape[1])
        fr = float(((np.abs(L * m) ** 2) + (np.abs(R * m) ** 2)).sum()) / energia_total
        if fr > 0.08:
            destino = Path(saida) / f"guitarra_{nome}.wav"
            salvar(destino, np.stack([yl, yr]), SR)
            partes[f"guitarra_{nome}"] = {"caminho": destino, "fracao": round(fr, 3)}
    # só vale a pena se houver ao menos dois lados realmente diferentes
    return partes if len(partes) >= 2 else {}
