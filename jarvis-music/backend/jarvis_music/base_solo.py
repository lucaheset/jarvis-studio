"""Guitarra base x guitarra solo quando as duas estão no centro do estéreo.

A divisão por panorama (separacao.dividir_por_panorama) só funciona quando as
guitarras foram gravadas abertas para os lados. Aqui a separação é guiada pelas
notas que o transcritor já tirou, tudo na CPU:

1. rotular(): cada nota vira base ou solo. Acordes (várias notas no mesmo
   ataque) e dedilhado que fica soando são base; a linha de uma nota por vez
   acima da região dos acordes é o solo. Notas vizinhas da mesma frase herdam
   o papel umas das outras.
2. separar(): para cada nota, os harmônicos dela no espectrograma vão para a
   máscara do seu papel. Onde só uma das partes toca, o resto do som (ataque,
   ruído) vai junto. As duas faixas somadas dão exatamente a guitarra original.

Funciona bem quando as partes tocam em regiões diferentes do braço; onde as
duas tocam a mesma nota ao mesmo tempo, uma vaza na outra.
"""
from bisect import bisect_left, bisect_right
from pathlib import Path

import numpy as np
import soundfile as sf

AGRUPAR = 0.045      # ataques mais próximos que isso são o mesmo acorde
JANELA_ACORDE = 1.5  # quanto olhar em volta para saber a altura dos acordes
N_FFT, HOP = 4096, 1024


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# --------------------------------------------------------------- 1. rótulos
def rotular(notas):
    """Põe n["papel_bs"] = "base" | "solo" em cada nota (não mexe em n["papel"])."""
    if not notas:
        return notas
    ordem = sorted(range(len(notas)), key=lambda i: notas[i]["inicio"])
    ns = [notas[i] for i in ordem]
    ini = np.array([n["inicio"] for n in ns])
    fim = np.array([n["fim"] for n in ns])
    midi = np.array([n["midi"] for n in ns])

    # grupos de ataque (acordes)
    grupo = np.zeros(len(ns), int)
    tam = {}
    g, ini_g = 0, ini[0]
    for i in range(len(ns)):
        if ini[i] - ini_g > AGRUPAR:
            g += 1
            ini_g = ini[i]
        grupo[i] = g
        tam[g] = tam.get(g, 0) + 1

    # nota do solo que cai junto com a palhetada entra no mesmo "acorde": ela fica
    # bem acima do resto do grupo. Separa: topo do grupo com salto >= 6 semitons.
    destacada = np.zeros(len(ns), bool)
    membros = {}
    for i in range(len(ns)):
        membros.setdefault(grupo[i], []).append(i)
    for gg, sel in membros.items():
        if len(sel) >= 3:
            alt = sorted(sel, key=lambda j: midi[j])
            if midi[alt[-1]] - midi[alt[-2]] >= 6:
                destacada[alt[-1]] = True

    # topo de cada acorde (3+ notas no mesmo ataque, sem a nota destacada)
    acordes_t, acordes_topo = [], []
    for gg, sel in membros.items():
        corpo = [j for j in sel if not destacada[j]]
        if len(corpo) >= 3:
            acordes_t.append(float(ini[corpo].min()))
            acordes_topo.append(float(midi[corpo].max()))
    ordem_ac = np.argsort(acordes_t)
    acordes_t = np.array(acordes_t)[ordem_ac]
    acordes_topo = np.array(acordes_topo)[ordem_ac]

    def teto(t):
        """nota mais aguda dos acordes em volta de t (None se não há acordes perto)"""
        a = bisect_left(acordes_t, t - JANELA_ACORDE)
        b = bisect_right(acordes_t, t + JANELA_ACORDE)
        return float(np.percentile(acordes_topo[a:b], 75)) if b > a else None

    corpo_tam = np.array([sum(1 for j in membros[grupo[i]] if not destacada[j]) for i in range(len(ns))])
    soltas = np.array([i for i in range(len(ns)) if destacada[i] or corpo_tam[i] <= 2])
    papel = np.array(["base"] * len(ns), dtype=object)
    for i in soltas:
        if not destacada[i] and corpo_tam[i] == 2:
            par = [j for j in membros[grupo[i]] if j != i][0]
            if midi[i] <= midi[par]:
                continue  # nota de baixo de um par fica na base
        t = ini[i]
        c = teto(t)
        if c is not None:
            if midi[i] >= c + 2:
                papel[i] = "solo"
            continue
        # sem acordes por perto: dedilhado (notas que ficam soando umas por cima das
        # outras, região média) ou solo (uma de cada vez, região aguda)
        a = bisect_left(ini, t - 1.0)
        b = bisect_right(ini, t + 1.0)
        viz = [j for j in range(a, b) if destacada[j] or corpo_tam[j] <= 2]
        soando = []
        for j in viz:
            k0 = bisect_left(ini, ini[j] - 2.0)
            soando.append(sum(1 for q in range(k0, j) if fim[q] > ini[j] + 0.03))
        poli = float(np.mean(soando)) if soando else 0.0
        altura = float(np.median(midi[viz])) if viz else float(midi[i])
        if poli < 1.3 and altura >= 59:
            papel[i] = "solo"

    # frases: nota cercada por notas do outro papel, perto no tempo e na altura, muda de lado
    for _ in range(2):
        for idx, i in enumerate(soltas):
            ant = soltas[idx - 1] if idx > 0 else None
            pro = soltas[idx + 1] if idx + 1 < len(soltas) else None
            if ant is None or pro is None:
                continue
            if ini[i] - ini[ant] > 0.45 or ini[pro] - ini[i] > 0.45:
                continue
            if papel[ant] == papel[pro] != papel[i] and abs(midi[i] - midi[ant]) <= 7 and abs(midi[i] - midi[pro]) <= 7:
                papel[i] = papel[ant]

    for i, n in enumerate(ns):
        n["papel_bs"] = papel[i]
    return notas


