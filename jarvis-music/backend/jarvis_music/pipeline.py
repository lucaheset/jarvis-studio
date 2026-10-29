"""Pipeline completo: áudio -> faixas + análise + tablatura."""
import json
import os
import shutil
import time
import traceback
from pathlib import Path

import numpy as np

from . import analise, efeitos, exportacao, gpu, separacao, tablatura
from .audio import carregar, picos, rms_db, para_mono, SR

ROTULOS = {"voz": "Voz", "guitarra": "Guitarra", "baixo": "Baixo", "bateria": "Bateria",
           "piano": "Piano", "outros": "Outros", "guitarra_esquerda": "Guitarra L",
           "guitarra_centro": "Guitarra C", "guitarra_direita": "Guitarra R",
           "guitarra_base": "Guitarra base", "guitarra_solo": "Guitarra solo"}


class Trabalho:
    """Estado de uma análise, salvo em disco para a interface ler."""

    def __init__(self, raiz, id_, nome_arquivo):
        self.dir = Path(raiz) / id_
        self.dir.mkdir(parents=True, exist_ok=True)
        self.estado = {"id": id_, "arquivo": nome_arquivo, "etapa": "na fila",
                       "progresso": 0, "registro": [], "faixas": [], "erro": None,
                       "criado": time.time()}
        self.salvar()

    @property
    def arquivo_estado(self):
        return self.dir / "estado.json"

    def salvar(self):
        tmp = self.arquivo_estado.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo_estado)

    def passo(self, texto, progresso=None):
        self.estado["etapa"] = texto
        if progresso is not None:
            self.estado["progresso"] = progresso
        self.estado["registro"].append({"t": round(time.time(), 1), "texto": texto})
        self.salvar()


def _faixa_info(id_, caminho, url_base):
    y = carregar(caminho)
    return {"id": id_, "rotulo": ROTULOS.get(id_, id_.title()),
            "url": f"{url_base}/{caminho.name}", "picos": picos(y),
            "db": round(rms_db(y), 1), "e_guitarra": id_.startswith("guitarra")}


def processar(caminho_audio, trabalho, modelos_dir, motor_separacao="auto"):
    """Roda tudo e preenche trabalho.estado."""
    try:
        d = trabalho.dir
        base = f"/api/arquivo/{trabalho.estado['id']}"
        trabalho.passo("Lendo o áudio", 3)
        original = d / f"original{Path(caminho_audio).suffix.lower() or '.wav'}"
        if Path(caminho_audio) != original:
            shutil.copy(caminho_audio, original)
        mono = para_mono(carregar(original))
        trabalho.estado["duracao"] = round(len(mono) / SR, 2)

        trabalho.passo("Detectando BPM e compasso", 8)
        ritmo = analise.bpm_e_batidas(original)
        trabalho.estado["ritmo"] = ritmo
        bpm = ritmo["bpm"] or 120.0

        trabalho.passo("Detectando o tom", 14)
        trabalho.estado["tom"] = analise.tom(mono)
        trabalho.passo("Tirando a cifra por compasso", 20)
        aplicar_cifra(trabalho.estado, mono)
        trabalho.salvar()

        trabalho.passo("Separando os instrumentos", 26)
        stems = separacao.separar(original, d, modelos_dir,
                                  aviso=lambda t: trabalho.passo(t, 30),
                                  motor=motor_separacao)
        if not stems:
            raise RuntimeError("a separação não gerou faixas")

        faixas = [_faixa_info(id_, p, base) for id_, p in sorted(stems.items())]
        trabalho.estado["faixas"] = faixas
        trabalho.passo(f"{len(faixas)} faixas prontas", 56)

        trabalho.passo("Encontrando as partes da música", 58)
        try:
            trabalho.estado["secoes"] = gerar_secoes(trabalho.estado, d, mono=mono)
        except Exception as e:  # as partes são um extra: não derrubam a análise
            trabalho.estado["secoes"] = {"lista": [], "erro": f"{e.__class__.__name__}: {e}"}
        trabalho.salvar()

        # guitarra: divide por panorama para aproximar base x solo
        if "guitarra" in stems:
            trabalho.passo("Separando as guitarras por panorama", 62)
            partes = separacao.dividir_por_panorama(stems["guitarra"], d)
            for id_, info in sorted(partes.items()):
                f = _faixa_info(id_, info["caminho"], base)
                f["fracao"] = info["fracao"]
                f["derivada_de"] = "guitarra"
                faixas.append(f)
            trabalho.estado["faixas"] = faixas
            trabalho.salvar()

            trabalho.passo("Analisando os efeitos da guitarra", 70)
            trabalho.estado["efeitos"] = {
                "guitarra": efeitos.analisar(stems["guitarra"], bpm=bpm)}
            for id_, info in partes.items():
                trabalho.estado["efeitos"][id_] = efeitos.analisar(info["caminho"], bpm=bpm)
            trabalho.salvar()

            trabalho.passo("Transcrevendo a guitarra", 78)
            trabalho.estado["tabs"] = {}
            alvos = {"guitarra": stems["guitarra"]}
            alvos.update({k: v["caminho"] for k, v in partes.items()})
            for id_, cam in alvos.items():
                try:
                    trabalho.passo(f"Gerando a tablatura ({ROTULOS.get(id_, id_)})", 80)
                    trabalho.estado["tabs"][id_] = gerar_tab(cam, d, id_, bpm, compassos=trabalho.estado.get("compassos"),
                                                             tom=(trabalho.estado.get("tom") or {}).get("tom"))
                    trabalho.salvar()
                except Exception as e:
                    trabalho.estado["tabs"][id_] = {"erro": f"{e.__class__.__name__}: {e}"}
                    trabalho.salvar()

            # guitarras juntas no centro: separa base e solo pelas notas da tab (só CPU)
            if not partes:
                trabalho.passo("Separando guitarra base e solo pelas notas", 94)
                try:
                    trabalho.estado["base_solo"] = dividir_base_solo(trabalho.estado, d)
                except Exception as e:  # extra: não derruba a análise
                    trabalho.estado["base_solo"] = {"ok": False, "motivo": f"{e.__class__.__name__}: {e}"}
                trabalho.salvar()

        trabalho.passo("Pronto", 100)
        trabalho.estado["concluido"] = True
    except Exception as e:
        trabalho.estado["erro"] = f"{e.__class__.__name__}: {e}"
        trabalho.estado["traceback"] = traceback.format_exc()[-2500:]
        trabalho.passo("Falhou")
    finally:
        trabalho.salvar()
        gpu.liberar()  # nenhum modelo fica parado ocupando a placa


