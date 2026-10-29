"""Salvar e abrir projetos: uma pasta com projeto.json e um .wav por faixa."""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from . import efeitos as fx

VERSAO = 1


def salvar(motor, pasta):
    pasta = Path(pasta)
    (pasta / "audio").mkdir(parents=True, exist_ok=True)
    faixas = []
    usados = set()
    for f in motor.faixas:
        arquivo = None
        if f.audio is not None:
            arquivo = f"audio/{f.id}.wav"
            sf.write(pasta / arquivo, f.audio.T, motor.sr, subtype="FLOAT")
            usados.add(f"{f.id}.wav")
        faixas.append({
            "nome": f.nome, "cor": f.cor, "arquivo": arquivo, "inicio": f.inicio,
            "volume_db": f.volume_db, "pan": f.pan, "mudo": f.mudo, "solo": f.solo,
            "entrada": f.entrada, "monitor": f.monitor,
            "efeitos": [e.salvar() for e in f.efeitos],
        })
    # tira os .wav de faixas que foram apagadas
    for velho in (pasta / "audio").glob("*.wav"):
        if velho.name not in usados:
            velho.unlink(missing_ok=True)
    dados = {
        "versao": VERSAO, "sr": motor.sr, "bpm": motor.bpm, "compasso": motor.compasso,
        "metronomo": motor.metronomo, "contagem": motor.contagem,
        "loop": motor.loop, "loop_ini": motor.loop_ini, "loop_fim": motor.loop_fim,
        "master_db": motor.master_db, "faixas": faixas,
    }
    (pasta / "projeto.json").write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(pasta)


def abrir(motor, pasta):
    """Carrega o projeto. Devolve a lista de avisos (plugins que não abriram etc.)."""
    pasta = Path(pasta)
    if pasta.is_file():
        pasta = pasta.parent
    dados = json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))
    avisos = []
    motor.parar()
    motor.faixas = []
    motor.pos = 0
    for k in ("bpm", "compasso", "metronomo", "contagem", "loop", "loop_ini", "loop_fim", "master_db"):
        if k in dados:
            setattr(motor, k, dados[k])
    r = motor.sr / dados.get("sr", motor.sr)
    for d in dados["faixas"]:
        audio = None
        if d.get("arquivo"):
            try:
                audio = motor.ler_arquivo(pasta / d["arquivo"])
            except Exception as e:
                avisos.append(f"{d['nome']}: não consegui ler o áudio ({e})")
        f = motor.nova_faixa(d["nome"], audio, round(d.get("inicio", 0) * r))
        f.armada = False
        f.cor = d.get("cor", f.cor)
        for k in ("volume_db", "pan", "mudo", "solo", "entrada", "monitor"):
            if k in d:
                setattr(f, k, d[k])
        efs = []
        for e in d.get("efeitos", []):
            try:
                efs.append(fx.de_dict(e))
            except Exception as err:
                avisos.append(f"{d['nome']}: efeito {e.get('nome_vst') or e['tipo']} não abriu ({err})")
        f.efeitos = efs
        f.refazer_cadeia()
    if r != 1:
        motor.loop_ini, motor.loop_fim = round(motor.loop_ini * r), round(motor.loop_fim * r)
    return avisos


def exportar_wav(motor, caminho):
    mix = motor.renderizar()
    sf.write(caminho, mix.T, motor.sr, subtype="PCM_24")
    return str(caminho)


def exportar_faixa(motor, id_, caminho):
    f = motor.faixa(id_)
    if f.audio is None:
        raise RuntimeError("Essa faixa está vazia.")
    sf.write(caminho, f.audio.T.astype(np.float32), motor.sr, subtype="PCM_24")
    return str(caminho)
