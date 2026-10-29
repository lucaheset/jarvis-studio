"""Ligação com o JARVIS MUSIC (separar e analisar músicas).

O JARVIS MUSIC continua sendo o mesmo programa, com o ambiente dele (PyTorch,
CUDA etc.). O Studio só liga o servidor dele em segundo plano, mostra a tela
numa aba e puxa os stems de uma análise para virarem faixas do estúdio.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

PORTA = int(os.environ.get("JM_PORTA", 8770))
URL = f"http://127.0.0.1:{PORTA}"


def _candidatas(raiz_studio):
    raiz = Path(raiz_studio)
    casa = Path.home()
    nomes = ["jarvis-music", "JARVIS MUSIC", "jarvis_music"]
    bases = [raiz.parent, raiz.parent.parent, casa, casa / "Desktop", casa / "Documents",
             casa / "Downloads", Path("G:/JARVIS"), Path("G:/"), Path("E:/"), Path("D:/"), Path("C:/")]
    for b in bases:
        for n in nomes:
            yield b / n


def valida(pasta):
    p = Path(pasta)
    return (p / "backend" / "servidor.py").exists()


def python_de(pasta):
    p = Path(pasta)
    for c in (p / ".venv" / "Scripts" / "python.exe", p / ".venv" / "bin" / "python"):
        if c.exists():
            return c
    return None


def achar(raiz_studio, salva=None):
    if salva and valida(salva):
        return str(Path(salva))
    for c in _candidatas(raiz_studio):
        try:
            if valida(c):
                return str(c)
        except OSError:
            continue
    return None


def _get(caminho, timeout=3):
    with urllib.request.urlopen(URL + caminho, timeout=timeout) as r:
        return r.read()


def no_ar():
    try:
        return json.loads(_get("/api/saude", timeout=1.5)).get("ok", False)
    except Exception:
        return False


class JarvisMusic:
    def __init__(self):
        self.proc = None
        self.log = None

    def iniciar(self, pasta, espera=90):
        """Liga o servidor (se ainda não estiver no ar) e espera ele responder."""
        if no_ar():
            return URL
        if self.proc is None or self.proc.poll() is not None:
            py = python_de(pasta)
            if py is None:
                raise RuntimeError(f"Não achei o ambiente do JARVIS MUSIC em {pasta}\\.venv. "
                                   "Rode o instalar.bat dele primeiro.")
            self.log = open(Path(tempfile.gettempdir()) / "jarvis-music-studio.log", "w",
                            encoding="utf-8", errors="replace")
            flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            self.proc = subprocess.Popen(
                [str(py), str(Path(pasta) / "backend" / "servidor.py")], cwd=str(pasta),
                stdout=self.log, stderr=subprocess.STDOUT, creationflags=flags, env=env)
        fim = time.time() + espera
        while time.time() < fim:
            if no_ar():
                return URL
            if self.proc.poll() is not None:
                raise RuntimeError("O servidor do JARVIS MUSIC fechou ao abrir. Veja o arquivo "
                                   f"{self.log.name if self.log else 'de log'}.")
            time.sleep(0.5)
        raise RuntimeError("O JARVIS MUSIC demorou demais para abrir.")

    def parar(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except Exception:
                self.proc.kill()
        self.proc = None

    @staticmethod
    def analises():
        itens = json.loads(_get("/api/analises?limite=40"))
        return [i for i in itens if i.get("concluido") or (i.get("progresso") or 0) >= 58]

    @staticmethod
    def baixar_faixas(id_):
        """Baixa os stems da análise. Devolve (estado, [(rótulo, caminho)])."""
        est = json.loads(_get(f"/api/estado/{urllib.parse.quote(id_)}"))
        pasta = Path(tempfile.mkdtemp(prefix="jarvis-stems-"))
        saida = []
        for f in est.get("faixas", []):
            url = f.get("url") or ""
            if "/api/arquivo/" in url:
                url = url[url.index("/api/arquivo/"):]
            elif f.get("arquivo") or f.get("id"):
                # sem url: o stem fica na pasta da análise com o nome da faixa
                nome_arq = f.get("arquivo") or f"{f['id']}.wav"
                url = f"/api/arquivo/{id_}/{Path(nome_arq).name}"
            else:
                continue
            nome = url.rsplit("/", 1)[-1]
            destino = pasta / nome
            destino.write_bytes(_get(urllib.parse.quote(url, safe="/%"), timeout=120))
            saida.append((f.get("rotulo") or f.get("id") or nome, destino))
        return est, saida
