"""BPM, compasso, tom e cifra de acordes."""
import numpy as np
import librosa

from .audio import para_mono, SR

NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Perfis de Krumhansl-Schmuckler (maior e menor)
PERFIL_MAIOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
PERFIL_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def bpm_e_batidas(caminho_ou_y, sr=SR):
    """BPM e tempos das batidas. Usa beat_this (estado da arte) quando disponível,
    senão o beat tracker do librosa."""
    try:
        from beat_this.inference import File2Beats  # noqa
        from . import gpu
        with gpu.uso("batidas") as dev:
            detector = File2Beats(checkpoint_path="final0", device=dev, dbn=False)
            batidas, fortes = detector(str(caminho_ou_y))
            del detector
        batidas = np.asarray(batidas, dtype=float)
        motor = "beat_this"
    except Exception:
        y = caminho_ou_y if isinstance(caminho_ou_y, np.ndarray) else librosa.load(str(caminho_ou_y), sr=sr, mono=True)[0]
        y = para_mono(y)
        _, quadros = librosa.beat.beat_track(y=y, sr=sr, units="time")
        batidas, fortes, motor = np.asarray(quadros, dtype=float), np.array([]), "librosa"

    if len(batidas) > 1:
        intervalos = np.diff(batidas)
        bpm = 60.0 / float(np.median(intervalos))
    else:
        bpm = 0.0
    # compasso pelo espaçamento das batidas fortes
    compasso = None
    if len(fortes) > 1 and len(batidas) > 1:
        passo = np.median(np.diff(fortes)) / np.median(np.diff(batidas))
        if 1.5 < passo < 8:
            compasso = f"{int(round(passo))}/4"
    return {
        "bpm": round(bpm, 1),
        "compasso": compasso,
        "batidas": [round(float(b), 3) for b in batidas],
        "fortes": [round(float(b), 3) for b in np.asarray(fortes, dtype=float)],
        "motor": motor,
    }


def _croma(y, sr=SR):
    y = para_mono(y)
    harm = librosa.effects.harmonic(y, margin=3)
    return librosa.feature.chroma_cqt(y=harm, sr=sr, bins_per_octave=36)


def tom(y, sr=SR):
    """Tom por correlação com os perfis de tonalidade, com as 3 melhores opções."""
    perfil = _croma(y, sr).mean(axis=1)
    perfil = perfil / (perfil.sum() + 1e-9)
    notas = []
    for i in range(12):
        girado = np.roll(perfil, -i)
        for modo, p in (("maior", PERFIL_MAIOR), ("menor", PERFIL_MENOR)):
            r = float(np.corrcoef(girado, p)[0, 1])
            notas.append((r, NOTAS[i], modo))
    notas.sort(reverse=True)
    melhor = notas[0]
    relativo = f"{NOTAS[(NOTAS.index(melhor[1]) + 9) % 12]}m" if melhor[2] == "maior" else \
               f"{NOTAS[(NOTAS.index(melhor[1]) + 3) % 12]}"
    return {
        "tom": f"{melhor[1]} {melhor[2]}",
        "confianca": round(max(0.0, melhor[0]), 3),
        "relativa": relativo,
        "alternativas": [f"{n} {m}" for _, n, m in notas[1:4]],
    }


# Modelos de acorde: (sufixo, intervalos em semitons)
FORMAS = [("", (0, 4, 7)), ("m", (0, 3, 7)), ("5", (0, 7)), ("7", (0, 4, 7, 10)),
          ("m7", (0, 3, 7, 10)), ("maj7", (0, 4, 7, 11)), ("sus4", (0, 5, 7)), ("dim", (0, 3, 6))]


def cifra(y, batidas, sr=SR):
    """Cifra por compasso: casa o croma médio de cada trecho com modelos de acorde."""
    if len(batidas) < 4:
        return []
    croma = _croma(y, sr)
    tempos = librosa.times_like(croma, sr=sr, hop_length=512)
    modelos = []
    for i in range(12):
        for sufixo, intervalos in FORMAS:
            v = np.zeros(12)
            for iv in intervalos:
                v[(i + iv) % 12] = 1
            modelos.append((f"{NOTAS[i]}{sufixo}", v / np.linalg.norm(v)))
    saida, grupos = [], [batidas[i:i + 4] for i in range(0, len(batidas) - 1, 4)]
    for g in grupos:
        ini, fim = float(g[0]), float(g[-1])
        faixa = (tempos >= ini) & (tempos < fim)
        if faixa.sum() < 2:
            continue
        v = croma[:, faixa].mean(axis=1)
        if np.linalg.norm(v) < 1e-6:
            continue
        v = v / np.linalg.norm(v)
        nome, pontos = max(((n, float(v @ m)) for n, m in modelos), key=lambda x: x[1])
        saida.append({"inicio": round(ini, 2), "fim": round(fim, 2),
                      "acorde": nome, "confianca": round(pontos, 3)})
    return saida


