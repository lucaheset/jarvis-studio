"""Seções da música com o SongFormer (Hao et al., 2025, pesos CC BY 4.0).

Estado da arte em análise de estrutura musical (HarmonixSet e SongFormBench):
devolve trechos com rótulos funcionais (intro, verse, chorus, bridge, inst,
outro...). Aqui os trechos são encaixados nos compassos reais da música e
traduzidos para o português (Verso 1, Refrão 2...).
"""
import os
import sys
import types
from pathlib import Path

PASTA_MODELO = Path(os.environ.get("JM_MODELOS", Path(__file__).resolve().parent.parent / "modelos")) / "songformer"
_MODELO = None

NOMES = {"intro": "Intro", "verse": "Verso", "chorus": "Refrão", "bridge": "Ponte", "inst": "Instrumental",
         "outro": "Final", "prechorus": "Pré-refrão", "pre-chorus": "Pré-refrão", "solo": "Solo",
         "silence": "Silêncio", "break": "Instrumental", "interlude": "Instrumental"}
CORES = {"Intro": "intro", "Verso": "verso", "Pré-refrão": "pre", "Refrão": "refrao", "Ponte": "ponte",
         "Solo": "solo", "Instrumental": "inst", "Final": "final", "Silêncio": "inst"}


def disponivel():
    return (PASTA_MODELO / "model.safetensors").exists()


def _carregar():
    global _MODELO
    if _MODELO is not None:
        return _MODELO
    # o código do modelo importa duas coisas que só servem para treino/avaliação:
    # msaf.eval (métricas) e transformers.deepspeed (removido nas versões novas)
    if "msaf" not in sys.modules:
        msaf = types.ModuleType("msaf")
        ev = types.ModuleType("msaf.eval")
        ev.compute_results = lambda *a, **k: None
        msaf.eval = ev
        sys.modules["msaf"], sys.modules["msaf.eval"] = msaf, ev
    try:
        import transformers.deepspeed  # noqa: F401
    except Exception:
        ds = types.ModuleType("transformers.deepspeed")
        ds.is_deepspeed_zero3_enabled = lambda: False
        sys.modules["transformers.deepspeed"] = ds
    pasta = str(PASTA_MODELO)
    if pasta not in sys.path:
        sys.path.append(pasta)
    os.environ["SONGFORMER_LOCAL_DIR"] = pasta
    from transformers import AutoModel
    from . import gpu
    m = AutoModel.from_pretrained(pasta, trust_remote_code=True, low_cpu_mem_usage=False)
    m.to(gpu.dispositivo())
    m.eval()
    _MODELO = m
    gpu.ao_liberar(_descarregar)
    return m


def _descarregar():
    global _MODELO
    _MODELO = None


def _encaixar(t, compassos):
    """índice do compasso cujo começo está mais perto de t"""
    return min(range(len(compassos)), key=lambda k: abs(compassos[k]["inicio"] - t))


def detectar(caminho_audio, compassos):
    """Devolve [{inicio, fim, k_ini, k_fim, nome, tipo, cor, rotulo_original}]."""
    import librosa
    import torch
    from . import gpu
    wav, _ = librosa.load(str(caminho_audio), sr=24000, mono=True)
    with gpu.uso("seções"), torch.inference_mode():
        brutos = _carregar()(wav)
    compassos = [c for c in compassos if c["fim"] > c["inicio"]]
    if not compassos:
        return []

    # encaixa as fronteiras nos compassos e junta trechos vizinhos iguais
    trechos = []
    for s in brutos:
        tipo = NOMES.get(s["label"], s["label"].title())
        k0 = _encaixar(float(s["start"]), compassos)
        if trechos and trechos[-1]["tipo"] == tipo:
            continue
        if trechos and k0 <= trechos[-1]["k_ini"]:
            trechos[-1].update(tipo=tipo, rotulo_original=s["label"])
            continue
        trechos.append({"k_ini": k0, "tipo": tipo, "rotulo_original": s["label"]})
    if not trechos:
        return []
    trechos[0]["k_ini"] = 0
    for a, b in zip(trechos, trechos[1:]):
        a["k_fim"] = b["k_ini"]
    trechos[-1]["k_fim"] = len(compassos)
    trechos = [t for t in trechos if t["k_fim"] > t["k_ini"]]

    repetidos = {t["tipo"] for t in trechos if sum(x["tipo"] == t["tipo"] for x in trechos) > 1}
    cont, saida = {}, []
    for t in trechos:
        cont[t["tipo"]] = cont.get(t["tipo"], 0) + 1
        nome = f"{t['tipo']} {cont[t['tipo']]}" if t["tipo"] in repetidos and t["tipo"] not in ("Intro", "Final") else t["tipo"]
        saida.append({
            "inicio": round(compassos[t["k_ini"]]["inicio"], 3), "fim": round(compassos[t["k_fim"] - 1]["fim"], 3),
            "k_ini": t["k_ini"], "k_fim": t["k_fim"], "nome": nome, "tipo": t["tipo"],
            "cor": CORES.get(t["tipo"], "parte"), "rotulo_original": t["rotulo_original"],
        })
    return saida
