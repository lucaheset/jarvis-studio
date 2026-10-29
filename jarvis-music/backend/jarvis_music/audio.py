"""Utilidades de áudio compartilhadas."""
import numpy as np
import soundfile as sf
import librosa

SR = 44100


def carregar(caminho, sr=SR, mono=False):
    """Carrega áudio como float32 (canais, amostras) ou (amostras,) se mono."""
    y, _ = librosa.load(str(caminho), sr=sr, mono=mono)
    if not mono and y.ndim == 1:
        y = np.stack([y, y])
    return y.astype(np.float32)


def salvar(caminho, y, sr=SR):
    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 2:
        y = y.T
    sf.write(str(caminho), y, sr, subtype="PCM_16")


def para_mono(y):
    return y.mean(axis=0) if y.ndim == 2 else y


def picos(y, n=1200):
    """Envelope de picos para desenhar a forma de onda na interface (0..1)."""
    m = np.abs(para_mono(y))
    if len(m) == 0:
        return [0.0] * n
    tam = max(1, len(m) // n)
    m = m[: tam * n].reshape(-1, tam).max(axis=1) if len(m) >= n else np.pad(m, (0, n - len(m)))
    topo = float(m.max()) or 1.0
    return [round(float(v) / topo, 3) for v in m]


def rms_db(y):
    m = para_mono(y)
    return float(20 * np.log10(np.sqrt(np.mean(m ** 2)) + 1e-9))