# --------------------------------------------------------------- 2. áudio
def _mascaras(notas, n_bins, n_quadros, sr):
    df = sr / N_FFT
    qs = HOP / sr
    M = {"base": np.zeros((n_bins, n_quadros), np.float32), "solo": np.zeros((n_bins, n_quadros), np.float32)}
    ativ = {"base": np.zeros(n_quadros, np.float32), "solo": np.zeros(n_quadros, np.float32)}
    teto_hz = min(11000.0, sr / 2 - 2 * df)
    for n in notas:
        p = n.get("papel_bs", "base")
        q0 = max(0, int((n["inicio"] - 0.03) / qs))
        q1 = min(n_quadros, int((n["fim"] + 0.12) / qs) + 1)
        if q1 <= q0:
            continue
        # envelope: cheio durante a nota, cai depois do fim
        tq = (np.arange(q0, q1) * qs) - n["fim"]
        env = np.where(tq <= 0, 1.0, np.exp(-tq / 0.06)).astype(np.float32)
        ativ[p][q0:q1] += env
        f0 = _hz(n["midi"])
        sobe = 1.0 + (0.12 if n.get("bends") or "bend" in " ".join(n.get("tecnicas") or []) else 0.0)
        alvo = M[p]
        for h in range(1, 64):
            fh = h * f0 * np.sqrt(1 + 0.0003 * h * h)  # corda de aço: harmônicos um pouco acima
            if fh > teto_hz:
                break
            c = fh / df
            sig = max(1.2, fh * 0.015 / df)
            k0 = max(0, int(c - 3 * sig))
            k1 = min(n_bins, int(c * sobe + 3 * sig) + 1)
            if k1 <= k0:
                continue
            k = np.arange(k0, k1)
            g = np.where(k < c, np.exp(-0.5 * ((k - c) / sig) ** 2),
                         np.where(k <= c * sobe, 1.0, np.exp(-0.5 * ((k - c * sobe) / sig) ** 2)))
            g = (g * h ** -0.6).astype(np.float32)
            bloco = alvo[k0:k1, q0:q1]
            np.maximum(bloco, np.outer(g, env), out=bloco)
    return M, ativ


def separar(caminho, notas, saida):
    """Escreve guitarra_base.wav e guitarra_solo.wav em `saida`. Devolve {id: caminho}."""
    import librosa

    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    y, sr = sf.read(str(caminho), dtype="float32", always_2d=True)
    y = y.T
    n_quadros = 1 + y.shape[1] // HOP
    M, ativ = _mascaras(notas, N_FFT // 2 + 1, n_quadros, sr)

    # onde nenhuma nota explica o som, vai para a parte que está tocando naquele instante
    k = np.ones(5, np.float32) / 5
    a_s = np.convolve(ativ["solo"], k, "same")
    a_b = np.convolve(ativ["base"], k, "same")
    resto_solo = a_s / (a_s + a_b + 1e-3)
    ws, wb = M["solo"] ** 2, M["base"] ** 2
    eps = np.float32(1e-2)
    mascara = (ws + eps * resto_solo[None, :]) / (ws + wb + eps)
    del ws, wb, M

    partes = {"guitarra_base": [], "guitarra_solo": []}
    for canal in y:
        X = librosa.stft(canal, n_fft=N_FFT, hop_length=HOP)
        q = min(X.shape[1], mascara.shape[1])
        S = X.copy()
        S[:, :q] *= mascara[:, :q]
        S[:, q:] *= resto_solo[-1] if len(resto_solo) else 0
        solo = librosa.istft(S, hop_length=HOP, length=len(canal))
        partes["guitarra_solo"].append(solo)
        partes["guitarra_base"].append(canal - solo)  # as duas somadas = original
    total = float(np.sum(y ** 2)) + 1e-12
    saidas = {}
    for nome, canais in partes.items():
        z = np.stack(canais)
        destino = saida / f"{nome}.wav"
        sf.write(str(destino), z.T, sr, subtype="PCM_16")
        saidas[nome] = {"caminho": destino, "fracao": round(float(np.sum(z ** 2)) / total, 3)}
    return saidas


def dividir(caminho_guitarra, notas, saida, minimo_solo=0.04):
    """Rotula as notas e separa. Devolve {} se não houver solo de verdade na música."""
    notas = [dict(n) for n in notas if n.get("midi") is not None]
    rotular(notas)
    n_solo = sum(1 for n in notas if n["papel_bs"] == "solo")
    if n_solo < max(8, minimo_solo * len(notas)):
        return {}
    return separar(caminho_guitarra, notas, saida)