# ---------------------------------------------------------------------------
# Cifra por compasso, alinhada às batidas fortes (para acompanhar em tempo real)

# acordes usados na cifra ao vivo: tríades e tétrades comuns (menos confusão)
FORMAS_VIVO = [("", (0, 4, 7), 0.0), ("m", (0, 3, 7), 0.0),
               ("7", (0, 4, 7, 10), 0.035), ("m7", (0, 3, 7, 10), 0.035)]


def _grade_regular(batidas):
    """Deixa a grade de batidas regular: o detector às vezes pula para meio tempo
    (pulsos com o dobro do intervalo) ou gera batidas fantasmas muito juntas."""
    b = np.sort(np.asarray(batidas, dtype=float))
    d = np.diff(b)
    d = d[d > 0.15]
    if len(d) < 3:
        return list(b), float(np.median(d)) if len(d) else 0.5
    P = float(np.percentile(d, 25))
    k = np.maximum(1, np.round(d / P))
    P = float(np.median(d / k))
    grade = [float(b[0])]
    for x in b[1:]:
        n = int(round((x - grade[-1]) / P))
        if n < 1:
            continue  # batida fantasma
        passo = (x - grade[-1]) / n
        grade.extend(grade[-1] + passo * i for i in range(1, n))
        grade.append(float(x))
    return grade, P


def _compassos(batidas, fortes, duracao):
    """Agrupa as batidas em compassos de tamanho fixo, com a fase (onde cai o 1º
    tempo) escolhida pelas batidas fortes detectadas."""
    grade, P = _grade_regular(batidas)
    fortes = np.asarray(fortes, dtype=float)
    m = 4
    if len(fortes) > 2:
        m = int(np.clip(round(float(np.median(np.diff(fortes))) / P), 2, 8))
    fase = 0
    if len(fortes):
        g = np.asarray(grade)
        pontos = [sum(np.min(np.abs(fortes[:, None] - g[o::m][None, :]), axis=1) < 0.2 * P)
                  for o in range(m)]
        fase = int(np.argmax(pontos))
    compassos = []
    if fase:
        compassos.append({"inicio": grade[0], "fim": grade[fase], "batidas": grade[:fase], "anacruse": True})
    for i in range(fase, len(grade), m):
        bs = grade[i:i + m]
        fim = grade[i + m] if i + m < len(grade) else min(duracao, bs[-1] + P)
        compassos.append({"inicio": bs[0], "fim": fim, "batidas": bs})
    return compassos, m


def _diatonicos(tom_texto):
    """Acordes do campo harmônico do tom (ex.: "D maior" -> D Em F#m G A A7 Bm...)."""
    try:
        nota, modo = tom_texto.split()
        r = NOTAS.index(nota)
    except Exception:
        return None
    if modo == "menor":
        r = (r + 3) % 12  # usa a relativa maior
    acordes = set()
    for grau, qual in ((0, "M"), (2, "m"), (4, "m"), (5, "M"), (7, "M"), (9, "m")):
        n = NOTAS[(r + grau) % 12]
        acordes |= {n, f"{n}7"} if (qual == "M" and grau == 7) else ({n} if qual == "M" else {f"{n}m", f"{n}m7"})
    return acordes


