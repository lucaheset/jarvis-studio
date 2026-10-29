"""API do J.A.R.V.I.S MUSIC. Serve a interface e roda o pipeline."""
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from jarvis_music import ffmpeg, gpu, pipeline

FFMPEG = ffmpeg.garantir()  # o separador e o download por link precisam dele

RAIZ = Path(__file__).resolve().parent
DADOS = Path(os.environ.get("JM_DADOS", RAIZ / "dados"))
MODELOS = Path(os.environ.get("JM_MODELOS", RAIZ / "modelos"))
WEB = RAIZ / "web"
DADOS.mkdir(parents=True, exist_ok=True)
MODELOS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="J.A.R.V.I.S MUSIC")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

TRABALHOS = {}
TRAVA = threading.Lock()


def _estado(id_):
    arq = DADOS / id_ / "estado.json"
    if not arq.exists():
        raise HTTPException(404, "análise não encontrada")
    return json.loads(arq.read_text(encoding="utf-8"))


@app.get("/api/saude")
def saude():
    info = {"ok": True, "gpu": None, "separador": None, "ffmpeg": bool(FFMPEG)}
    try:
        import torch
        if gpu.sem_gpu():
            info["gpu"] = "CPU (JM_SEM_GPU)"
        else:
            info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    except Exception:
        info["gpu"] = "PyTorch não instalado"
    try:
        import audio_separator  # noqa
        info["separador"] = "BS-RoFormer (audio-separator)"
    except Exception:
        try:
            import demucs  # noqa
            info["separador"] = "Demucs"
        except Exception:
            info["separador"] = None
    return info


@app.post("/api/analisar")
async def analisar(arquivo: UploadFile = File(...), motor: str = Form("auto")):
    id_ = uuid.uuid4().hex[:12]
    trabalho = pipeline.Trabalho(DADOS, id_, arquivo.filename or "audio")
    destino = trabalho.dir / f"entrada{Path(arquivo.filename or '').suffix.lower() or '.wav'}"
    with destino.open("wb") as f:
        shutil.copyfileobj(arquivo.file, f)
    with TRAVA:
        TRABALHOS[id_] = trabalho
    t = threading.Thread(target=pipeline.processar,
                         args=(destino, trabalho, MODELOS), kwargs={"motor_separacao": motor},
                         daemon=True)
    t.start()
    return {"id": id_}


def _baixar_e_processar(url, trabalho, motor):
    """Baixa o áudio do link e roda o mesmo pipeline do envio de arquivo."""
    from jarvis_music import youtube

    def progresso(texto):
        # atualiza a etapa sem encher o registro com cada porcentagem
        trabalho.estado["etapa"] = texto
        trabalho.salvar()

    try:
        trabalho.passo("Baixando o áudio do link", 1)
        caminho, titulo = youtube.baixar(url, trabalho.dir, progresso)
        trabalho.estado["arquivo"] = titulo
        trabalho.estado["link"] = url
        trabalho.passo(f"Baixado: {titulo}", 2)
    except Exception as e:
        trabalho.estado["erro"] = f"não consegui baixar o link: {e}"
        trabalho.passo("Falhou")
        return
    pipeline.processar(caminho, trabalho, MODELOS, motor_separacao=motor)


@app.post("/api/analisar_link")
def analisar_link(url: str = Form(...), motor: str = Form("auto")):
    from jarvis_music import youtube
    if not youtube.link_valido(url):
        raise HTTPException(400, "cole um link começando com http:// ou https://")
    id_ = uuid.uuid4().hex[:12]
    trabalho = pipeline.Trabalho(DADOS, id_, url.strip())
    with TRAVA:
        TRABALHOS[id_] = trabalho
    threading.Thread(target=_baixar_e_processar, args=(url, trabalho, motor), daemon=True).start()
    return {"id": id_}


# ------------------------------------------------------------ gerar no Suno
@app.get("/api/suno")
def suno_estado():
    from jarvis_music import suno
    return suno.atualizar()


@app.post("/api/suno/abrir")
def suno_abrir():
    from jarvis_music import suno
    try:
        return suno.abrir()
    except Exception as e:
        raise HTTPException(500, f"não consegui abrir a janela do Suno: {e}")


@app.post("/api/suno/gerar")
async def suno_gerar(req: Request):
    from jarvis_music import suno
    corpo = await req.json()
    dados = {k: str(corpo.get(k) or "").strip()[:3000] for k in ("descricao", "letra", "estilo", "titulo")}
    dados["instrumental"] = bool(corpo.get("instrumental"))
    if not (dados["descricao"] or dados["letra"] or dados["estilo"]):
        raise HTTPException(400, "descreva a música ou mande letra e estilo")
    return suno.gerar(dados)


