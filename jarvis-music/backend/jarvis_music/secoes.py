"""Seções da música (intro, verso, pré-refrão, refrão, ponte, solo, final).

Trabalha compasso a compasso, em cima dos compassos reais da cifra:
1. Características de cada compasso: harmonia (croma), timbre (MFCC), acordes e
   a energia de cada faixa separada (voz, guitarra, bateria, baixo...).
2. Fronteiras: mudança brusca nessas características (novidade numa matriz de
   auto-similaridade), entrada/saída da voz e preferência por frases de 4/8 compassos.
3. Rótulos: trechos parecidos viram o mesmo grupo (A, B, C...). Daí os nomes:
   o grupo cantado que mais se repete e tem mais energia é o refrão; o cantado
   que vem antes dele é o verso; o cantado que só aparece uma vez no fim é a
   ponte; partes sem voz são intro, solo, instrumental ou final.
É uma estimativa: a interface deixa renomear cada parte.
"""
from pathlib import Path

import librosa
import numpy as np

from .audio import SR, carregar, para_mono

CORES = {"Intro": "intro", "Verso": "verso", "Pré-refrão": "pre", "Refrão": "refrao", "Ponte": "ponte",
         "Solo": "solo", "Instrumental": "inst", "Final": "final", "Parte": "parte"}
STEMS = ("voz", "guitarra", "bateria", "baixo", "piano", "outros")


def _por_compasso(matriz, tempos, compassos):
    """média de cada coluna da matriz (características x quadros) dentro de cada compasso"""
    saida = []
    for c in compassos:
        sel = (tempos >= c["inicio"]) & (tempos < c["fim"])
        saida.append(matriz[:, sel].mean(axis=1) if sel.any() else np.zeros(matriz.shape[0]))
    return np.array(saida)


def _energias(dir_analise, compassos):
    hop = 2048
    e = {}
    for st in STEMS:
        p = Path(dir_analise) / f"{st}.wav"
        if not p.exists():
            continue
        y = para_mono(carregar(p))
        rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
        t = librosa.times_like(rms, sr=SR, hop_length=hop)
        v = _por_compasso(rms[None, :], t, compassos)[:, 0]
        ref = float(np.percentile(v, 90)) or 1.0
        e[st] = np.clip(v / ref, 0, 1.5)
    return e


def _novidade(S, largura=4):
    """novidade de Foote: kernel xadrez gaussiano ao longo da diagonal"""
    n = len(S)
    L = largura
    g = np.exp(-0.5 * ((np.arange(-L, L) + 0.5) / (L * 0.6)) ** 2)
    K = np.outer(g, g) * np.outer(np.sign(np.arange(-L, L) + 0.5), np.sign(np.arange(-L, L) + 0.5))
    P = np.pad(S, L, mode="edge")
    nov = np.array([np.sum(P[i:i + 2 * L, i:i + 2 * L] * K) for i in range(n)])
    nov = np.maximum(nov, 0)
    return nov / (nov.max() or 1)


def _fronteiras(nov, voz_on, n, minimo=4):
    """escolhe onde as seções começam: picos de novidade, entrada/saída da voz e frases de 4"""
    pontos = nov.copy()
    # entrada ou saída da voz é fronteira forte
    for i in range(1, n):
        if voz_on[i] != voz_on[i - 1]:
            pontos[i] += 0.6
    # música popular anda em frases de 4/8 compassos: fronteira fora da frase precisa ser mais forte
    frase = np.array([1.3 if i % 8 == 0 else 1.15 if i % 4 == 0 else 0.95 if i % 2 == 0 else 0.75 for i in range(n)])
    pontos = pontos * frase
    escolhidas = [0]
    candidatos = sorted(range(1, n), key=lambda i: -pontos[i])
    for i in candidatos:
        if pontos[i] < 0.25:
            break
        if all(abs(i - j) >= minimo for j in escolhidas) and n - i >= 2:
            escolhidas.append(i)
    escolhidas.sort()
    # puxa cada fronteira para a frase de 4 compassos mais próxima (se não perder força)
    ajustadas = [0]
    for b in escolhidas[1:]:
        ant = ajustadas[-1]
        melhor = b
        for d in (-1, 1, -2, 2):
            c = b + d
            if 0 < c < n and (c - ant) % 4 == 0 and (b - ant) % 4 != 0 and pontos[c] >= 0.6 * pontos[b]:
                melhor = c
                break
        if melhor - ant >= 2:
            ajustadas.append(melhor)
    return ajustadas


def _sim_trechos(F, a, b):
    """similaridade entre dois trechos (sequências de compassos) por DTW sobre o cosseno"""
    A, B = F[a[0]:a[1]], F[b[0]:b[1]]
    C = 1 - A @ B.T
    D = librosa.sequence.dtw(C=C, subseq=False)[0]
    return 1 - D[-1, -1] / (len(A) + len(B))