def cifra_compassos(y, ritmo, sr=SR, tom_texto=None):
    """Cifra batida a batida suavizada (Viterbi) e organizada por compasso.

    Troca de acorde é mais barata no 1º tempo do compasso, depois no meio dele,
    e cara nos outros tempos, que é como a maioria das músicas se comporta.
    Devolve (compassos, cifra_linear, tempos_por_compasso).
    """
    y = para_mono(y)
    duracao = len(y) / sr
    batidas = [b for b in ritmo.get("batidas", []) if b < duracao]
    if len(batidas) < 4:
        return [], [], None
    compassos, por_compasso = _compassos(batidas, ritmo.get("fortes", []), duracao)

    # unidades de análise: cada batida (até a próxima)
    unidades = []
    for ci, c in enumerate(compassos):
        n = len(c["batidas"])
        for bi, b in enumerate(c["batidas"]):
            fim = c["batidas"][bi + 1] if bi + 1 < n else c["fim"]
            unidades.append((ci, bi, n, b, fim))

    hop = 512
    croma = _croma(y, sr)
    tempos = librosa.times_like(croma, sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_ref = float(np.median(rms[rms > 0])) if np.any(rms > 0) else 1.0

    nomes, mats, custos = [], [], []
    for i in range(12):
        for suf, ivs, custo in FORMAS_VIVO:
            v = np.zeros(12)
            for iv in ivs:
                v[(i + iv) % 12] = 1
            nomes.append(f"{NOTAS[i]}{suf}")
            mats.append(v / np.linalg.norm(v))
            custos.append(custo)
    nomes.append("N")  # sem acorde (silêncio)
    M = np.array(mats)
    custos = np.array(custos)
    campo = _diatonicos(tom_texto) if tom_texto else None
    if campo:  # acordes fora do tom precisam de mais evidência
        custos = custos + np.array([0.0 if n in campo else 0.04 for n in nomes[:-1]])

    K = 10.0
    E = np.zeros((len(unidades), len(nomes)))
    for u, (_, _, _, ini, fim) in enumerate(unidades):
        sel = (tempos >= ini) & (tempos < fim)
        if sel.sum() < 1:
            sel = np.argmin(np.abs(tempos - ini)) == np.arange(len(tempos))
        v = croma[:, sel].mean(axis=1)
        silencio = float(rms[sel[: len(rms)]].mean()) < 0.12 * rms_ref if sel[: len(rms)].any() else False
        nv = np.linalg.norm(v)
        sim = (M @ (v / nv)) - custos if nv > 1e-6 else np.zeros(len(M))
        E[u, :-1] = K * sim
        E[u, -1] = K * (0.95 if silencio else 0.2)

    # Viterbi
    S = len(nomes)
    pont = E[0].copy()
    volta = np.zeros((len(unidades), S), dtype=int)
    for u in range(1, len(unidades)):
        _, bi, n, _, _ = unidades[u]
        if bi == 0:
            pena = 1.2
        elif n % 2 == 0 and bi == n // 2:
            pena = 2.2
        else:
            pena = 4.0
        melhor = int(np.argmax(pont))
        trocar = pont[melhor] - pena
        volta[u] = np.where(pont >= trocar, np.arange(S), melhor)
        pont = np.maximum(pont, trocar) + E[u]
    caminho = [int(np.argmax(pont))]
    for u in range(len(unidades) - 1, 0, -1):
        caminho.append(int(volta[u, caminho[-1]]))
    caminho.reverse()

    # monta os compassos com os acordes de cada um (só onde o acorde muda)
    saida = [{"n": i + (0 if compassos[0].get("anacruse") else 1),
              "inicio": round(c["inicio"], 3), "fim": round(c["fim"], 3),
              "batidas": [round(b, 3) for b in c["batidas"]], "acordes": []}
             for i, c in enumerate(compassos)]
    anterior = None
    for u, (ci, bi, _, ini, _) in enumerate(unidades):
        nome = nomes[caminho[u]]
        # no 1º tempo sempre escreve o acorde (como "| G | G |" numa cifra)
        if bi == 0 or nome != anterior:
            saida[ci]["acordes"].append({"acorde": nome, "batida": bi, "inicio": round(ini, 3)})
        anterior = nome

    linear = []
    for c in saida:
        for a in c["acordes"]:
            if linear and linear[-1]["acorde"] == a["acorde"]:
                continue
            if linear:
                linear[-1]["fim"] = a["inicio"]
            linear.append({"inicio": a["inicio"], "fim": c["fim"], "acorde": a["acorde"]})
    if linear:
        linear[-1]["fim"] = saida[-1]["fim"]
    linear = [x for x in linear if x["acorde"] != "N"]
    return saida, linear, por_compasso