def _baixar_suno(clip_id, trabalho, motor):
    from jarvis_music import suno
    try:
        trabalho.passo("Baixando a música do Suno", 1)
        caminho, titulo = suno.baixar(clip_id, trabalho.dir)
        trabalho.estado["arquivo"] = titulo
        trabalho.estado["suno"] = suno.salvar_info(trabalho.dir, clip_id)
        trabalho.passo(f"Baixado: {titulo}", 2)
    except Exception as e:
        trabalho.estado["erro"] = f"não consegui baixar do Suno: {e}"
        trabalho.passo("Falhou")
        return
    pipeline.processar(caminho, trabalho, MODELOS, motor_separacao=motor)


@app.post("/api/suno/analisar/{clip_id}")
def suno_analisar(clip_id: str, motor: str = Form("auto")):
    from jarvis_music import suno
    c = suno.CLIPS.get(clip_id)
    if not c:
        raise HTTPException(404, "música do Suno desconhecida: atualize a lista")
    if c.get("status") != "complete":
        raise HTTPException(409, "essa música ainda não terminou no Suno")
    id_ = uuid.uuid4().hex[:12]
    trabalho = pipeline.Trabalho(DADOS, id_, c.get("titulo") or "Suno")
    with TRAVA:
        TRABALHOS[id_] = trabalho
    threading.Thread(target=_baixar_suno, args=(clip_id, trabalho, motor), daemon=True).start()
    return {"id": id_}


@app.get("/api/estado/{id_}")
def estado(id_: str):
    return _estado(id_)


def _pasta(id_):
    """Pasta de uma análise, sem deixar sair de DADOS."""
    pasta = (DADOS / id_).resolve()
    if pasta.parent != DADOS.resolve() or not (pasta / "estado.json").exists():
        raise HTTPException(404, "análise não encontrada")
    return pasta


@app.get("/api/arquivo/{id_}/{nome:path}")
def arquivo(id_: str, nome: str):
    pasta = _pasta(id_)
    caminho = (pasta / nome).resolve()
    if not caminho.is_relative_to(pasta) or not caminho.is_file():
        raise HTTPException(404, "arquivo não encontrado")
    return FileResponse(caminho)


# ------------------------------------------------ velocidade e tom do áudio
def _faixas_ids(est):
    return [f["id"] for f in est.get("faixas", [])]


@app.post("/api/variacao/{id_}")
def pedir_variacao(id_: str, velocidade: float = Form(1.0), semitons: int = Form(0)):
    """Renderiza (ou reaproveita) todas as faixas numa velocidade/tom novos."""
    from jarvis_music import variacao
    if not (0.25 <= velocidade <= 2.0) or not (-12 <= semitons <= 12):
        raise HTTPException(400, "velocidade entre 25% e 200%, tom entre -12 e +12")
    est = _estado(id_)
    return variacao.pedir(_pasta(id_), _faixas_ids(est), velocidade, semitons)


@app.get("/api/variacao/{id_}")
def ver_variacao(id_: str, velocidade: float = 1.0, semitons: int = 0):
    from jarvis_music import variacao
    info = variacao.estado(_pasta(id_), velocidade, semitons)
    if info is None:
        raise HTTPException(404, "esta versão ainda não foi pedida")
    return info


