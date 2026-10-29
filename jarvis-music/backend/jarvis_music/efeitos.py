"""Estimativa dos efeitos na faixa de guitarra.

Duas camadas:
 1. Classificador aberto (SFXlearner, ResNet-18, 13 efeitos) quando houver pesos
    locais. Em música misturada a precisão cai bastante.
 2. Medidas de áudio, que sempre rodam e explicam o porquê: saturação,
    cauda de reverb, tempo do delay em relação ao BPM, modulação e brilho.
"""
import numpy as np
import librosa

from .audio import para_mono, SR

ROTULOS_SFX = ["overdrive", "distorção", "chorus", "flanger", "phaser", "tremolo",
               "reverb", "delay com repetições", "slapback delay",
               "reforço de graves", "corte de graves", "reforço de agudos", "corte de agudos"]


def _sfxlearner(y, pesos, sr=SR):
    """Roda o ResNet-18 do SFXlearner se os pesos estiverem no disco."""
    import torch
    from torchvision.models import resnet18

    modelo = resnet18(num_classes=len(ROTULOS_SFX))
    estado = torch.load(str(pesos), map_location="cpu")
    modelo.load_state_dict(estado.get("state_dict", estado), strict=False)
    modelo.eval()
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, n_fft=2048, hop_length=512)
    mel = librosa.power_to_db(mel, ref=np.max)
    saidas = []
    janela = 128
    for i in range(0, max(1, mel.shape[1] - janela), janela):
        p = mel[:, i:i + janela]
        if p.shape[1] < janela:
            break
        x = torch.tensor(p)[None, None].repeat(1, 3, 1, 1).float()
        x = (x - x.mean()) / (x.std() + 1e-6)
        with torch.no_grad():
            saidas.append(torch.sigmoid(modelo(x))[0].numpy())
    if not saidas:
        return {}
    prob = np.mean(saidas, axis=0)
    return {ROTULOS_SFX[i]: round(float(prob[i]), 3) for i in range(len(ROTULOS_SFX))}


def _saturacao(y, sr):
    """Quanto de distorção: brilho dos harmônicos + fator de crista."""
    crista = float(np.max(np.abs(y)) / (np.sqrt(np.mean(y ** 2)) + 1e-9))
    achatamento = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    rolagem = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.95)))
    # som limpo tem crista alta (dinâmica) e menos energia nos agudos
    q = np.clip((6.5 - crista) / 4.0, 0, 1) * 0.6 + np.clip(rolagem / 7000.0, 0, 1) * 0.4
    q = float(np.clip(q + achatamento * 0.8, 0, 1))
    if q > 0.72:
        nome, nivel = "distorção alta (high gain)", q
    elif q > 0.5:
        nome, nivel = "distorção", q
    elif q > 0.3:
        nome, nivel = "overdrive leve", q
    else:
        nome, nivel = "som limpo", 1 - q
    return nome, round(float(nivel), 2), {"crista": round(crista, 2), "rolloff_hz": int(rolagem)}


def _reverb(y, sr):
    """Cauda de reverb: quanto a energia demora a cair depois dos ataques."""
    env = librosa.onset.onset_strength(y=y, sr=sr)
    picos = librosa.util.peak_pick(env, pre_max=6, post_max=6, pre_avg=10,
                                   post_avg=10, delta=0.4, wait=12)
    if len(picos) < 3:
        return 0.0, 0.0
    quedas = []
    for p in picos[:-1]:
        trecho = env[p:p + 40]
        if len(trecho) < 10 or trecho[0] <= 0:
            continue
        alvo = trecho[0] * 0.1
        abaixo = np.where(trecho < alvo)[0]
        if len(abaixo):
            quedas.append(abaixo[0] * 512 / sr)
    if not quedas:
        return 0.0, 0.0
    t60 = float(np.median(quedas)) * 6  # extrapola de -10 dB para -60 dB
    return round(t60, 2), round(float(np.clip((t60 - 0.25) / 2.0, 0, 1)), 2)


