"""Motor de áudio do JARVIS Studio.

Roda fora do navegador, direto na placa de som (ASIO de preferência), e faz
tudo dentro de um único callback: toca as faixas, passa cada uma pela cadeia de
efeitos, monitora a entrada da faixa armada, grava e soma o metrônomo.
"""
import os

os.environ.setdefault("SD_ENABLE_ASIO", "1")   # usa a PortAudio com ASIO que vem no sounddevice

import gc
import math
import threading
import time
import uuid

import numpy as np
import pedalboard as pb
import sounddevice as sd

from . import efeitos as fx

CORES = ["#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa", "#fb923c", "#4ade80"]
PICO_PASSO = 256        # amostras por ponto da forma de onda


def db_para_lin(db):
    return 0.0 if db <= -60 else 10 ** (db / 20)


class Faixa:
    def __init__(self, nome, cor):
        self.id = uuid.uuid4().hex[:8]
        self.nome = nome
        self.cor = cor
        self.audio = None           # float32 (2, N) ou None
        self.inicio = 0             # amostra da timeline onde o áudio começa
        self.volume_db = 0.0
        self.pan = 0.0
        self.mudo = False
        self.solo = False
        self.armada = False
        self.monitor = False
        self.entrada = [0]          # canais da placa: [0] mono, [0, 1] estéreo
        self.efeitos = []
        self.cadeia = None          # pb.Pedalboard só com os efeitos ativos
        self.versao = 0             # muda quando o áudio muda (a tela busca a forma de onda de novo)
        self.medidor = 0.0
        self._picos = None

    @property
    def fim(self):
        return self.inicio + (0 if self.audio is None else self.audio.shape[1])

    def refazer_cadeia(self):
        ativos = [e.plugin for e in self.efeitos if e.ativo]
        self.cadeia = pb.Pedalboard(ativos) if ativos else None

    def trocar_audio(self, audio, inicio=0):
        self.audio = None if audio is None else np.ascontiguousarray(audio, dtype=np.float32)
        self.inicio = int(inicio)
        self.versao += 1
        self._picos = None

    def picos(self):
        if self._picos is None:
            if self.audio is None:
                self._picos = []
            else:
                mono = np.abs(self.audio).max(axis=0)
                n = len(mono) // PICO_PASSO * PICO_PASSO
                p = mono[:n].reshape(-1, PICO_PASSO).max(axis=1) if n else np.zeros(0)
                if len(mono) > n:
                    p = np.append(p, mono[n:].max())
                self._picos = np.clip(p * 255, 0, 255).astype(np.uint8).tolist()
        return self._picos

    def info(self):
        return {
            "id": self.id, "nome": self.nome, "cor": self.cor, "inicio": self.inicio,
            "duracao": 0 if self.audio is None else self.audio.shape[1],
            "volume_db": self.volume_db, "pan": self.pan, "mudo": self.mudo, "solo": self.solo,
            "armada": self.armada, "monitor": self.monitor, "entrada": self.entrada,
            "efeitos": [e.info() for e in self.efeitos], "versao": self.versao,
        }


class _ThreadPlaca:
    """Thread fixo que abre e fecha a placa.

    O driver ASIO é um objeto COM: só carrega num thread com COM inicializado
    em apartment single-threaded (STA). O app chama o motor de threads do
    servidor, sem COM, e aí o driver falha com "Failed to load ASIO driver".
    Por isso tudo que toca no stream roda aqui, sempre no mesmo thread.
    """

    def __init__(self):
        import queue
        self._fila = queue.Queue()
        threading.Thread(target=self._laco, name="placa", daemon=True).start()

    def _laco(self):
        if os.name == "nt":
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)   # COINIT_APARTMENTTHREADED
        while True:
            fn, pronto, res = self._fila.get()
            try:
                res["v"] = fn()
            except BaseException as e:
                res["e"] = e
            pronto.set()

    def rodar(self, fn):
        if threading.current_thread().name == "placa":
            return fn()
        pronto, res = threading.Event(), {}
        self._fila.put((fn, pronto, res))
        pronto.wait()
        if "e" in res:
            raise res["e"]
        return res.get("v")


