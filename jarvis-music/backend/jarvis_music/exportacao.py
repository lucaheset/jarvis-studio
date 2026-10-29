"""Exporta a tablatura: Guitar Pro (.gp5), MusicXML, MIDI e texto.

A ideia é você abrir no Guitar Pro, TuxGuitar ou MuseScore e corrigir o que o
transcritor errou, em vez de ficar preso ao resultado automático.

As exportações usam os compassos reais da música (os mesmos da cifra ao vivo):
fórmula de compasso de cada um, notas na posição das batidas detectadas,
duração de cada nota até a próxima e o nome do acorde em cima.
"""
import bisect
import xml.etree.ElementTree as ET
from pathlib import Path

from .tablatura import AFINACOES, NOTAS

DIV = 4  # divisões por semínima: grade de semicolcheia
# durações escrevíveis, em semicolcheias: (tamanho, valor GP, pontuada, nome MusicXML)
DURACOES = [(16, 1, False, "whole"), (12, 2, True, "half"), (8, 2, False, "half"),
            (6, 4, True, "quarter"), (4, 4, False, "quarter"), (3, 8, True, "eighth"),
            (2, 8, False, "eighth"), (1, 16, False, "16th")]


def _quebrar(n):
    """Quebra n semicolcheias em durações escrevíveis (maior primeiro)."""
    partes = []
    for tam, *_ in DURACOES:
        while n >= tam:
            partes.append(tam)
            n -= tam
    return partes


def _pausas(de, ate):
    eventos, pos = [], de
    for d in _quebrar(ate - de):
        eventos.append((pos, d, None))
        pos += d
    return eventos


def _compassos_padrao(notas, bpm):
    seg = 4 * 60.0 / max(bpm, 1e-6)
    fim = max((n["fim"] for n in notas), default=0)
    return [{"n": k + 1, "inicio": k * seg, "fim": (k + 1) * seg,
             "batidas": [k * seg + b * seg / 4 for b in range(4)], "acordes": []}
            for k in range(int(fim / seg) + 1)]


def quantizar(notas, compassos=None, bpm=120.0):
    """Coloca as notas na grade de semicolcheias dos compassos reais.

    Retorna [{tempos, acordes{slot: nome}, eventos: [(slot, dur, [notas] | None)]}].
    Cada nota dura até o próximo ataque (ou até acabar); as durações já vêm
    quebradas em valores escrevíveis e o resto do tempo vira pausa.
    """
    notas = [n for n in notas if "casa" in n]
    compassos = compassos or _compassos_padrao(notas, bpm)
    inicios = [c["inicio"] for c in compassos]
    por = [[] for _ in compassos]
    for n in notas:
        k = bisect.bisect_right(inicios, n["inicio"] + 0.02) - 1
        if 0 <= k < len(compassos):
            por[k].append(n)

    saida = []
    for c, lista in zip(compassos, por):
        tempos = max(1, len(c["batidas"]))
        slots = tempos * DIV
        bs = list(c["batidas"]) + [c["fim"]]

        def slot_de(t):
            for b in range(len(bs) - 1):
                if t < bs[b + 1] or b == len(bs) - 2:
                    frac = (t - bs[b]) / max(1e-6, bs[b + 1] - bs[b])
                    return b * DIV + min(max(frac, 0.0), 1.0) * DIV
            return 0.0

        grupos = {}
        for n in sorted(lista, key=lambda x: x["inicio"]):
            s = min(int(round(slot_de(n["inicio"]))), slots - 1)
            g = grupos.setdefault(s, [])
            if all(m["corda"] != n["corda"] for m in g):  # uma nota por corda
                g.append(n)
        ataques = sorted(grupos)
        eventos, pos = [], 0
        for i, s in enumerate(ataques):
            if s > pos:
                eventos += _pausas(pos, s)
            prox = ataques[i + 1] if i + 1 < len(ataques) else slots
            fim_nota = max(int(round(slot_de(min(n["fim"], c["fim"])))) for n in grupos[s])
            dur = max(1, min(prox, max(fim_nota, s + 1)) - s)
            d0 = _quebrar(dur)[0]
            eventos.append((s, d0, grupos[s]))
            pos = s + d0
        if pos < slots:
            eventos += _pausas(pos, slots)
        acordes = {}
        for a in c.get("acordes", []):
            if a["acorde"] != "N":
                acordes[min(int(a["batida"]) * DIV, slots - 1)] = a["acorde"]
        saida.append({"tempos": tempos, "eventos": eventos, "acordes": acordes})
    return saida


