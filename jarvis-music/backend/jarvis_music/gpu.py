"""Uso educado da placa de vídeo: os modelos não podem travar o PC.

Antes, separar/transcrever deixava a GPU em 100% e o Windows inteiro travava.
Tudo que usa modelo passa por aqui:
- um modelo por vez (fila), nunca dois na GPU ao mesmo tempo;
- o processo roda com prioridade baixa no Windows, tanto na CPU quanto no
  agendador da GPU, então a tela, o jogo e o navegador passam na frente;
- teto de memória de vídeo (JM_GPU_MEMORIA, fração da placa, padrão 0.5);
- pausas curtas entre os blocos que a gente controla (JM_GPU_PAUSA, segundos);
- no fim de cada análise os modelos saem da memória e a VRAM é devolvida.

JM_SEM_GPU=1 força tudo na CPU.
"""
import contextlib
import gc
import os
import sys
import threading
import time

_FILA = threading.Lock()
_DESCARREGAR = []        # funções que tiram os modelos da memória
_PREPARADO = False


def _env_float(nome, padrao):
    try:
        return float(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


MEMORIA = min(0.9, max(0.1, _env_float("JM_GPU_MEMORIA", 0.5)))
PAUSA = max(0.0, _env_float("JM_GPU_PAUSA", 0.05))


def sem_gpu():
    return os.environ.get("JM_SEM_GPU", "").strip() not in ("", "0")


if sem_gpu():
    # esconde a placa de tudo (torch, audio-separator, demucs) antes de qualquer import
    os.environ["CUDA_VISIBLE_DEVICES"] = ""


def prioridade_baixa():
    """Prioridade abaixo do normal na CPU e no agendador de GPU do Windows."""
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.nice(10)
        return
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    eu = k32.GetCurrentProcess()
    with contextlib.suppress(Exception):
        k32.SetPriorityClass(eu, 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
    with contextlib.suppress(Exception):
        # D3DKMT_SCHEDULINGPRIORITYCLASS_BELOW_NORMAL = 1: o compositor da área
        # de trabalho e os outros programas ganham a placa primeiro
        f = ctypes.WinDLL("gdi32").D3DKMTSetProcessSchedulingPriorityClass
        f.argtypes = [wintypes.HANDLE, ctypes.c_int]
        f(eu, 1)


def _preparar(torch):
    global _PREPARADO
    if _PREPARADO:
        return
    _PREPARADO = True
    prioridade_baixa()
    with contextlib.suppress(Exception):
        torch.cuda.set_per_process_memory_fraction(MEMORIA, 0)


def dispositivo():
    """'cuda' (já com os limites aplicados) ou 'cpu'."""
    if sem_gpu():
        return "cpu"
    try:
        import torch
    except ImportError:
        return "cpu"
    if not torch.cuda.is_available():
        return "cpu"
    _preparar(torch)
    return "cuda"


def ao_liberar(funcao):
    """Registra quem sabe tirar um modelo da memória (chamado em liberar())."""
    if funcao not in _DESCARREGAR:
        _DESCARREGAR.append(funcao)
    return funcao


def _esvaziar_cache():
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available() and torch.cuda.is_initialized():
        with contextlib.suppress(Exception):
            torch.cuda.synchronize()
        torch.cuda.empty_cache()
        with contextlib.suppress(Exception):
            torch.cuda.ipc_collect()


def liberar():
    """Descarrega todos os modelos e devolve a memória de vídeo."""
    for f in _DESCARREGAR:
        with contextlib.suppress(Exception):
            f()
    _esvaziar_cache()


@contextlib.contextmanager
def uso(nome=""):
    """Um modelo por vez na GPU; ao sair, devolve o cache de memória."""
    with _FILA:
        try:
            yield dispositivo()
        finally:
            _esvaziar_cache()
            if PAUSA:
                time.sleep(PAUSA * 10)  # respiro para a área de trabalho entre etapas


def respirar():
    """Pausa curta entre blocos de inferência que a gente mesmo controla."""
    if PAUSA:
        time.sleep(PAUSA)


def flags_subprocesso():
    """creationflags para rodar um processo filho com prioridade baixa."""
    return 0x00004000 if sys.platform == "win32" else 0  # BELOW_NORMAL_PRIORITY_CLASS
