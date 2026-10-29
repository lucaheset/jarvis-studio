"""Catálogo de efeitos (FX) do estúdio.

Os efeitos nativos vêm do pedalboard (Spotify), que roda em C++ e libera o GIL,
então dá para usar em tempo real dentro do callback de áudio. Plugins VST3 de
terceiros também entram pelo pedalboard.
"""
import base64
import os
import uuid
from pathlib import Path

import pedalboard as pb

# tipo -> (classe, nome mostrado, [(parâmetro, rótulo, mín, máx, passo, unidade)])
CATALOGO = {
    "gate": (pb.NoiseGate, "Noise gate", [
        ("threshold_db", "Limiar", -90, 0, 1, "dB"),
        ("ratio", "Razão", 1, 20, 0.5, ":1"),
        ("attack_ms", "Ataque", 0.1, 50, 0.1, "ms"),
        ("release_ms", "Soltura", 5, 500, 1, "ms"),
    ]),
    "passa_altas": (pb.HighpassFilter, "Corta graves (HPF)", [
        ("cutoff_frequency_hz", "Frequência", 20, 1000, 1, "Hz"),
    ]),
    "graves": (pb.LowShelfFilter, "EQ graves", [
        ("cutoff_frequency_hz", "Frequência", 40, 500, 1, "Hz"),
        ("gain_db", "Ganho", -18, 18, 0.5, "dB"),
        ("q", "Q", 0.3, 4, 0.05, ""),
    ]),
    "medios": (pb.PeakFilter, "EQ médios", [
        ("cutoff_frequency_hz", "Frequência", 200, 6000, 10, "Hz"),
        ("gain_db", "Ganho", -18, 18, 0.5, "dB"),
        ("q", "Q", 0.3, 8, 0.05, ""),
    ]),
    "agudos": (pb.HighShelfFilter, "EQ agudos", [
        ("cutoff_frequency_hz", "Frequência", 1500, 16000, 50, "Hz"),
        ("gain_db", "Ganho", -18, 18, 0.5, "dB"),
        ("q", "Q", 0.3, 4, 0.05, ""),
    ]),
    "passa_baixas": (pb.LowpassFilter, "Corta agudos (LPF)", [
        ("cutoff_frequency_hz", "Frequência", 1000, 20000, 50, "Hz"),
    ]),
    "compressor": (pb.Compressor, "Compressor", [
        ("threshold_db", "Limiar", -60, 0, 0.5, "dB"),
        ("ratio", "Razão", 1, 20, 0.5, ":1"),
        ("attack_ms", "Ataque", 0.1, 100, 0.1, "ms"),
        ("release_ms", "Soltura", 10, 1000, 5, "ms"),
    ]),
    "distorcao": (pb.Distortion, "Distorção", [
        ("drive_db", "Drive", 0, 60, 0.5, "dB"),
    ]),
    "clipping": (pb.Clipping, "Clipping", [
        ("threshold_db", "Limiar", -40, 0, 0.5, "dB"),
    ]),
    "bitcrush": (pb.Bitcrush, "Bitcrush", [
        ("bit_depth", "Bits", 2, 16, 0.5, "bits"),
    ]),
    "chorus": (pb.Chorus, "Chorus", [
        ("rate_hz", "Velocidade", 0.05, 10, 0.05, "Hz"),
        ("depth", "Profundidade", 0, 1, 0.01, ""),
        ("centre_delay_ms", "Atraso", 1, 30, 0.5, "ms"),
        ("feedback", "Realimentação", 0, 0.95, 0.01, ""),
        ("mix", "Mix", 0, 1, 0.01, ""),
    ]),
    "phaser": (pb.Phaser, "Phaser", [
        ("rate_hz", "Velocidade", 0.05, 10, 0.05, "Hz"),
        ("depth", "Profundidade", 0, 1, 0.01, ""),
        ("centre_frequency_hz", "Frequência", 100, 5000, 10, "Hz"),
        ("feedback", "Realimentação", 0, 0.95, 0.01, ""),
        ("mix", "Mix", 0, 1, 0.01, ""),
    ]),
    "delay": (pb.Delay, "Delay", [
        ("delay_seconds", "Tempo", 0.01, 2, 0.005, "s"),
        ("feedback", "Repetições", 0, 0.95, 0.01, ""),
        ("mix", "Mix", 0, 1, 0.01, ""),
    ]),
    "reverb": (pb.Reverb, "Reverb", [
        ("room_size", "Sala", 0, 1, 0.01, ""),
        ("damping", "Abafar", 0, 1, 0.01, ""),
        ("wet_level", "Efeito", 0, 1, 0.01, ""),
        ("dry_level", "Original", 0, 1, 0.01, ""),
        ("width", "Largura", 0, 1, 0.01, ""),
    ]),
    "ganho": (pb.Gain, "Ganho", [
        ("gain_db", "Ganho", -24, 24, 0.5, "dB"),
    ]),
    "limitador": (pb.Limiter, "Limitador", [
        ("threshold_db", "Limiar", -30, 0, 0.5, "dB"),
        ("release_ms", "Soltura", 10, 1000, 5, "ms"),
    ]),
}