_PLACA = _ThreadPlaca()


def _clique(sr, freq, dur=0.03):
    t = np.arange(int(sr * dur)) / sr
    return (np.sin(2 * np.pi * freq * t) * np.exp(-t * 90)).astype(np.float32)


class Motor:
    def __init__(self):
        self.sr = 48000
        self.bloco = 256
        self.stream = None
        self.n_entradas = 0
        self.n_saidas = 2
        self.config = {}
        self.latencia = (0.0, 0.0)
        self.ajuste_latencia = 0     # amostras extras de compensação, se o usuário quiser afinar

        self.faixas = []             # lista trocada inteira (copy-on-write), o callback só lê
        self.tocando = False
        self.gravando = False
        self.pos = 0                 # amostra atual da timeline (pode ser negativa na contagem)
        self.bpm = 120.0
        self.compasso = 4
        self.metronomo = False
        self.metro_volume = 0.6
        self.contagem = True
        self.loop = False
        self.loop_ini = 0
        self.loop_fim = 0
        self.master_db = 0.0
        self.medidor_master = 0.0
        self.medidor_entrada = []
        self.xruns = 0
        self.erro = None
        self.renderizando = False

        self._rec = {}               # id da faixa -> lista de blocos (2, n)
        self._rec_inicio = 0
        self._cliques = (_clique(self.sr, 1600), _clique(self.sr, 1000))
        self._lock = threading.Lock()

    # ------------------------------------------------------------ dispositivos
    @staticmethod
    def dispositivos():
        apis = sd.query_hostapis()
        lista = []
        for i, d in enumerate(sd.query_devices()):
            lista.append({
                "id": i, "nome": d["name"], "api": apis[d["hostapi"]]["name"],
                "entradas": d["max_input_channels"], "saidas": d["max_output_channels"],
                "sr_padrao": d["default_samplerate"],
            })
        return {"apis": [a["name"] for a in apis], "dispositivos": lista}

    @staticmethod
    def _achar(nome, api):
        if not nome:
            return None
        for d in Motor.dispositivos()["dispositivos"]:
            if d["nome"] == nome and d["api"] == api:
                return d
        return None

    def abrir(self, config):
        """config: api, entrada, saida (nomes), sr, bloco, exclusivo."""
        _PLACA.rodar(lambda: self._abrir(config))

    def _abrir(self, config):
        self.fechar()
        api = config.get("api")
        ent = self._achar(config.get("entrada"), api)
        sai = self._achar(config.get("saida"), api)
        if sai is None:
            raise RuntimeError("Escolha uma saída de áudio.")
        sr = int(config.get("sr") or 48000)
        bloco = int(config.get("bloco") or 256)
        if api == "ASIO" and ent and ent["id"] != sai["id"]:
            raise RuntimeError("No ASIO a entrada e a saída precisam ser a mesma placa.")

        if sr != self.sr:
            self._reamostrar_tudo(sr)
        self.sr, self.bloco = sr, bloco
        self._cliques = (_clique(sr, 1600), _clique(sr, 1000))
        self.n_entradas = min(ent["entradas"], 16) if ent else 0
        self.n_saidas = min(sai["saidas"], 2)

        extra = None
        if api and "WASAPI" in api and config.get("exclusivo"):
            w = sd.WasapiSettings(exclusive=True)
            extra = (w, w) if ent else w
        gc.collect()
        if ent:
            self.stream = sd.Stream(
                device=(ent["id"], sai["id"]), samplerate=sr, blocksize=bloco,
                channels=(self.n_entradas, self.n_saidas), dtype="float32",
                latency=bloco / sr, callback=self._callback, extra_settings=extra)
        else:
            self.stream = sd.OutputStream(
                device=sai["id"], samplerate=sr, blocksize=bloco, channels=self.n_saidas,
                dtype="float32", latency=bloco / sr, callback=self._callback_saida,
                extra_settings=extra)
        self.stream.start()
        lat = self.stream.latency
        self.latencia = lat if isinstance(lat, tuple) else (0.0, lat)
        self.config = dict(config, sr=sr, bloco=bloco)
        self.erro = None

    def fechar(self):
        _PLACA.rodar(self._fechar)

    def _fechar(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    @property
    def compensacao(self):
        return int(round((self.latencia[0] + self.latencia[1]) * self.sr)) + self.ajuste_latencia

    # ---------------------------------------------------------------- callback
    def _callback(self, indata, outdata, frames, tempo, status):
        if status:
            self.xruns += 1
        try:
            out = self.processar(indata.T, frames)
            outdata[:, :out.shape[0]] = out.T
            if outdata.shape[1] > out.shape[0]:
                outdata[:, out.shape[0]:] = 0
        except Exception as e:   # nunca deixa o callback morrer
            outdata.fill(0)
            self.erro = f"{type(e).__name__}: {e}"

    def _callback_saida(self, outdata, frames, tempo, status):
        self._callback(np.zeros((frames, 0), np.float32), outdata, frames, tempo, status)

    def processar(self, entrada, frames):
        """entrada: (canais, frames). Devolve (2, frames)."""
        sr = self.sr
        out = np.zeros((2, frames), np.float32)
        if entrada.shape[0]:
            self.medidor_entrada = np.abs(entrada).max(axis=1).tolist()
        if self.renderizando:
            return out

        faixas = self.faixas
        tocando = self.tocando
        gravando = self.gravando
        pos = self.pos
        algum_solo = any(f.solo for f in faixas)

        for f in faixas:
            ouvir_entrada = f.armada and f.monitor and entrada.shape[0] > 0
            if not tocando and not ouvir_entrada:
                f.medidor = 0.0
                continue
            sinal = np.zeros((2, frames), np.float32)

            # áudio já gravado (a faixa que está gravando não toca o take antigo)
            if tocando and f.audio is not None and not (gravando and f.armada):
                a, b = pos - f.inicio, pos - f.inicio + frames
                n = f.audio.shape[1]
                if b > 0 and a < n:
                    i0, i1 = max(a, 0), min(b, n)
                    sinal[:, i0 - a:i1 - a] = f.audio[:, i0:i1]

            if f.armada and entrada.shape[0]:
                bruto = self._entrada_da_faixa(entrada, f)
                if gravando:
                    self._rec.setdefault(f.id, []).append(bruto.copy())
                if ouvir_entrada:
                    sinal += bruto

            cadeia = f.cadeia
            if cadeia is not None:
                proc = cadeia.process(sinal, sr, reset=False)
                if proc.shape[1] < frames:     # plugin com latência devolveu menos
                    pad = np.zeros((2, frames), np.float32)
                    pad[:, frames - proc.shape[1]:] = proc
                    proc = pad
                sinal = proc

            audivel = not f.mudo and (f.solo or not algum_solo)
            if not audivel:
                f.medidor = 0.0
                continue
            g = db_para_lin(f.volume_db)
            sinal[0] *= g * min(1.0, 1.0 - f.pan)
            sinal[1] *= g * min(1.0, 1.0 + f.pan)
            f.medidor = float(np.abs(sinal).max())
            out += sinal

        if tocando and self.metronomo:
            out += self._metronomo(pos, frames)[None, :] * self.metro_volume

        out *= db_para_lin(self.master_db)
        np.clip(out, -1.0, 1.0, out=out)
        self.medidor_master = float(np.abs(out).max())

        if tocando:
            self.pos = pos + frames
            if self.loop and not gravando and self.loop_fim > self.loop_ini and self.pos >= self.loop_fim:
                self.pos = self.loop_ini
        return out

    def _entrada_da_faixa(self, entrada, f):
        canais = [c for c in f.entrada if c < entrada.shape[0]] or [0]
        if len(canais) == 1:
            m = entrada[canais[0]]
            return np.vstack([m, m]).astype(np.float32)
        return entrada[canais[:2]].astype(np.float32)

    def _metronomo(self, pos, frames):
        batida = self.sr * 60.0 / self.bpm
        idx = np.arange(pos, pos + frames)
        n = np.floor(idx / batida)
        fase = (idx - n * batida).astype(np.int64)
        acento, normal = self._cliques
        res = np.zeros(frames, np.float32)
        m = fase < len(normal)
        if m.any():
            forte = (n.astype(np.int64) % self.compasso) == 0
            res[m & forte] = acento[fase[m & forte]]
            res[m & ~forte] = normal[fase[m & ~forte]]
        return res

    # --------------------------------------------------------------- transporte
    def tocar(self):
        if self.stream is None:
            raise RuntimeError("Abra a placa de áudio em Configurar áudio.")
        self.tocando = True

    def pausar(self):
        self._encerrar_gravacao()
        self.tocando = False

    def parar(self):
        self.pausar()

    def ir_para(self, amostra):
        self.pos = max(0, int(amostra))

    def gravar(self):
        if self.stream is None:
            raise RuntimeError("Abra a placa de áudio em Configurar áudio.")
        if not any(f.armada for f in self.faixas):
            raise RuntimeError("Arme uma faixa para gravar (botão vermelho da faixa).")
        if self.n_entradas == 0:
            raise RuntimeError("Nenhuma entrada de áudio aberta. Escolha a entrada em Configurar áudio.")
        if self.gravando:
            return
        self._rec = {}
        if self.contagem and not self.tocando:
            self.pos -= int(round(self.compasso * self.sr * 60.0 / self.bpm))
        self._rec_inicio = self.pos
        self.gravando = True
        self.tocando = True

    def _encerrar_gravacao(self):
        if not self.gravando:
            return
        self.gravando = False
        time.sleep(3 * self.bloco / self.sr + 0.005)   # deixa o último bloco do callback terminar
        blocos, self._rec = self._rec, {}
        comp = self.compensacao
        for f in self.faixas:
            partes = blocos.get(f.id)
            if not partes:
                continue
            novo = np.concatenate(partes, axis=1)
            inicio = self._rec_inicio - comp     # o que entrou chegou atrasado: puxa para trás
            if inicio < 0:
                novo = novo[:, -inicio:]
                inicio = 0
            if novo.shape[1]:
                self._sobrepor(f, novo, inicio)
        if self.pos < 0:
            self.pos = 0

    @staticmethod
    def _sobrepor(f, novo, inicio):
        """Grava por cima só do trecho novo, mantendo o resto do take antigo."""
        if f.audio is None:
            f.trocar_audio(novo, inicio)
            return
        ini = min(f.inicio, inicio)
        fim = max(f.fim, inicio + novo.shape[1])
        buf = np.zeros((2, fim - ini), np.float32)
        buf[:, f.inicio - ini:f.fim - ini] = f.audio
        buf[:, inicio - ini:inicio - ini + novo.shape[1]] = novo
        f.trocar_audio(buf, ini)

    # ------------------------------------------------------------------- faixas
    def nova_faixa(self, nome=None, audio=None, inicio=0):
        f = Faixa(nome or f"Faixa {len(self.faixas) + 1}", CORES[len(self.faixas) % len(CORES)])
        if audio is not None:
            f.trocar_audio(audio, inicio)
        else:
            f.armada = not any(x.armada for x in self.faixas)
            f.monitor = f.armada
        self.faixas = self.faixas + [f]
        return f

    def faixa(self, id_):
        for f in self.faixas:
            if f.id == id_:
                return f
        raise KeyError(id_)

    def remover_faixa(self, id_):
        self.faixas = [f for f in self.faixas if f.id != id_]

    def mover_faixa(self, id_, direcao):
        lst = list(self.faixas)
        i = next(k for k, f in enumerate(lst) if f.id == id_)
        j = i + direcao
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self.faixas = lst

    def duracao(self):
        return max((f.fim for f in self.faixas), default=0)

    # ------------------------------------------------------------------ efeitos
    def adicionar_efeito(self, id_, efeito, posicao=None):
        f = self.faixa(id_)
        lst = list(f.efeitos)
        lst.insert(len(lst) if posicao is None else posicao, efeito)
        f.efeitos = lst
        f.refazer_cadeia()

    def aplicar_preset(self, id_, nome):
        f = self.faixa(id_)
        f.efeitos = [fx.criar(t, p) for t, p in fx.PRESETS[nome]]
        f.refazer_cadeia()

    def efeito(self, id_, ef_id):
        f = self.faixa(id_)
        return f, next(e for e in f.efeitos if e.id == ef_id)

    # ------------------------------------------------------------- import/export
    def ler_arquivo(self, caminho):
        with pb.io.AudioFile(str(caminho)).resampled_to(self.sr) as arq:
            audio = arq.read(arq.frames)
        if audio.shape[0] == 1:
            audio = np.vstack([audio, audio])
        return audio[:2].astype(np.float32)

    def renderizar(self, cauda_s=2.0):
        """Mixagem final com todos os efeitos (offline)."""
        faixas = self.faixas
        fim = self.duracao()
        if fim == 0:
            raise RuntimeError("Não há nada gravado para exportar.")
        total = fim + int(cauda_s * self.sr)
        mix = np.zeros((2, total), np.float32)
        algum_solo = any(f.solo for f in faixas)
        self.renderizando = True
        try:
            time.sleep(3 * self.bloco / self.sr)
            for f in faixas:
                if f.audio is None or f.mudo or (algum_solo and not f.solo):
                    continue
                sinal = np.zeros((2, total), np.float32)
                sinal[:, f.inicio:f.fim] = f.audio
                if f.cadeia is not None:
                    proc = f.cadeia.process(sinal, self.sr, reset=True)
                    sinal = np.zeros((2, total), np.float32)
                    sinal[:, total - proc.shape[1]:] = proc
                g = db_para_lin(f.volume_db)
                sinal[0] *= g * min(1.0, 1.0 - f.pan)
                sinal[1] *= g * min(1.0, 1.0 + f.pan)
                mix += sinal
                if f.cadeia is not None:
                    f.cadeia.reset()
        finally:
            self.renderizando = False
        mix *= db_para_lin(self.master_db)
        return np.clip(mix, -1.0, 1.0)

    def _reamostrar_tudo(self, novo_sr):
        if not any(f.audio is not None for f in self.faixas):
            return
        import soxr
        r = novo_sr / self.sr
        for f in self.faixas:
            if f.audio is not None:
                f.trocar_audio(soxr.resample(f.audio.T, self.sr, novo_sr).T, round(f.inicio * r))
        self.pos = round(self.pos * r)
        self.loop_ini, self.loop_fim = round(self.loop_ini * r), round(self.loop_fim * r)

    # -------------------------------------------------------------------- estado
    def estado(self):
        cpu = 0.0
        try:
            cpu = float(self.stream.cpu_load) if self.stream else 0.0
        except Exception:
            pass
        return {
            "pos": self.pos, "tocando": self.tocando, "gravando": self.gravando,
            "rec_inicio": self._rec_inicio, "sr": self.sr,
            "medidores": {f.id: f.medidor for f in self.faixas},
            "master": self.medidor_master,
            "entrada": self.medidor_entrada,
            "cpu": cpu, "xruns": self.xruns, "erro": self.erro,
            "aberto": self.stream is not None,
        }

    def resumo(self):
        return {
            "sr": self.sr, "bloco": self.bloco, "bpm": self.bpm, "compasso": self.compasso,
            "metronomo": self.metronomo, "metro_volume": self.metro_volume,
            "contagem": self.contagem, "loop": self.loop, "loop_ini": self.loop_ini,
            "loop_fim": self.loop_fim, "master_db": self.master_db,
            "n_entradas": self.n_entradas, "config": self.config,
            "latencia_ms": round((self.latencia[0] + self.latencia[1]) * 1000, 1),
            "compensacao": self.compensacao, "ajuste_latencia": self.ajuste_latencia,
            "aberto": self.stream is not None,
            "faixas": [f.info() for f in self.faixas],
        }
