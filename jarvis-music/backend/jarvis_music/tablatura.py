"""Áudio de guitarra -> notas -> tablatura.

1. Notas: transcritor de guitarra (Basic Pitch por padrão; usa um modelo
   específico de guitarra quando estiver instalado).
2. Corda/casa: programação dinâmica que minimiza o esforço da mão
   (nos moldes do baseline A* do artigo do Fretting-Transformer).
3. Técnicas: bend, slide, vibrato e hammer-on/pull-off pela curva de pitch.
"""
import numpy as np
import librosa

from .audio import para_mono, SR

NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Afinações: MIDI da 6ª para a 1ª corda
AFINACOES = {
    "E padrão": [40, 45, 50, 55, 59, 64],
    "Eb (meio tom abaixo)": [39, 44, 49, 54, 58, 63],
    "D (um tom abaixo)": [38, 43, 48, 53, 57, 62],
    "Drop D": [38, 45, 50, 55, 59, 64],
    "Drop C": [36, 43, 48, 53, 57, 62],
    "Drop C#": [37, 44, 49, 54, 58, 63],
    "C# padrão": [37, 42, 47, 52, 56, 61],
    "Drop B": [35, 42, 47, 52, 56, 61],
}

MAX_CASA = 22


def nome_nota(midi):
    return f"{NOTAS[int(midi) % 12]}{int(midi) // 12 - 1}"


# ---------------------------------------------------------------- transcrição
_MODELOS = {}


def _descarregar():
    _MODELOS.clear()


def _registrar():
    from . import gpu
    gpu.ao_liberar(_descarregar)


_registrar()

# checkpoints de guitarra de Riley et al. (CRNN de alta resolução, licença MIT)
CHECKPOINTS = {"gaps": "guitar-gaps.pth", "fl": "guitar-fl.pth"}


def _crnn(nome, limiar_onset):
    """Carrega (uma vez) o transcritor de guitarra de alta resolução."""
    chave = (nome, round(limiar_onset, 3))
    if chave not in _MODELOS:
        from huggingface_hub import hf_hub_download
        from piano_transcription_inference import PianoTranscription
        from . import gpu
        ckpt = hf_hub_download("xavriley/midi-transcription-models", CHECKPOINTS[nome])
        # lotes pequenos: a placa fica livre para a tela entre um lote e outro
        _MODELOS[chave] = PianoTranscription(
            "Regress_onset_offset_frame_velocity_CRNN", checkpoint_path=ckpt, device=gpu.dispositivo(),
            segment_samples=10 * 16000, batch_size=2, onset_threshold=limiar_onset,
            offset_threshold=0.3, frame_threshold=0.1)
    return _MODELOS[chave]


def _transcrever_crnn(caminho, nome, sensibilidade):
    import contextlib, io
    y, _ = librosa.load(str(caminho), sr=16000, mono=True)
    limiar = float(np.clip(0.15 + 0.3 * sensibilidade, 0.1, 0.5))  # 0.5 -> 0.30 (padrão do modelo)
    from . import gpu
    with gpu.uso("tablatura"):
        modelo = _crnn(nome, limiar)
        with contextlib.redirect_stdout(io.StringIO()):
            saida = modelo.transcribe(y, None)
    notas = []
    for e in saida["est_note_events"]:
        ini, fim = float(e["onset_time"]), float(e["offset_time"])
        notas.append({"inicio": round(ini, 4), "fim": round(max(fim, ini + 0.03), 4),
                      "midi": int(e["midi_note"]), "forca": round(float(e["velocity"]) / 127, 3),
                      "bends": []})
    return notas


def _transcrever_basic_pitch(caminho, sensibilidade):
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    _, _, eventos = predict(
        str(caminho), ICASSP_2022_MODEL_PATH,
        onset_threshold=sensibilidade, frame_threshold=0.3,
        minimum_note_length=60,          # guitarra toca notas curtas
        minimum_frequency=70.0,          # abaixo da 6ª corda em Drop B
        maximum_frequency=1400.0,        # acima da 1ª corda na casa 22
        multiple_pitch_bends=False, melodia_trick=True,
    )
    return [{"inicio": round(float(i), 4), "fim": round(float(f), 4),
             "midi": int(p), "forca": round(float(a), 3),
             "bends": [int(b) for b in (bd or [])]}
            for i, f, p, a, bd in eventos]