def _delay(y, sr, bpm):
    """Procura repetições na autocorrelação do envelope e compara com o BPM."""
    env = librosa.onset.onset_strength(y=y, sr=sr)
    env = env - env.mean()
    if len(env) < 100:
        return None
    ac = librosa.autocorrelate(env, max_size=int(2.0 * sr / 512))
    ac[: int(0.06 * sr / 512)] = 0
    if ac.max() <= 0:
        return None
    ac = ac / ac.max()
    idx = int(np.argmax(ac))
    forca = float(ac[idx])
    ms = idx * 512 / sr * 1000
    if forca < 0.25 or not (60 < ms < 1200):
        return None
    info = {"ms": int(ms), "forca": round(forca, 2)}
    if bpm:
        semin = 60000.0 / bpm / 2
        figuras = {"colcheia": semin, "colcheia pontuada": semin * 1.5,
                   "semicolcheia": semin / 2, "negra": semin * 2,
                   "quarto de tempo com tercina": semin * 2 / 3}
        nome, erro = min(((k, abs(ms - v) / v) for k, v in figuras.items()), key=lambda x: x[1])
        if erro < 0.12:
            info["figura"] = nome
    return info


def _modulacao(y, sr):
    """Chorus/tremolo/phaser: oscilação lenta no volume ou no centro espectral."""
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    cen = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    taxa_q = sr / hop
    achados = {}
    for nome, sinal in (("tremolo", rms), ("chorus/phaser", cen)):
        s = sinal - sinal.mean()
        if len(s) < 64 or s.std() < 1e-9:
            continue
        esp = np.abs(np.fft.rfft(s * np.hanning(len(s))))
        freqs = np.fft.rfftfreq(len(s), 1 / taxa_q)
        faixa = (freqs > 0.3) & (freqs < 9.0)   # Hz típicos de LFO
        if not faixa.any():
            continue
        pico = float(esp[faixa].max() / (esp[faixa].mean() + 1e-9))
        if pico > 7.0:
            achados[nome] = {"hz": round(float(freqs[faixa][np.argmax(esp[faixa])]), 2),
                             "forca": round(min(pico / 20.0, 1.0), 2)}
    return achados


def analisar(caminho, bpm=None, pesos_sfx=None, sr=SR):
    """Resumo dos efeitos: lista ordenada por confiança + medidas de apoio."""
    y = para_mono(librosa.load(str(caminho), sr=sr, mono=True)[0])
    if len(y) < sr // 2:
        return {"efeitos": [], "medidas": {}, "aviso": "faixa curta demais"}

    nome_sat, nivel_sat, m_sat = _saturacao(y, sr)
    t60, conf_rev = _reverb(y, sr)
    delay = _delay(y, sr, bpm)
    mod = _modulacao(y, sr)

    efeitos = [{"efeito": nome_sat, "confianca": nivel_sat, "como": "fator de crista e brilho"}]
    if conf_rev > 0.25:
        efeitos.append({"efeito": "reverb", "confianca": conf_rev,
                        "como": f"cauda de cerca de {t60:.1f}s", "detalhe": {"t60_s": t60}})
    if delay:
        rotulo = "delay"
        if delay.get("figura"):
            rotulo = f"delay em {delay['figura']}"
        efeitos.append({"efeito": rotulo, "confianca": delay["forca"],
                        "como": f"repetição a cada {delay['ms']} ms", "detalhe": delay})
    for nome, d in mod.items():
        efeitos.append({"efeito": nome, "confianca": d["forca"],
                        "como": f"oscilação de {d['hz']} Hz", "detalhe": d})

    if pesos_sfx:
        try:
            prob = _sfxlearner(y, pesos_sfx, sr)
            for nome, p in sorted(prob.items(), key=lambda x: -x[1])[:5]:
                if p > 0.5:
                    efeitos.append({"efeito": nome, "confianca": round(p, 2),
                                    "como": "classificador SFXlearner"})
        except Exception as e:
            efeitos.append({"efeito": "classificador indisponível", "confianca": 0.0,
                            "como": f"{e.__class__.__name__}"})

    efeitos.sort(key=lambda e: -e["confianca"])
    return {
        "efeitos": efeitos,
        "medidas": {**m_sat, "t60_s": t60, "delay": delay, "modulacao": mod},
        "aviso": "estimativa a partir do áudio já misturado; serve como ponto de partida",
    }