# cadeias prontas: (tipo, {parâmetro: valor})
PRESETS = {
    "Guitarra limpa": [
        ("gate", {"threshold_db": -60}),
        ("passa_altas", {"cutoff_frequency_hz": 90}),
        ("compressor", {"threshold_db": -20, "ratio": 3}),
        ("chorus", {"rate_hz": 0.8, "depth": 0.2, "mix": 0.3}),
        ("reverb", {"room_size": 0.35, "wet_level": 0.2, "dry_level": 0.8}),
    ],
    "Guitarra distorcida": [
        ("gate", {"threshold_db": -50, "ratio": 10}),
        ("passa_altas", {"cutoff_frequency_hz": 100}),
        ("distorcao", {"drive_db": 32}),
        ("medios", {"cutoff_frequency_hz": 800, "gain_db": 3, "q": 0.8}),
        ("passa_baixas", {"cutoff_frequency_hz": 7000}),
        ("delay", {"delay_seconds": 0.38, "feedback": 0.25, "mix": 0.15}),
        ("reverb", {"room_size": 0.3, "wet_level": 0.15, "dry_level": 0.85}),
    ],
    "Voz": [
        ("passa_altas", {"cutoff_frequency_hz": 100}),
        ("compressor", {"threshold_db": -18, "ratio": 4, "attack_ms": 5, "release_ms": 120}),
        ("agudos", {"cutoff_frequency_hz": 6000, "gain_db": 3}),
        ("reverb", {"room_size": 0.4, "wet_level": 0.18, "dry_level": 0.85}),
    ],
    "Baixo": [
        ("compressor", {"threshold_db": -22, "ratio": 4}),
        ("graves", {"cutoff_frequency_hz": 100, "gain_db": 3}),
        ("passa_baixas", {"cutoff_frequency_hz": 5000}),
    ],
}

PASTAS_VST3 = [
    Path(os.environ.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files")) / "VST3",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Common" / "VST3",
]


class Efeito:
    """Um efeito na cadeia de uma faixa: nativo ou VST3."""

    def __init__(self, tipo, plugin, caminho=None, nome_vst=None):
        self.id = uuid.uuid4().hex[:8]
        self.tipo = tipo            # chave do CATALOGO ou "vst3"
        self.plugin = plugin
        self.caminho = caminho      # só VST3
        self.nome_vst = nome_vst
        self.ativo = True

    @property
    def nome(self):
        if self.tipo == "vst3":
            return self.plugin.name
        return CATALOGO[self.tipo][1]

    def params(self):
        if self.tipo == "vst3":
            return []
        return [
            {"nome": p, "rotulo": r, "min": a, "max": b, "passo": s, "unidade": u,
             "valor": float(getattr(self.plugin, p))}
            for p, r, a, b, s, u in CATALOGO[self.tipo][2]
        ]

    def ajustar(self, nome, valor):
        if self.tipo == "vst3":
            return
        validos = {p[0] for p in CATALOGO[self.tipo][2]}
        if nome in validos:
            setattr(self.plugin, nome, float(valor))

    def info(self):
        return {"id": self.id, "tipo": self.tipo, "nome": self.nome, "ativo": self.ativo,
                "params": self.params(), "vst": self.tipo == "vst3"}

    def salvar(self):
        d = {"tipo": self.tipo, "ativo": self.ativo}
        if self.tipo == "vst3":
            d["caminho"] = self.caminho
            d["nome_vst"] = self.nome_vst
            try:
                d["estado"] = base64.b64encode(self.plugin.raw_state).decode()
            except Exception:
                pass
        else:
            d["params"] = {p["nome"]: p["valor"] for p in self.params()}
        return d


def criar(tipo, params=None):
    cls = CATALOGO[tipo][0]
    ef = Efeito(tipo, cls())
    for k, v in (params or {}).items():
        ef.ajustar(k, v)
    return ef


def carregar_vst3(caminho, nome_vst=None, estado=None):
    if not nome_vst:
        nomes = pb.VST3Plugin.get_plugin_names_for_file(caminho)
        nome_vst = nomes[0] if nomes else None
    plugin = pb.load_plugin(caminho, plugin_name=nome_vst)
    if getattr(plugin, "is_instrument", False) and not getattr(plugin, "is_effect", True):
        raise ValueError(f"{plugin.name} é um instrumento (VSTi). Por enquanto só entram efeitos.")
    if estado:
        try:
            plugin.raw_state = base64.b64decode(estado)
        except Exception:
            pass
    return Efeito("vst3", plugin, caminho=str(caminho), nome_vst=nome_vst)


def de_dict(d):
    if d["tipo"] == "vst3":
        ef = carregar_vst3(d["caminho"], d.get("nome_vst"), d.get("estado"))
    else:
        ef = criar(d["tipo"], d.get("params"))
    ef.ativo = d.get("ativo", True)
    return ef


def listar_vst3():
    """Plugins VST3 instalados nas pastas padrão do Windows (nunca falha)."""
    achados = []
    for pasta in PASTAS_VST3:
        try:
            if not (str(pasta) and pasta.is_dir()):
                continue
            for raiz, dirs, arquivos in os.walk(pasta, onerror=lambda e: None):
                # um .vst3 pode ser pasta (bundle): entra na lista e não desce nela
                for d in [d for d in dirs if d.lower().endswith(".vst3")]:
                    achados.append({"nome": d[:-5], "caminho": os.path.join(raiz, d)})
                    dirs.remove(d)
                for a in arquivos:
                    if a.lower().endswith(".vst3"):
                        achados.append({"nome": a[:-5], "caminho": os.path.join(raiz, a)})
        except Exception:
            continue
    return sorted(achados, key=lambda x: x["nome"].lower())


def catalogo():
    return {
        "nativos": [{"tipo": k, "nome": v[1]} for k, v in CATALOGO.items()],
        "presets": list(PRESETS),
    }