def transcrever(caminho, sensibilidade=0.5, motor="auto"):
    """Retorna notas [{inicio, fim, midi, forca, bends}] ordenadas no tempo.

    motor: "fl" (padrão: CRNN de guitarra de alta resolução de Riley et al.), "gaps", ou
    "basic_pitch" (reserva, se o modelo de guitarra não estiver disponível).
    """
    if motor == "auto":
        motor = "fl"  # melhor no GuitarSet: F1 de nota 0,90 (gaps 0,86; basic-pitch 0,77)
    if motor in CHECKPOINTS:
        try:
            notas = _transcrever_crnn(caminho, motor, sensibilidade)
        except Exception:
            notas = _transcrever_basic_pitch(caminho, sensibilidade)
    else:
        notas = _transcrever_basic_pitch(caminho, sensibilidade)
    notas = [n for n in notas if 35 <= n["midi"] <= 92]  # fora do alcance da guitarra
    notas.sort(key=lambda n: (n["inicio"], n["midi"]))
    return limpar_harmonicos(notas)


HARMONICOS = {12, 19, 24, 28, 31, 7, 16}


def limpar_harmonicos(notas, janela=0.06, razao=0.62):
    """Remove notas fantasmas: harmônicos que o transcritor ouve como nota nova.

    Descarta uma nota quando ela começa junto de outra mais forte e está a um
    intervalo de harmônico acima dela (oitava, quinta, dupla oitava...), com
    amplitude bem menor.
    """
    fora = set()
    for i, n in enumerate(notas):
        for j in range(i + 1, len(notas)):
            m = notas[j]
            if m["inicio"] - n["inicio"] > janela:
                break
            forte, fraca = (n, m) if n["forca"] >= m["forca"] else (m, n)
            d = fraca["midi"] - forte["midi"]
            if d in HARMONICOS and fraca["forca"] < forte["forca"] * razao:
                fora.add(id(fraca))
    return [n for n in notas if id(n) not in fora]


# ------------------------------------------------------------------ afinação
def detectar_afinacao(notas):
    """Afinação padrão, a menos que haja notas abaixo do Mi grave (E2).

    Só dá para concluir que a guitarra está afinada mais grave quando aparecem
    notas que não existem na afinação padrão; nesse caso escolhe a afinação
    mais próxima da padrão que torna essas notas possíveis.
    Devolve (nome, confiança 0..1).
    """
    if not notas:
        return "E padrão", 0.0
    alturas = np.array([n["midi"] for n in notas])
    graves = alturas < 40
    if graves.mean() < 0.003:
        return "E padrão", round(float(1 - graves.mean() * 100), 2)
    ordem = ["Drop D", "D (um tom abaixo)", "Drop C#", "C# padrão", "Drop C", "Drop B"]
    for nome in ordem:
        base = AFINACOES[nome][0]
        fora = float(np.mean(alturas < base))
        if fora < 0.003:
            usadas = float(np.mean(alturas[graves] == base)) if graves.any() else 0.0
            return nome, round(float(np.clip(0.5 + usadas / 2, 0, 1)), 2)
    return "Drop B", 0.3


# --------------------------------------------------------- técnicas por nota
def marcar_ligados(notas):
    """Hammer-on, pull-off e slide: nota seguinte na MESMA corda, sem novo ataque
    (começa colada no fim da anterior) e sem outra nota no meio."""
    por_corda = {}
    for n in sorted(notas, key=lambda x: x["inicio"]):
        if "corda" not in n:
            continue
        ant = por_corda.get(n["corda"])
        if ant is not None and 0 <= n["inicio"] - ant["fim"] < 0.04 and n["inicio"] - ant["inicio"] < 0.6:
            juntas = [m for m in notas if abs(m["inicio"] - n["inicio"]) < 0.035 and m is not n]
            if not juntas:  # num acorde não é ligado
                d = n["casa"] - ant["casa"]
                t = "slide" if abs(d) >= 3 else "hammer-on" if d > 0 else "pull-off" if d < 0 else None
                if t:
                    ant.setdefault("tecnicas", [])
                    if t not in ant["tecnicas"]:
                        ant["tecnicas"].append(t)
        por_corda[n["corda"]] = n
    return notas