def aplicar_cifra(estado, mono):
    """Cifra alinhada aos compassos (para acompanhar ao vivo) + a lista linear."""
    compassos, linear, por_compasso = analise.cifra_compassos(
        mono, estado.get("ritmo") or {}, tom_texto=(estado.get("tom") or {}).get("tom"))
    estado["compassos"] = compassos
    estado["tempos_por_compasso"] = por_compasso
    estado["cifra"] = linear
    estado["versao_cifra"] = 2


def dividir_base_solo(estado, dir_analise):
    """Cria as faixas guitarra_base e guitarra_solo a partir das notas da tab da guitarra.
    Mexe em estado["faixas"] e devolve um resumo para a interface."""
    from . import base_solo
    tab = (estado.get("tabs") or {}).get("guitarra") or {}
    cam = Path(dir_analise) / "guitarra.wav"
    if not tab.get("notas") or not cam.exists():
        return {"ok": False, "motivo": "esta música não tem tablatura da guitarra"}
    partes = base_solo.dividir(cam, tab["notas"], dir_analise)
    faixas = [f for f in estado.get("faixas", []) if f["id"] not in ("guitarra_base", "guitarra_solo")]
    if not partes:
        estado["faixas"] = faixas
        return {"ok": False, "motivo": "quase não achei notas de solo na faixa de guitarra: "
                "parece ser só base (o solo pode ter ido para a faixa Outros)"}
    url = f"/api/arquivo/{estado['id']}"
    for id_, info in sorted(partes.items()):
        f = _faixa_info(id_, info["caminho"], url)
        f.update(fracao=info["fracao"], derivada_de="guitarra", metodo="notas")
        faixas.append(f)
    estado["faixas"] = faixas
    return {"ok": True, "fracoes": {k: v["fracao"] for k, v in partes.items()}}


def gerar_secoes(estado, dir_analise, mono=None, motor=None):
    """Partes da música (intro, verso, refrão...) encaixadas nos compassos.

    motor: "songformer" (modelo, usa a GPU com os limites de gpu.py),
    "heuristica" (só CPU) ou "auto" (o modelo quando os pesos existem).
    Padrão: variável JM_SECOES, senão "auto"."""
    from . import secoes, secoes_ml
    motor = motor or os.environ.get("JM_SECOES", "auto")
    compassos = estado.get("compassos") or []
    if motor in ("auto", "songformer") and secoes_ml.disponivel():
        originais = sorted(Path(dir_analise).glob("original.*"))
        try:
            lista = secoes_ml.detectar(originais[0], compassos)
            if lista:
                return {"lista": lista, "motor": "SongFormer (Hao et al., 2025)"}
        except Exception as e:
            if motor == "songformer":
                raise
            aviso = f"SongFormer indisponível ({e.__class__.__name__}); usei a estimativa por compassos"
            return {"lista": secoes.detectar(dir_analise, compassos, mono=mono),
                    "motor": "estimativa por compassos", "aviso": aviso}
    return {"lista": secoes.detectar(dir_analise, compassos, mono=mono), "motor": "estimativa por compassos"}