# ------------------------------------------------------------ biblioteca
@app.get("/api/biblioteca")
def biblioteca():
    itens = []
    for d in sorted(DADOS.glob("*/estado.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            e = json.loads(d.read_text(encoding="utf-8"))
        except Exception:
            continue
        ritmo, tom = e.get("ritmo") or {}, e.get("tom") or {}
        itens.append({
            "id": e.get("id"), "arquivo": e.get("arquivo"), "link": e.get("link"),
            "concluido": e.get("concluido"), "erro": e.get("erro"), "progresso": e.get("progresso"),
            "etapa": e.get("etapa"), "duracao": e.get("duracao"), "criado": e.get("criado"),
            "bpm": ritmo.get("bpm"), "compasso": ritmo.get("compasso"), "tom": tom.get("tom"),
            "faixas": len(e.get("faixas", [])), "tem_tab": bool(e.get("tabs")),
        })
    return itens


@app.post("/api/renomear/{id_}")
def renomear(id_: str, nome: str = Form(...)):
    pasta = _pasta(id_)
    nome = nome.strip()[:200]
    if not nome:
        raise HTTPException(400, "nome vazio")
    arq = pasta / "estado.json"
    with TRAVA:
        e = json.loads(arq.read_text(encoding="utf-8"))
        e["arquivo"] = nome
        arq.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.delete("/api/analise/{id_}")
def apagar(id_: str):
    pasta = _pasta(id_)
    e = json.loads((pasta / "estado.json").read_text(encoding="utf-8"))
    if not e.get("concluido") and not e.get("erro"):
        raise HTTPException(409, "essa música ainda está sendo analisada")
    shutil.rmtree(pasta)
    return {"ok": True}


# ------------------------------------------------------- exportar áudio
@app.post("/api/exportar/{id_}")
def exportar(id_: str, formato: str = Form("wav"), modo: str = Form("stems"),
             faixas: str = Form(None), ganhos: str = Form(None),
             velocidade: float = Form(1.0), semitons: int = Form(0)):
    from jarvis_music import exportar_audio, variacao
    est = _estado(id_)
    pasta = _pasta(id_)
    lista = json.loads(faixas) if faixas else _faixas_ids(est)
    lista = [f for f in lista if f in _faixas_ids(est)]
    if not lista:
        raise HTTPException(400, "escolha pelo menos uma faixa")
    chave = None
    if abs(velocidade - 1.0) > 1e-3 or semitons:
        info = variacao.estado(pasta, velocidade, semitons)
        if not info or not info.get("pronto"):
            raise HTTPException(409, "essa velocidade/tom ainda está sendo preparada")
        chave = info["chave"]
    try:
        arq = exportar_audio.exportar(pasta, lista, formato=formato, modo=modo,
                                      ganhos=json.loads(ganhos) if ganhos else None,
                                      chave_variacao=chave, nome_base=est.get("arquivo") or "musica")
    except ValueError as e:
        raise HTTPException(400, str(e))
    # o arquivo é temporário: apaga depois de entregar
    return FileResponse(arq, filename=arq.name, background=BackgroundTask(arq.unlink, missing_ok=True))


@app.post("/api/tab/{id_}/{faixa}")
def refazer_tab(id_: str, faixa: str, sensibilidade: float = Form(0.5),
                afinacao: str = Form(None), papeis: str = Form(None)):
    """Refaz a tablatura de uma faixa: ajusta a sensibilidade, força uma afinação
    ou corrige trechos marcados por você como base/solo."""
    est = _estado(id_)
    caminho = DADOS / id_ / f"{faixa}.wav"
    if not caminho.exists():
        raise HTTPException(404, "faixa não encontrada")
    bpm = (est.get("ritmo") or {}).get("bpm") or 120.0
    try:
        tab = pipeline.gerar_tab(caminho, DADOS / id_, faixa, bpm, sensibilidade=sensibilidade,
                                 compassos=est.get("compassos"), tom=(est.get("tom") or {}).get("tom"))
    finally:
        gpu.liberar()
    if papeis:
        try:
            marcas = json.loads(papeis)  # [{"inicio":s,"fim":s,"papel":"solo"}]
            from jarvis_music import tablatura
            for n in tab.get("notas", []):
                for m in marcas:
                    if m["inicio"] <= n["inicio"] < m["fim"]:
                        n["papel"] = m["papel"]
            afin = afinacao or tab.get("afinacao", "E padrão")
            for papel in ("base", "solo"):
                sel = [n for n in tab["notas"] if n.get("papel") == papel]
                tab["ascii"][papel] = tablatura.tab_ascii(sel, afin, bpm, compassos=est.get("compassos"))
        except Exception as e:
            tab["aviso_papeis"] = str(e)
    est.setdefault("tabs", {})[faixa] = tab
    (DADOS / id_ / "estado.json").write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return tab


CIFRANDO = set()


@app.post("/api/tab/{id_}/{faixa}/notas")
async def salvar_notas(id_: str, faixa: str, req: Request):
    """Salva as correções da tablatura feitas na tela (lista completa de notas)."""
    corpo = await req.json()
    notas = corpo.get("notas")
    if not isinstance(notas, list):
        raise HTTPException(400, "mande a lista de notas")
    pasta = _pasta(id_)
    with TRAVA:
        est = _estado(id_)
        antiga = (est.get("tabs") or {}).get(faixa)
        if not antiga:
            raise HTTPException(404, "essa faixa não tem tablatura")
        bpm = (est.get("ritmo") or {}).get("bpm") or 120.0
        tab = pipeline.salvar_tab_editada(antiga, notas, pasta, faixa, bpm, compassos=est.get("compassos"),
                                          tom=(est.get("tom") or {}).get("tom"))
        est["tabs"][faixa] = tab
        (pasta / "estado.json").write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return tab


@app.post("/api/cifra/{id_}")
def refazer_cifra(id_: str):
    """Gera a cifra por compasso de uma análise antiga (feita antes da cifra ao vivo)."""
    est = _estado(id_)
    if est.get("versao_cifra") == 2:
        return {"compassos": est["compassos"], "cifra": est["cifra"],
                "tempos_por_compasso": est.get("tempos_por_compasso")}
    with TRAVA:
        if id_ in CIFRANDO:
            raise HTTPException(409, "a cifra desta música já está sendo gerada")
        CIFRANDO.add(id_)
    try:
        originais = sorted((DADOS / id_).glob("original.*"))
        if not originais:
            raise HTTPException(404, "o áudio original desta análise não existe mais")
        from jarvis_music.audio import carregar, para_mono
        pipeline.aplicar_cifra(est, para_mono(carregar(originais[0])))
        arq = DADOS / id_ / "estado.json"
        atual = json.loads(arq.read_text(encoding="utf-8"))
        for k in ("compassos", "cifra", "tempos_por_compasso", "versao_cifra"):
            atual[k] = est[k]
        arq.write_text(json.dumps(atual, ensure_ascii=False), encoding="utf-8")
        return {"compassos": est["compassos"], "cifra": est["cifra"],
                "tempos_por_compasso": est.get("tempos_por_compasso")}
    finally:
        with TRAVA:
            CIFRANDO.discard(id_)


DIVIDINDO = set()


@app.post("/api/base_solo/{id_}")
def separar_base_solo(id_: str):
    """Separa guitarra base e solo pelas notas da tab (CPU), para músicas já analisadas."""
    pasta = _pasta(id_)
    with TRAVA:
        if id_ in DIVIDINDO:
            raise HTTPException(409, "já estou separando as guitarras desta música")
        DIVIDINDO.add(id_)
    try:
        est = _estado(id_)
        info = pipeline.dividir_base_solo(est, pasta)
        with TRAVA:
            atual = _estado(id_)
            atual["faixas"] = est["faixas"]
            atual["base_solo"] = info
            (pasta / "estado.json").write_text(json.dumps(atual, ensure_ascii=False), encoding="utf-8")
        return atual
    finally:
        with TRAVA:
            DIVIDINDO.discard(id_)


SECCIONANDO = set()


@app.post("/api/secoes/{id_}")
def gerar_secoes(id_: str, motor: str = Form(None)):
    """Partes da música (intro, verso, refrão...) para análises feitas antes delas."""
    pasta = _pasta(id_)
    est = _estado(id_)
    if (est.get("secoes") or {}).get("lista") and not motor:
        return est["secoes"]
    if not est.get("compassos"):
        raise HTTPException(409, "gere a cifra por compasso antes")
    if motor not in (None, "auto", "songformer", "heuristica"):
        raise HTTPException(400, "motor deve ser auto, songformer ou heuristica")
    with TRAVA:
        if id_ in SECCIONANDO:
            raise HTTPException(409, "as partes desta música já estão sendo calculadas")
        SECCIONANDO.add(id_)
    try:
        secoes = pipeline.gerar_secoes(est, pasta, motor=motor)
        with TRAVA:
            atual = _estado(id_)
            atual["secoes"] = secoes
            (pasta / "estado.json").write_text(json.dumps(atual, ensure_ascii=False), encoding="utf-8")
        return secoes
    finally:
        gpu.liberar()
        with TRAVA:
            SECCIONANDO.discard(id_)


@app.post("/api/secoes/{id_}/nomes")
async def salvar_nomes_secoes(id_: str, req: Request):
    """Grava os nomes das partes editados na tela ({"nomes": ["Intro", "Verso 1", ...]})."""
    nomes = (await req.json()).get("nomes")
    if not isinstance(nomes, list):
        raise HTTPException(400, "mande a lista de nomes")
    pasta = _pasta(id_)
    with TRAVA:
        est = _estado(id_)
        lista = (est.get("secoes") or {}).get("lista") or []
        if len(nomes) != len(lista):
            raise HTTPException(400, "a lista não bate com as partes salvas")
        for s, nome in zip(lista, nomes):
            nome = str(nome or "").strip()[:40]
            if nome:
                s["nome"] = nome
        est["secoes"]["editada"] = True
        (pasta / "estado.json").write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return est["secoes"]


@app.get("/api/analises")
def analises(limite: int = 20):
    itens = []
    for d in sorted(DADOS.glob("*/estado.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            e = json.loads(d.read_text(encoding="utf-8"))
            itens.append({k: e.get(k) for k in ("id", "arquivo", "etapa", "progresso",
                                                "concluido", "erro", "duracao")})
        except Exception:
            continue
        if len(itens) >= limite:
            break
    return itens


if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
else:
    @app.get("/")
    def raiz():
        return JSONResponse({"aviso": "interface não compilada: rode npm run build em web/"})


if __name__ == "__main__":
    import uvicorn
    gpu.prioridade_baixa()  # o servidor nunca disputa a máquina com a tela
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("JM_PORTA", 8770)))