def detectar_tecnicas(caminho, notas, sr=SR):
    """Marca bend e vibrato (só em notas soltas)."""
    y = para_mono(librosa.load(str(caminho), sr=sr, mono=True)[0])
    hop = 256
    try:
        f0, voz, _ = librosa.pyin(y, fmin=70, fmax=1400, sr=sr, hop_length=hop,
                                  frame_length=2048, fill_na=np.nan)
    except Exception:
        return notas
    tempos = librosa.times_like(f0, sr=sr, hop_length=hop)
    semi = 12 * np.log2(np.where(np.isfinite(f0) & (f0 > 0), f0, np.nan) / 440.0) + 69

    for k, n in enumerate(notas):
        dur = max(1e-3, n["fim"] - n["inicio"])
        # curva de pitch só faz sentido com uma nota soando: num acorde o pitch é de todas
        sobreposto = sum(max(0.0, min(n["fim"], m["fim"]) - max(n["inicio"], m["inicio"]))
                         for m in notas[max(0, k - 8):k + 8] if m is not n)
        if sobreposto > 0.25 * dur:
            n["tecnicas"] = []
            continue
        faixa = (tempos >= n["inicio"]) & (tempos <= n["fim"])
        curva = semi[faixa]
        curva = curva[np.isfinite(curva)]
        tecnicas = []
        if len(curva) >= 6:
            desvio = curva - np.median(curva[: max(2, len(curva) // 5)])
            subida = float(np.max(desvio))
            # bend: sobe e fica; tem de subir pelo menos meio tom
            if subida > 0.65 and float(np.mean(desvio[-len(desvio) // 3:])) > 0.45:
                tecnicas.append("bend" if subida < 2.6 else "bend 1 tom+")
            # vibrato: oscilação periódica de pequena amplitude
            if n["fim"] - n["inicio"] > 0.18 and len(curva) > 16:
                osc = curva - np.convolve(curva, np.ones(7) / 7, mode="same")
                miolo = osc[4:-4]
                if len(miolo) > 8 and 0.14 < float(np.std(miolo)) < 0.55:
                    cruz = int(np.sum(np.diff(np.sign(miolo)) != 0))
                    # vibrato de verdade: 4 a 9 Hz, ou seja várias oscilações completas
                    if cruz >= 8 and cruz <= len(miolo) // 2:
                        tecnicas.append("vibrato")
        n["tecnicas"] = tecnicas
    return notas


# -------------------------------------------------- base x solo (por trecho)
def classificar_base_solo(notas, bpm=120.0, janela=2.0):
    """Marca cada nota como 'base' ou 'solo', em janelas de 2 s.

    O que mais separa os dois é quantas notas soam ao mesmo tempo: na base
    (acordes, dedilhado) várias; no solo, uma de cada vez. Ajuda também a
    região do braço e quantas notas cada ataque tem. Calibrado no GuitarSet
    (gravações rotuladas como acompanhamento ou solo): 96% das janelas certas.
    Devolve também os trechos, para a interface poder corrigir.
    """
    if not notas:
        return [], []
    fim = max(n["fim"] for n in notas)
    trechos, t = [], 0.0
    while t < fim:
        bloco = [n for n in notas if n["inicio"] < t + janela and n["fim"] > t]
        if bloco:
            grade = np.arange(t, t + janela, 0.02)
            ativos = np.array([sum(1 for n in bloco if n["inicio"] <= g < n["fim"]) for g in grade])
            soando = ativos[ativos > 0]
            uma_so = float(np.mean(soando == 1)) if len(soando) else 1.0
            inicios = np.array(sorted(n["inicio"] for n in bloco))
            ataques = len(inicios) - int(np.sum(np.diff(inicios) < 0.06))
            por_ataque = len(bloco) / max(1, ataques)
            media = float(np.mean([n["midi"] for n in bloco]))
            pontos = 3 * (uma_so - 0.5) + (media - 60) / 8 - (por_ataque - 1.5)
            papel = "solo" if pontos > -0.75 else "base"
            trechos.append({"inicio": round(t, 2), "fim": round(min(t + janela, fim), 2),
                            "papel": papel, "pontos": round(float(pontos), 2)})
        t += janela

    # suaviza trechos isolados (um bloco solto entre dois iguais)
    for i in range(1, len(trechos) - 1):
        if trechos[i - 1]["papel"] == trechos[i + 1]["papel"] != trechos[i]["papel"]:
            trechos[i]["papel"] = trechos[i - 1]["papel"]

    for n in notas:
        achou = next((s for s in trechos if s["inicio"] <= n["inicio"] < s["fim"]), None)
        n["papel"] = achou["papel"] if achou else "base"
    return notas, trechos


# ------------------------------------------------------- corda/casa (Viterbi)
# Pesos ajustados no GuitarSet (treino: guitarristas 00-02; teste: 03-05).
# Acerto de corda com as notas certas: 71% nos guitarristas de teste
# (a versão anterior acertava 52%).
PESOS = {"trans": 2.5, "prior": 2.0, "span": 2.0, "dedos": 2.0,
         "mov": 0.6, "mov2": 2.0, "corda": 0.5, "tempo": 1.0}
_PRIOR = None


def _prior():
    """Estatística de qual corda guitarristas usam para cada altura, e de como
    pulam de corda entre notas seguidas (aprendida do GuitarSet)."""
    global _PRIOR
    if _PRIOR is None:
        import json
        from pathlib import Path
        d = json.loads((Path(__file__).parent / "prior_cordas.json").read_text(encoding="utf-8"))
        _PRIOR = {
            "por_altura": {int(k): {int(c): v for c, v in x.items()} for k, x in d["por_altura"].items()},
            "trans": {int(k): {int(c): v for c, v in x.items()} for k, x in d["trans"].items()},
        }
    return _PRIOR


def _custo_corda(prior, rel, corda):
    c = prior["por_altura"].get(rel)
    tot = sum(c.values()) if c else 0
    p = ((c.get(corda, 0) if c else 0) + 0.5) / (tot + 3.0) if tot else 1 / 3
    return -PESOS["prior"] * np.log(p)


def atribuir_cordas(notas, afinacao="E padrão", janela=0.035):
    """Escolhe corda e casa de cada nota com Viterbi sobre todo o trecho.

    Custos: corda mais usada para aquela altura, salto de corda típico entre
    notas seguidas, deslocamento da mão (menor quando há pausa), abertura do
    acorde e número de dedos. Notas simultâneas são resolvidas juntas, uma por corda.
    """
    if not notas:
        return notas
    cordas = AFINACOES.get(afinacao, AFINACOES["E padrão"])
    prior, w = _prior(), PESOS
    notas.sort(key=lambda n: (n["inicio"], n["midi"]))

    eventos, atual = [], [0]
    for i in range(1, len(notas)):
        if notas[i]["inicio"] - notas[atual[0]]["inicio"] < janela:
            atual.append(i)
        else:
            eventos.append(atual)
            atual = [i]
    eventos.append(atual)

    def posicoes(midi):
        return [(6 - s, midi - b) for s, b in enumerate(cordas) if 0 <= midi - b <= MAX_CASA]

    def combos(ev):
        ls = [posicoes(notas[i]["midi"]) for i in ev]
        ls = [l for l in ls if l] or [[(1, 0)]]
        ev_validos = [i for i in ev if posicoes(notas[i]["midi"])] or ev[:1]
        if len(ev_validos) > 6:  # mais de 6 notas juntas: fica com as 6 mais fortes
            ev_validos = sorted(ev_validos, key=lambda i: -notas[i].get("forca", 0))[:6]
            ls = [posicoes(notas[i]["midi"]) for i in ev_validos]
        cs = [[]]
        for l in ls:
            novos = []
            for c in cs:
                usadas = {p[0] for p in c}
                novos += [c + [p] for p in l if p[0] not in usadas]
            cs = (novos or [c + [l[0]] for c in cs])[:400]
        return ev_validos, cs

    est = []
    for ev in eventos:
        ev_ok, cs = combos(ev)
        opcoes = []
        for c in cs:
            casas = [f for _, f in c if f > 0]
            span = (max(casas) - min(casas)) if casas else 0
            if span > 5 and len(c) > 1:
                continue
            custo = sum(_custo_corda(prior, notas[i]["midi"] - cordas[0], s) for i, (s, _) in zip(ev_ok, c))
            custo += w["span"] * max(0, span - 3) + w["dedos"] * max(0, len(set(casas)) - 4)
            opcoes.append((c, custo, float(np.mean(casas)) if casas else None,
                           float(np.mean([s for s, _ in c]))))
        if not opcoes:
            c = cs[0]
            casas = [f for _, f in c if f > 0]
            opcoes = [(c, 0.0, float(np.mean(casas)) if casas else None, float(np.mean([s for s, _ in c])))]
        est.append((ev_ok, opcoes))

    custo = [o[1] for o in est[0][1]]
    volta = [[-1] * len(custo)]
    mao = [o[2] for o in est[0][1]]
    for k in range(1, len(est)):
        ev_ok, opcoes = est[k]
        ev_ant, op_ant = est[k - 1]
        dt = notas[ev_ok[0]]["inicio"] - notas[ev_ant[0]]["inicio"]
        fator = 1.0 / (1.0 + w["tempo"] * max(0.0, dt - 0.15))
        dp = int(np.clip(notas[ev_ok[0]]["midi"] - notas[ev_ant[0]]["midi"], -12, 12))
        tc = prior["trans"].get(dp, {})
        tot = sum(tc.values())
        novo, vk, mk = [], [], []
        for c, cl, centro, corda_m in opcoes:
            melhor, arg = float("inf"), 0
            for j, (cp, _, _, corda_p) in enumerate(op_ant):
                ref = mao[j]
                mov = 0.0 if (centro is None or ref is None) else abs(centro - ref)
                t = (w["mov"] * mov + w["mov2"] * max(0.0, mov - 4)) * fator
                if len(c) == 1 and len(cp) == 1:
                    ds = int(round(corda_m - corda_p))
                    t += -w["trans"] * np.log((tc.get(ds, 0) + 0.3) / (tot + 3.3))
                else:
                    t += w["corda"] * abs(corda_m - corda_p) * 0.3
                v = custo[j] + t
                if v < melhor:
                    melhor, arg = v, j
            novo.append(melhor + cl)
            vk.append(arg)
            mk.append(centro if centro is not None else mao[arg])
        custo, mao = novo, mk
        volta.append(vk)

    j = int(np.argmin(custo))
    escolhas = []
    for k in range(len(est) - 1, -1, -1):
        escolhas.append(est[k][1][j][0])
        j = volta[k][j]
    escolhas.reverse()

    fora = set()
    for (ev_ok, _), (ev_todos) in zip(est, eventos):
        fora |= set(ev_todos) - set(ev_ok)
    for (ev_ok, _), c in zip(est, escolhas):
        for i, (s, f) in zip(ev_ok, c):
            notas[i]["corda"], notas[i]["casa"] = int(s), int(f)
            notas[i]["nota"] = nome_nota(notas[i]["midi"])
    if fora:  # notas impossíveis nesta afinação ou acorde com mais de 6 notas
        notas[:] = [n for i, n in enumerate(notas) if i not in fora]
    return notas


# ------------------------------------------------------------- texto da tab
SIMBOLO = {"bend": "b", "bend 1 tom+": "b", "slide": "/", "hammer-on": "h",
           "pull-off": "p", "vibrato": "~"}


def _texto_nota(n):
    texto = str(n["casa"])
    for t in n.get("tecnicas", []):
        if t in SIMBOLO:
            return texto + SIMBOLO[t]
    return texto


def tab_ascii(notas, afinacao="E padrão", bpm=120.0, compassos_por_linha=4, papel=None, compassos=None):
    """Tablatura em texto. Com `compassos` (da cifra) usa os compassos reais da
    música, 4 colunas por tempo, e escreve os acordes em cima de cada linha."""
    notas = [n for n in notas if "casa" in n and (papel is None or n.get("papel") == papel)]
    if not notas:
        return "(sem notas nesta faixa)"
    cordas = AFINACOES.get(afinacao, AFINACOES["E padrão"])
    rotulos = [NOTAS[m % 12].ljust(2) for m in cordas[::-1]]   # 1ª corda em cima

    if not compassos:  # sem cifra: grade fixa em 4/4 pelo BPM
        seg = 4 * 60.0 / max(bpm, 1e-6)
        total = max(n["fim"] for n in notas)
        compassos = [{"n": k + 1, "inicio": k * seg, "fim": (k + 1) * seg,
                      "batidas": [k * seg + b * seg / 4 for b in range(4)], "acordes": []}
                     for k in range(int(total / seg) + 1)]

    def coluna(c, t):
        """posição (em 16 avos) de t dentro do compasso c, seguindo as batidas reais"""
        bs = list(c["batidas"]) + [c["fim"]]
        for b in range(len(bs) - 1):
            if t < bs[b + 1] or b == len(bs) - 2:
                frac = (t - bs[b]) / max(1e-6, bs[b + 1] - bs[b])
                return int(round(b * 4 + min(max(frac, 0), 0.999) * 4))
        return 0

    por_compasso = [[] for _ in compassos]
    inicios = [c["inicio"] for c in compassos]
    import bisect
    for n in notas:
        k = bisect.bisect_right(inicios, n["inicio"] + 0.02) - 1
        if 0 <= k < len(compassos):
            por_compasso[k].append(n)

    blocos = []
    ultimo = max((k for k, l in enumerate(por_compasso) if l), default=-1)
    for ini in range(0, ultimo + 1, compassos_por_linha):
        grupo = range(ini, min(ini + compassos_por_linha, len(compassos)))
        linhas = [rotulos[r] + "|" for r in range(6)]
        acima = " " * 3
        for k in grupo:
            c = compassos[k]
            slots = max(4, len(c["batidas"]) * 4)
            cel = [dict() for _ in range(slots)]       # slot -> {linha: texto}
            for n in sorted(por_compasso[k], key=lambda x: x["inicio"]):
                col = min(coluna(c, n["inicio"]), slots - 1)
                linha = n["corda"] - 1
                while col < slots - 1 and linha in cel[col]:
                    col += 1                           # mesma corda já ocupada: vai pro próximo
                cel[col][linha] = _texto_nota(n)
            acordes = {int(a["batida"]) * 4: a["acorde"] for a in c.get("acordes", []) if a["acorde"] != "N"}
            for col in range(slots):
                # coluna vazia ocupa 1 traço; com nota, a largura da nota + 1
                largura = (max(len(t) for t in cel[col].values()) + 1) if cel[col] else 1
                if col in acordes:
                    largura = max(largura, min(len(acordes[col]) + 1, 6))
                for r in range(6):
                    linhas[r] += cel[col].get(r, "").ljust(largura, "-")
                acima += acordes.get(col, "").ljust(largura)[:largura]
            for r in range(6):
                linhas[r] += "|"
            acima += " "
        numero = compassos[ini].get("n", ini + 1)
        blocos.append(f"compasso {numero}\n{acima.rstrip()}\n" + "\n".join(linhas))
    cab = f"Afinação: {afinacao}   BPM: {bpm:.0f}\n"
    return cab + "\n\n".join(blocos)