def gerar_tab(caminho_guitarra, dir_saida, id_faixa, bpm, sensibilidade=0.5, compassos=None, tom=None):
    """Transcreve uma faixa de guitarra e exporta nos formatos editáveis."""
    notas = tablatura.transcrever(caminho_guitarra, sensibilidade=sensibilidade, motor="auto")
    if not notas:
        return {"notas": [], "aviso": "nenhuma nota detectada nesta faixa"}
    notas = tablatura.detectar_tecnicas(caminho_guitarra, notas)
    notas, trechos = tablatura.classificar_base_solo(notas, bpm=bpm)
    afin, conf_afin = tablatura.detectar_afinacao(notas)
    notas = tablatura.atribuir_cordas(notas, afinacao=afin)
    notas = tablatura.marcar_ligados(notas)

    saida = montar_tab(notas, dir_saida, id_faixa, bpm, afin, compassos=compassos, tom=tom)
    saida.update({"motor": "guitarra-fl (Riley et al.) + Viterbi de cordas (GuitarSet)",
                  "confianca_afinacao": conf_afin, "trechos": trechos})
    return saida


def montar_tab(notas, dir_saida, id_faixa, bpm, afin, compassos=None, tom=None):
    """Exporta GP5/MusicXML/MIDI e o texto de uma lista de notas já com corda e casa."""
    notas.sort(key=lambda n: (n["inicio"], n.get("corda", 0)))
    arquivos, falhas = {}, []
    for papel in (None, "base", "solo"):
        sel = notas if papel is None else [n for n in notas if n.get("papel") == papel]
        if not sel:
            continue
        sufixo = papel or "completo"
        nome = f"tab_{id_faixa}_{sufixo}"
        rotulo = f"{ROTULOS.get(id_faixa, id_faixa)} {sufixo}"
        for chave, func in (
            ("gp5", lambda: exportacao.para_gp5(sel, dir_saida / f"{nome}.gp5", afinacao=afin, bpm=bpm,
                                                faixa=rotulo, compassos=compassos, tom=tom)),
            ("musicxml", lambda: exportacao.para_musicxml(sel, dir_saida / f"{nome}.musicxml", afinacao=afin,
                                                          bpm=bpm, compassos=compassos, tom=tom)),
            ("midi", lambda: exportacao.para_midi(sel, dir_saida / f"{nome}.mid", bpm=bpm)),
        ):
            try:
                arquivos[f"{sufixo}_{chave}"] = func().name
            except Exception as e:
                falhas.append(f"{sufixo} {chave}: {e.__class__.__name__}: {e}")

    return {
        "afinacao": afin, "bpm": round(bpm, 1),
        "n_notas": len(notas),
        "notas": notas,
        "ascii": {
            "completo": tablatura.tab_ascii(notas, afin, bpm, compassos=compassos),
            "base": tablatura.tab_ascii(notas, afin, bpm, papel="base", compassos=compassos),
            "solo": tablatura.tab_ascii(notas, afin, bpm, papel="solo", compassos=compassos),
        },
        "arquivos": arquivos,
        "falhas_exportacao": falhas,
        "aviso": "transcrição automática: confira as notas e corrija no Guitar Pro ou MuseScore",
    }


def salvar_tab_editada(tab_antiga, notas_novas, dir_saida, id_faixa, bpm, compassos=None, tom=None):
    """Grava as correções feitas na tela: confere cada nota contra a afinação e refaz os arquivos."""
    afin = tab_antiga.get("afinacao", "E padrão")
    cordas = tablatura.AFINACOES.get(afin, tablatura.AFINACOES["E padrão"])
    limpas = []
    for n in notas_novas:
        try:
            corda, casa = int(n["corda"]), int(n["casa"])
            inicio, fim = float(n["inicio"]), float(n["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (1 <= corda <= 6 and 0 <= casa <= 24 and fim > inicio >= 0):
            continue
        midi = cordas[6 - corda] + casa
        tecs = [t for t in (n.get("tecnicas") or []) if t in tablatura.SIMBOLO]
        limpas.append({"inicio": round(inicio, 4), "fim": round(fim, 4), "midi": midi, "corda": corda,
                       "casa": casa, "nota": tablatura.nome_nota(midi), "tecnicas": tecs,
                       "papel": n.get("papel") if n.get("papel") in ("base", "solo") else "base",
                       "forca": float(n.get("forca", 0.7)), "editada": bool(n.get("editada"))})
    saida = montar_tab(limpas, dir_saida, id_faixa, bpm, afin, compassos=compassos, tom=tom)
    saida.update({k: tab_antiga[k] for k in ("motor", "confianca_afinacao", "trechos") if k in tab_antiga})
    saida["editada"] = True
    saida["n_editadas"] = sum(1 for n in limpas if n["editada"])
    return saida
