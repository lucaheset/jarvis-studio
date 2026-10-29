"""Velocidade e tom do áudio sem um mexer no outro (Signalsmith Stretch).

Renderiza todas as faixas de uma análise com a mesma velocidade e o mesmo
deslocamento de tom, para o mixer continuar tocando tudo em sincronia.
Medido: 60x mais rápido que o tempo real por faixa e os ataques ficam
alinhados (desvio menor que 10 ms). As versões ficam em cache por música.
"""
import json
import os
import shutil
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

GUARDAR = 5          # quantas versões manter por música (o treino progressivo usa várias)
_TRAVA = threading.Lock()
_EM_ANDAMENTO = {}   # (pasta, chave) -> thread


def chave(velocidade, semitons):
    return f"v{int(round(velocidade * 100))}_s{int(semitons):+d}"


def _prioridade_baixa():
    """Roda abaixo do normal para o PC continuar respondendo enquanto prepara."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        try:
            os.nice(10)
        except Exception:
            pass


def _renderizar_faixa(args):
    """Roda em outro processo: uma faixa com velocidade e tom novos -> FLAC."""
    origem, destino, velocidade, semitons = args
    import numpy as np
    import soundfile as sf
    import python_stretch as ps

    y, sr = sf.read(origem, dtype="float32", always_2d=True)
    x = np.ascontiguousarray(y.T)
    s = ps.Signalsmith.Stretch()
    s.preset(x.shape[0], sr)
    s.setTimeFactor(float(velocidade))
    s.setTransposeSemitones(float(semitons))
    out = s.process(x)
    pico = float(np.max(np.abs(out))) if out.size else 0.0
    if pico > 0.999:  # o deslocamento de tom pode passar de 0 dBFS
        out = out * (0.999 / pico)
    tmp = destino + ".tmp.flac"
    sf.write(tmp, out.T, sr, subtype="PCM_16", format="FLAC")
    Path(tmp).replace(destino)
    return destino


def estado(dir_analise, velocidade, semitons):
    d = Path(dir_analise) / "variacoes" / chave(velocidade, semitons)
    arq = d / "estado.json"
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    return None


def _limpar_antigas(dir_analise, manter):
    base = Path(dir_analise) / "variacoes"
    if not base.exists():
        return
    pastas = sorted((p for p in base.iterdir() if p.is_dir() and p.name != manter),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for p in pastas[GUARDAR - 1:]:
        shutil.rmtree(p, ignore_errors=True)


def pedir(dir_analise, faixas, velocidade, semitons):
    """Começa (ou reaproveita) a versão pedida. Devolve o estado atual dela."""
    dir_analise = Path(dir_analise)
    k = chave(velocidade, semitons)
    pasta = dir_analise / "variacoes" / k
    atual = estado(dir_analise, velocidade, semitons)
    if atual and atual.get("pronto"):
        pasta.touch()
        return atual
    with _TRAVA:
        if (str(dir_analise), k) in _EM_ANDAMENTO:
            return atual or {"chave": k, "pronto": False, "feitas": 0, "total": len(faixas)}
        pasta.mkdir(parents=True, exist_ok=True)
        info = {"chave": k, "velocidade": velocidade, "semitons": semitons, "pronto": False,
                "feitas": 0, "total": len(faixas), "erro": None, "faixas": {}}
        (pasta / "estado.json").write_text(json.dumps(info), encoding="utf-8")
        t = threading.Thread(target=_trabalhar, args=(dir_analise, pasta, faixas, velocidade, semitons, info),
                             daemon=True)
        _EM_ANDAMENTO[(str(dir_analise), k)] = t
        t.start()
    return info


def _trabalhar(dir_analise, pasta, faixas, velocidade, semitons, info):
    inicio = time.time()
    try:
        tarefas = [(str(dir_analise / f"{f}.wav"), str(pasta / f"{f}.flac"), velocidade, semitons)
                   for f in faixas if (dir_analise / f"{f}.wav").exists()]
        info["total"] = len(tarefas)
        with ProcessPoolExecutor(max_workers=min(4, max(1, len(tarefas))), initializer=_prioridade_baixa) as ex:
            for destino in ex.map(_renderizar_faixa, tarefas):
                nome = Path(destino).stem
                info["faixas"][nome] = Path(destino).name
                info["feitas"] += 1
                (pasta / "estado.json").write_text(json.dumps(info), encoding="utf-8")
        info["pronto"] = True
        info["segundos"] = round(time.time() - inicio, 1)
    except Exception as e:
        info["erro"] = f"{e.__class__.__name__}: {e}"
    finally:
        (pasta / "estado.json").write_text(json.dumps(info), encoding="utf-8")
        with _TRAVA:
            _EM_ANDAMENTO.pop((str(dir_analise), info["chave"]), None)
        _limpar_antigas(dir_analise, info["chave"])
