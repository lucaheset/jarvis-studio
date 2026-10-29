"""Ponte entre a tela (JavaScript) e o motor de áudio.

O pywebview expõe os métodos desta classe em window.pywebview.api.<nome>().
Cada método devolve um dicionário; erros voltam como {"erro": "mensagem"}.
"""
import functools
import json
import threading
import traceback
from pathlib import Path

from . import efeitos as fx
from . import musica
from . import projeto
from .motor import Motor, PICO_PASSO

TIPOS_AUDIO = ("Áudio (*.wav;*.mp3;*.flac;*.ogg;*.m4a;*.aif;*.aiff)", "Todos os arquivos (*.*)")


def _seguro(fn):
    @functools.wraps(fn)
    def envolto(self, *a, **k):
        try:
            r = fn(self, *a, **k)
            return {"ok": True} if r is None else r
        except Exception as e:
            traceback.print_exc()
            return {"erro": str(e) or type(e).__name__}
    return envolto


class Api:
    def __init__(self, pasta_dados):
        self._motor = Motor()
        self._janela = None
        self._dados = Path(pasta_dados)
        self._dados.mkdir(parents=True, exist_ok=True)
        self._arq_config = self._dados / "config.json"
        self._projeto = None          # pasta do projeto aberto
        self._pos_play = 0
        self._editores = {}
        self._musica = musica.JarvisMusic()

    # ----------------------------------------------------------------- internos
    def _ler_config(self):
        try:
            return json.loads(self._arq_config.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _gravar_config(self, **novos):
        c = self._ler_config()
        c.update(novos)
        self._arq_config.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")

    def _dialogo(self, tipo, **k):
        import webview
        fd = getattr(webview, "FileDialog", None)
        mapa = {"abrir": "OPEN", "salvar": "SAVE", "pasta": "FOLDER"}
        if fd is not None:
            modo = getattr(fd, mapa[tipo])
        else:
            modo = getattr(webview, f"{mapa[tipo]}_DIALOG")
        r = self._janela.create_file_dialog(modo, **k)
        if not r:
            return None
        return r if isinstance(r, str) else list(r)

    def _iniciar(self, janela):
        """Chamado pelo app.py depois que a janela existe: reabre a placa salva."""
        self._janela = janela
        cfg = self._ler_config().get("audio")
        if cfg:
            try:
                self._motor.abrir(cfg)
            except Exception as e:
                self._motor.erro = f"Não abriu a placa salva: {e}"

    def _encerrar(self):
        self._motor.parar()
        self._motor.fechar()
        self._musica.parar()

    # ------------------------------------------------------------------ leitura
    @_seguro
    def estado(self):
        return self._motor.estado()

    @_seguro
    def resumo(self):
        r = self._motor.resumo()
        r["projeto"] = self._projeto
        return r

    @_seguro
    def dispositivos(self):
        d = Motor.dispositivos()
        d["config"] = self._motor.config or self._ler_config().get("audio", {})
        return d

    @_seguro
    def catalogo(self):
        c = fx.catalogo()
        try:
            c["vst3"] = fx.listar_vst3()
        except Exception:
            c["vst3"] = []
        return c

    @_seguro
    def picos(self, id_):
        f = self._motor.faixa(id_)
        return {"versao": f.versao, "passo": PICO_PASSO, "picos": f.picos()}

    # -------------------------------------------------------------------- áudio
    @_seguro
    def configurar(self, cfg):
        self._motor.parar()
        self._motor.abrir(cfg)
        self._gravar_config(audio=self._motor.config)
        return self._motor.resumo()

    # --------------------------------------------------------------- transporte
    @_seguro
    def tocar(self):
        if not self._motor.tocando:
            self._pos_play = max(self._motor.pos, 0)
        self._motor.tocar()

    @_seguro
    def pausar(self):
        self._motor.pausar()

    @_seguro
    def parar(self):
        estava = self._motor.tocando
        self._motor.parar()
        if estava:
            self._motor.ir_para(self._pos_play)
        else:
            self._motor.ir_para(0)

    @_seguro
    def gravar(self):
        if not self._motor.tocando:
            self._pos_play = max(self._motor.pos, 0)
        self._motor.gravar()

    @_seguro
    def ir_para(self, amostra):
        self._motor.ir_para(amostra)
        if not self._motor.tocando:
            self._pos_play = self._motor.pos

    @_seguro
    def ajustar_global(self, campo, valor):
        m = self._motor
        tipos = {"bpm": float, "compasso": int, "metronomo": bool, "metro_volume": float,
                 "contagem": bool, "loop": bool, "loop_ini": int, "loop_fim": int,
                 "master_db": float, "ajuste_latencia": int}
        if campo not in tipos:
            raise ValueError(f"campo desconhecido: {campo}")
        v = tipos[campo](valor)
        if campo == "bpm":
            v = min(max(v, 20.0), 400.0)
        if campo == "compasso":
            v = min(max(v, 1), 16)
        setattr(m, campo, v)

    # ------------------------------------------------------------------- faixas
    @_seguro
    def nova_faixa(self):
        return self._motor.nova_faixa().info()

    @_seguro
    def remover_faixa(self, id_):
        if self._motor.gravando:
            raise RuntimeError("Pare a gravação antes de apagar faixas.")
        self._motor.remover_faixa(id_)

    @_seguro
    def mover_faixa(self, id_, direcao):
        self._motor.mover_faixa(id_, int(direcao))

    @_seguro
    def ajustar_faixa(self, id_, campo, valor):
        f = self._motor.faixa(id_)
        if campo == "nome":
            f.nome = str(valor)[:60] or f.nome
        elif campo in ("volume_db", "pan"):
            v = float(valor)
            setattr(f, campo, min(max(v, -60.0), 12.0) if campo == "volume_db" else min(max(v, -1.0), 1.0))
        elif campo in ("mudo", "solo", "monitor"):
            setattr(f, campo, bool(valor))
        elif campo == "armada":
            if self._motor.gravando:
                raise RuntimeError("Não dá para armar ou desarmar durante a gravação.")
            f.armada = bool(valor)
        elif campo == "entrada":
            f.entrada = [int(c) for c in valor][:2] or [0]
        elif campo == "inicio":
            f.inicio = max(0, int(valor))
        else:
            raise ValueError(f"campo desconhecido: {campo}")
        return f.info()

    @_seguro
    def limpar_faixa(self, id_):
        self._motor.faixa(id_).trocar_audio(None)

    # ------------------------------------------------------------------ efeitos
    @_seguro
    def adicionar_efeito(self, id_, tipo):
        ef = fx.criar(tipo)
        self._motor.adicionar_efeito(id_, ef)
        return self._motor.faixa(id_).info()

    @_seguro
    def adicionar_vst(self, id_, caminho=None):
        if not caminho:
            pasta = next((str(p) for p in fx.PASTAS_VST3 if p and p.is_dir()), "")
            esc = self._dialogo("abrir", directory=pasta, file_types=("Plugin VST3 (*.vst3)",))
            if not esc:
                return {"cancelado": True}
            caminho = esc[0] if isinstance(esc, list) else esc
        ef = fx.carregar_vst3(caminho)
        self._motor.adicionar_efeito(id_, ef)
        return self._motor.faixa(id_).info()

    @_seguro
    def aplicar_preset(self, id_, nome):
        self._motor.aplicar_preset(id_, nome)
        return self._motor.faixa(id_).info()

    @_seguro
    def remover_efeito(self, id_, ef_id):
        f, ef = self._motor.efeito(id_, ef_id)
        f.efeitos = [e for e in f.efeitos if e.id != ef_id]
        f.refazer_cadeia()
        return f.info()

    @_seguro
    def mover_efeito(self, id_, ef_id, direcao):
        f, ef = self._motor.efeito(id_, ef_id)
        lst = list(f.efeitos)
        i = lst.index(ef)
        j = i + int(direcao)
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            f.efeitos = lst
            f.refazer_cadeia()
        return f.info()

    @_seguro
    def alternar_efeito(self, id_, ef_id):
        f, ef = self._motor.efeito(id_, ef_id)
        ef.ativo = not ef.ativo
        f.refazer_cadeia()
        return f.info()

    @_seguro
    def ajustar_efeito(self, id_, ef_id, param, valor):
        f, ef = self._motor.efeito(id_, ef_id)
        ef.ajustar(param, valor)

    @_seguro
    def abrir_editor(self, id_, ef_id):
        f, ef = self._motor.efeito(id_, ef_id)
        if ef.tipo != "vst3":
            raise RuntimeError("Só plugins VST3 têm janela própria.")
        if ef.id in self._editores and self._editores[ef.id].is_alive():
            return {"aberto": True}
        t = threading.Thread(target=ef.plugin.show_editor, daemon=True)
        t.start()
        self._editores[ef.id] = t

    # ------------------------------------------------------------- import/export
    @_seguro
    def importar(self):
        arqs = self._dialogo("abrir", allow_multiple=True, file_types=TIPOS_AUDIO)
        if not arqs:
            return {"cancelado": True}
        novas = []
        for a in arqs:
            audio = self._motor.ler_arquivo(a)
            novas.append(self._motor.nova_faixa(Path(a).stem, audio).info())
        return {"faixas": novas}

    @_seguro
    def exportar_mix(self):
        nome = (Path(self._projeto).name if self._projeto else "mix") + ".wav"
        destino = self._dialogo("salvar", save_filename=nome, file_types=("WAV (*.wav)",))
        if not destino:
            return {"cancelado": True}
        destino = destino[0] if isinstance(destino, list) else destino
        if not destino.lower().endswith(".wav"):
            destino += ".wav"
        self._motor.parar()
        return {"arquivo": projeto.exportar_wav(self._motor, destino)}

    @_seguro
    def exportar_faixa(self, id_):
        f = self._motor.faixa(id_)
        destino = self._dialogo("salvar", save_filename=f"{f.nome}.wav", file_types=("WAV (*.wav)",))
        if not destino:
            return {"cancelado": True}
        destino = destino[0] if isinstance(destino, list) else destino
        if not destino.lower().endswith(".wav"):
            destino += ".wav"
        return {"arquivo": projeto.exportar_faixa(self._motor, id_, destino)}

    # ------------------------------------------------------------------ projeto
    @_seguro
    def novo_projeto(self):
        self._motor.parar()
        self._motor.faixas = []
        self._motor.pos = 0
        self._motor.loop = False
        self._projeto = None
        self._motor.nova_faixa()

    @_seguro
    def salvar(self, como=False):
        if self._motor.gravando:
            raise RuntimeError("Pare a gravação antes de salvar.")
        if como or not self._projeto:
            base = self._ler_config().get("pasta_projetos", str(self._dados.parent / "projetos"))
            Path(base).mkdir(parents=True, exist_ok=True)
            pasta = self._dialogo("pasta", directory=base)
            if not pasta:
                return {"cancelado": True}
            pasta = pasta[0] if isinstance(pasta, list) else pasta
            if not (Path(pasta) / "projeto.json").exists() and any(Path(pasta).iterdir()):
                # pasta com outras coisas: cria uma subpasta para o projeto
                n = 1
                while (Path(pasta) / f"Projeto {n}").exists():
                    n += 1
                pasta = str(Path(pasta) / f"Projeto {n}")
            self._projeto = pasta
            self._gravar_config(pasta_projetos=str(Path(pasta).parent))
        projeto.salvar(self._motor, self._projeto)
        self._gravar_config(ultimo_projeto=self._projeto)
        return {"projeto": self._projeto}

    @_seguro
    def abrir_projeto(self, pasta=None):
        if not pasta:
            base = self._ler_config().get("pasta_projetos", str(self._dados.parent / "projetos"))
            esc = self._dialogo("abrir", directory=base, file_types=("Projeto JARVIS Studio (projeto.json)",))
            if not esc:
                return {"cancelado": True}
            pasta = esc[0] if isinstance(esc, list) else esc
        avisos = projeto.abrir(self._motor, pasta)
        p = Path(pasta)
        self._projeto = str(p.parent if p.is_file() else p)
        self._gravar_config(ultimo_projeto=self._projeto)
        return {"projeto": self._projeto, "avisos": avisos}

    @_seguro
    def ultimo_projeto(self):
        p = self._ler_config().get("ultimo_projeto")
        return {"projeto": p if p and (Path(p) / "projeto.json").exists() else None}

    # ------------------------------------------------------------ JARVIS MUSIC
    @_seguro
    def musica_abrir(self, escolher=False):
        """Liga o JARVIS MUSIC e devolve o endereço da tela dele."""
        raiz = Path(__file__).resolve().parent.parent
        pasta = None if escolher else musica.achar(raiz, self._ler_config().get("pasta_jarvis_music"))
        if not pasta:
            esc = self._dialogo("pasta")
            if not esc:
                return {"cancelado": True}
            pasta = esc[0] if isinstance(esc, list) else esc
            if not musica.valida(pasta):
                raise RuntimeError("Essa pasta não é o JARVIS MUSIC (não tem backend\\servidor.py).")
        self._gravar_config(pasta_jarvis_music=str(pasta))
        return {"url": self._musica.iniciar(pasta), "pasta": str(pasta)}

    @_seguro
    def musica_analises(self):
        return {"analises": self._musica.analises()}

    @_seguro
    def musica_importar(self, id_):
        """Traz os stems de uma análise como faixas do estúdio."""
        est, faixas = self._musica.baixar_faixas(id_)
        if not faixas:
            raise RuntimeError("Essa análise ainda não tem faixas separadas.")
        m = self._motor
        vazio = not any(f.audio is not None for f in m.faixas)
        vazias = []
        if vazio:
            # projeto sem nada gravado: a música vem primeiro e as faixas vazias
            # (a da guitarra, armada) ficam embaixo dela
            vazias, m.faixas = m.faixas, []
            bpm = (est.get("ritmo") or {}).get("bpm")
            if bpm:
                m.bpm = float(round(bpm, 1))
        novas = []
        for rotulo, caminho in faixas:
            f = m.nova_faixa(rotulo, m.ler_arquivo(caminho))
            novas.append(f.info())
            try:
                caminho.unlink()
            except OSError:
                pass
        m.faixas = m.faixas + vazias
        return {"faixas": novas, "musica": est.get("arquivo"), "bpm": m.bpm}