def _tom_fifths(tom):
    """'D maior' -> 2 (sustenidos); 'B menor' -> 2."""
    try:
        nota, modo = (tom or "").split()
        i = NOTAS.index(nota)
    except ValueError:
        return 0
    if modo == "menor":
        i = (i + 3) % 12
    return {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}[i]


def para_gp5(notas, destino, afinacao="E padrão", bpm=120.0, titulo="J.A.R.V.I.S MUSIC",
             faixa="Guitarra", compassos=None, tom=None):
    import guitarpro as gp

    cordas_midi = AFINACOES.get(afinacao, AFINACOES["E padrão"])[::-1]  # 1ª -> 6ª
    musica = gp.models.Song(title=titulo, artist="J.A.R.V.I.S MUSIC", tempo=int(round(bpm)))
    musica.tracks.clear()
    musica.measureHeaders.clear()

    trilha = gp.models.Track(musica, name=faixa, fretCount=24)
    trilha.strings = [gp.models.GuitarString(i + 1, m) for i, m in enumerate(cordas_midi)]
    trilha.measures.clear()

    inicio = 960
    for i, cp in enumerate(quantizar(notas, compassos, bpm)):
        cab = gp.models.MeasureHeader(number=i + 1, start=inicio)
        cab.timeSignature = gp.models.TimeSignature(numerator=cp["tempos"],
                                                    denominator=gp.models.Duration(value=4))
        musica.measureHeaders.append(cab)
        medida = gp.models.Measure(trilha, cab)
        medida.voices.clear()
        voz = gp.models.Voice(medida)
        voz.beats.clear()
        for slot, dur, grupo in cp["eventos"]:
            tam = next(d for d in DURACOES if d[0] == dur)
            batida = gp.models.Beat(voz, duration=gp.models.Duration(value=tam[1], isDotted=tam[2]))
            batida.start = inicio + slot * 240
            batida.notes.clear()
            if slot in cp["acordes"]:
                batida.text = cp["acordes"][slot]
            if grupo:
                batida.status = gp.models.BeatStatus.normal
                for n in grupo:
                    nota = gp.models.Note(batida, value=int(n["casa"]),
                                          string=int(n["corda"]),  # corda 1 = mi agudo = string 1 do Guitar Pro
                                          velocity=int(40 + 70 * min(1.0, n.get("forca", 0.6))),
                                          type=gp.models.NoteType.normal)
                    ef = nota.effect
                    tecs = n.get("tecnicas", [])
                    ef.vibrato = "vibrato" in tecs
                    ef.hammer = ("hammer-on" in tecs) or ("pull-off" in tecs)
                    if "slide" in tecs:
                        ef.slides = [gp.models.SlideType.legatoSlideTo]
                    if any(t.startswith("bend") for t in tecs):
                        alvo = 100 if "1 tom" in " ".join(tecs) else 50
                        ef.bend = gp.models.BendEffect(
                            type=gp.models.BendType.bend, value=alvo,
                            points=[gp.models.BendPoint(0, 0),
                                    gp.models.BendPoint(6, alvo // 2),
                                    gp.models.BendPoint(12, alvo)])
                    batida.notes.append(nota)
            else:
                batida.status = gp.models.BeatStatus.rest
            voz.beats.append(batida)
        medida.voices.append(voz)
        medida.voices.append(gp.models.Voice(medida))  # 2ª voz vazia, como o formato espera
        trilha.measures.append(medida)
        inicio += cp["tempos"] * 960
    musica.tracks.append(trilha)

    destino = Path(destino)
    gp.write(musica, str(destino), version=(5, 1, 0))
    return destino


KIND = {"": "major", "m": "minor", "7": "dominant", "m7": "minor-seventh", "maj7": "major-seventh",
        "5": "power", "sus4": "suspended-fourth", "dim": "diminished"}


def _harmonia(m, nome):
    raiz = nome[:2] if len(nome) > 1 and nome[1] == "#" else nome[:1]
    h = ET.SubElement(m, "harmony")
    r = ET.SubElement(h, "root")
    ET.SubElement(r, "root-step").text = raiz[0]
    if "#" in raiz:
        ET.SubElement(r, "root-alter").text = "1"
    ET.SubElement(h, "kind").text = KIND.get(nome[len(raiz):], "major")


def para_musicxml(notas, destino, afinacao="E padrão", bpm=120.0, titulo="J.A.R.V.I.S MUSIC",
                  compassos=None, tom=None):
    cordas_midi = AFINACOES.get(afinacao, AFINACOES["E padrão"])  # da 6ª para a 1ª
    raiz = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(raiz, "work"), "work-title").text = titulo
    lista = ET.SubElement(raiz, "part-list")
    sp = ET.SubElement(lista, "score-part", id="P1")
    ET.SubElement(sp, "part-name").text = "Guitarra"
    parte = ET.SubElement(raiz, "part", id="P1")

    anterior = None
    for i, cp in enumerate(quantizar(notas, compassos, bpm)):
        m = ET.SubElement(parte, "measure", number=str(i + 1))
        if i == 0 or cp["tempos"] != anterior:
            at = ET.SubElement(m, "attributes")
            if i == 0:
                ET.SubElement(at, "divisions").text = str(DIV)
                ET.SubElement(ET.SubElement(at, "key"), "fifths").text = str(_tom_fifths(tom))
            ts = ET.SubElement(at, "time")
            ET.SubElement(ts, "beats").text = str(cp["tempos"])
            ET.SubElement(ts, "beat-type").text = "4"
            if i == 0:
                clave = ET.SubElement(at, "clef")
                ET.SubElement(clave, "sign").text = "TAB"
                ET.SubElement(clave, "line").text = "5"
                st = ET.SubElement(at, "staff-details")
                ET.SubElement(st, "staff-lines").text = "6"
                for k, midi in enumerate(cordas_midi):  # linha 1 = corda mais grave
                    afin = ET.SubElement(st, "staff-tuning", line=str(k + 1))
                    ET.SubElement(afin, "tuning-step").text = NOTAS[midi % 12][0]
                    if "#" in NOTAS[midi % 12]:
                        ET.SubElement(afin, "tuning-alter").text = "1"
                    ET.SubElement(afin, "tuning-octave").text = str(midi // 12 - 1)
                direcao = ET.SubElement(m, "direction", placement="above")
                ET.SubElement(ET.SubElement(direcao, "direction-type"), "words").text = f"afinação: {afinacao}"
                ET.SubElement(direcao, "sound", tempo=str(int(round(bpm))))
        anterior = cp["tempos"]

        for slot, dur, grupo in cp["eventos"]:
            if slot in cp["acordes"]:
                _harmonia(m, cp["acordes"][slot])
            tam = next(d for d in DURACOES if d[0] == dur)
            if not grupo:
                r = ET.SubElement(m, "note")
                ET.SubElement(r, "rest")
                ET.SubElement(r, "duration").text = str(dur)
                ET.SubElement(r, "type").text = tam[3]
                if tam[2]:
                    ET.SubElement(r, "dot")
                continue
            for k, n in enumerate(sorted(grupo, key=lambda x: x["midi"])):
                el = ET.SubElement(m, "note")
                if k:
                    ET.SubElement(el, "chord")
                p = ET.SubElement(el, "pitch")
                passo = NOTAS[n["midi"] % 12]
                ET.SubElement(p, "step").text = passo[0]
                if "#" in passo:
                    ET.SubElement(p, "alter").text = "1"
                ET.SubElement(p, "octave").text = str(n["midi"] // 12 - 1)
                ET.SubElement(el, "duration").text = str(dur)
                ET.SubElement(el, "type").text = tam[3]
                if tam[2]:
                    ET.SubElement(el, "dot")
                tecnico = ET.SubElement(ET.SubElement(el, "notations"), "technical")
                tecs = n.get("tecnicas", [])
                if "hammer-on" in tecs:
                    ET.SubElement(tecnico, "hammer-on", type="start").text = "H"
                if "pull-off" in tecs:
                    ET.SubElement(tecnico, "pull-off", type="start").text = "P"
                if any(t.startswith("bend") for t in tecs):
                    b = ET.SubElement(tecnico, "bend")
                    ET.SubElement(b, "bend-alter").text = "2" if "1 tom" in " ".join(tecs) else "1"
                ET.SubElement(tecnico, "string").text = str(n["corda"])
                ET.SubElement(tecnico, "fret").text = str(n["casa"])

    destino = Path(destino)
    ET.ElementTree(raiz).write(str(destino), encoding="UTF-8", xml_declaration=True)
    return destino


def para_midi(notas, destino, bpm=120.0, nome="Guitarra"):
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
    inst = pretty_midi.Instrument(program=29, name=nome)  # overdriven guitar
    for n in notas:
        inst.notes.append(pretty_midi.Note(
            velocity=int(40 + 70 * min(1.0, n.get("forca", 0.6))),
            pitch=int(n["midi"]), start=float(n["inicio"]), end=float(max(n["fim"], n["inicio"] + 0.05))))
    pm.instruments.append(inst)
    destino = Path(destino)
    pm.write(str(destino))
    return destino