def detectar(dir_analise, compassos, mono=None):
    """Devolve [{inicio, fim, k_ini, k_fim, nome, grupo, cor, vocal}] (k = índice do compasso)."""
    compassos = [c for c in compassos if c["fim"] > c["inicio"]]
    n = len(compassos)
    if n < 6:
        return []
    if mono is None:
        orig = sorted(Path(dir_analise).glob("original.*"))
        mono = para_mono(carregar(orig[0]))

    hop = 1024
    harm = librosa.effects.harmonic(mono, margin=2)
    croma = librosa.feature.chroma_cqt(y=harm, sr=SR, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=mono, sr=SR, n_mfcc=14, hop_length=hop)[1:]
    t = librosa.times_like(croma, sr=SR, hop_length=hop)
    Cb = _por_compasso(croma, t, compassos)
    Mb = _por_compasso(mfcc, t, compassos)
    Cb = Cb / (np.linalg.norm(Cb, axis=1, keepdims=True) + 1e-9)
    Mb = (Mb - Mb.mean(0)) / (Mb.std(0) + 1e-9)
    Mb = Mb / (np.linalg.norm(Mb, axis=1, keepdims=True) + 1e-9)
    en = _energias(dir_analise, compassos)
    voz = en.get("voz", np.zeros(n))
    voz_on = voz > 0.25
    total = np.mean([v for v in en.values()], axis=0) if en else np.ones(n)
    Eb = np.stack([en.get(s, np.zeros(n)) for s in STEMS], 1)
    Eb = Eb / (np.linalg.norm(Eb, axis=1, keepdims=True) + 1e-9)

    F = np.hstack([Cb * 1.0, Mb * 0.8, Eb * 0.7])
    F = F / (np.linalg.norm(F, axis=1, keepdims=True) + 1e-9)
    S = F @ F.T
    nov = _novidade(S, largura=4)
    fr = _fronteiras(nov, voz_on, n)
    trechos = [(fr[i], fr[i + 1] if i + 1 < len(fr) else n) for i in range(len(fr))]

    # agrupa trechos parecidos (harmonia pesa mais que timbre)
    G = np.hstack([Cb * 1.0, Mb * 0.5])
    G = G / (np.linalg.norm(G, axis=1, keepdims=True) + 1e-9)
    grupos = [-1] * len(trechos)
    prox = 0
    for i, a in enumerate(trechos):
        if grupos[i] >= 0:
            continue
        grupos[i] = prox
        for j in range(i + 1, len(trechos)):
            if grupos[j] >= 0:
                continue
            b = trechos[j]
            mesmo_canto = abs(float(voz[a[0]:a[1]].mean()) - float(voz[b[0]:b[1]].mean())) < 0.35
            if mesmo_canto and _sim_trechos(G, a, b) > 0.82:
                grupos[j] = prox
        prox += 1

    info = []
    for (a, b), g in zip(trechos, grupos):
        info.append({"a": a, "b": b, "g": g, "vocal": float(voz[a:b].mean()) > 0.3,
                     "energia": float(total[a:b].mean()), "guitarra": float(en.get("guitarra", np.zeros(n))[a:b].mean())})

    # nomes
    vocais = {}
    for k, s in enumerate(info):
        if s["vocal"]:
            vocais.setdefault(s["g"], []).append(k)
    refrao = None
    if vocais:
        refrao = max(vocais, key=lambda g: (len(vocais[g]) >= 2) * 2 + np.mean([info[k]["energia"] for k in vocais[g]])
                     + 0.15 * len(vocais[g]))
    primeiro_refrao = min(vocais[refrao]) if refrao is not None else len(info)
    nomes = [None] * len(info)
    for k, s in enumerate(info):
        if s["vocal"]:
            if s["g"] == refrao:
                nomes[k] = "Refrão"
            elif k + 1 < len(info) and info[k + 1]["g"] == refrao and (s["b"] - s["a"]) <= 4 and k > 0 \
                    and nomes[k - 1] != "Refrão":
                nomes[k] = "Pré-refrão"
            elif k < primeiro_refrao or len(vocais.get(s["g"], [])) >= 2:
                nomes[k] = "Verso"
            elif k > primeiro_refrao:
                nomes[k] = "Ponte"
            else:
                nomes[k] = "Parte"
        else:
            if k == 0:
                nomes[k] = "Intro"
            elif k == len(info) - 1:
                nomes[k] = "Final"
            elif s["guitarra"] > 0.6 and s["energia"] > 0.45:
                nomes[k] = "Solo"
            else:
                nomes[k] = "Instrumental"
    # "Verso" de grupos diferentes: o segundo grupo de verso que vem logo antes do refrão vira pré-refrão
    contagem, saida = {}, []
    repetidos = {nm for nm in nomes if nomes.count(nm) > 1 and nm not in ("Intro", "Final")}
    for k, s in enumerate(info):
        nm = nomes[k]
        contagem[nm] = contagem.get(nm, 0) + 1
        rotulo = f"{nm} {contagem[nm]}" if nm in repetidos else nm
        c0, c1 = compassos[s["a"]], compassos[s["b"] - 1]
        saida.append({"inicio": round(c0["inicio"], 3), "fim": round(c1["fim"], 3), "k_ini": s["a"], "k_fim": s["b"],
                      "nome": rotulo, "tipo": nm, "grupo": "ABCDEFGHIJKLMNOP"[s["g"] % 16],
                      "cor": CORES.get(nm, "parte"), "vocal": s["vocal"]})
    return saida
