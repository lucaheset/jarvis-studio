"""Gerar músicas com a conta do Suno do usuário.

O Suno não tem API pública. Em vez de guardar senha ou cookie, o app roda um Chrome
(ou Edge) só dele, com perfil próprio, numa janela escondida fora da tela. Ela só
aparece quando o usuário precisa entrar na conta (uma vez) ou resolver um captcha.
O app se liga a essa janela pela porta de depuração do navegador:
- preenche o pedido na página de criar e aperta "Create" (se aparecer um captcha, quem
  resolve é o usuário, na janela);
- lê as músicas que a própria página recebe do Suno (respostas da studio-api), então
  continua funcionando mesmo que os endereços internos mudem de nome;
- baixa o MP3 pronto e manda para a mesma análise do envio de arquivo.

Se o Suno mudar o site e o preenchimento automático falhar, o usuário ainda pode criar
na janela, que aparece sozinha: o app pega as músicas novas do mesmo jeito.
A janela fica sem som (--mute-audio): a música é ouvida no player do app.
"""
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import Future
from pathlib import Path

URL_CRIAR = "https://suno.com/create"
API = "studio-api-prod.suno.com"
PORTA = int(os.environ.get("JM_SUNO_PORTA", 9333))
PERFIL = Path(os.environ.get("JM_SUNO_PERFIL", Path(__file__).resolve().parent.parent / "suno_perfil"))

_CANDIDATOS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def navegador():
    for c in _CANDIDATOS:
        if Path(c).is_file():
            return c
    return shutil.which("chrome") or shutil.which("msedge")


# ------------------------------------------------------------------ estado
_trava = threading.Lock()
CLIPS = {}      # id -> dados normalizados de cada música vista
PEDIDOS = []    # pedidos feitos pelo app, mais novo por último
INFO = {"janela": False, "visivel": False, "logado": None, "creditos": None, "erro": None, "aviso": None}
ESCONDIDA = {"left": -3200, "top": 0, "width": 1280, "height": 900}
NA_TELA = {"left": 120, "top": 60, "width": 1180, "height": 880}


def _clip(c):
    """Normaliza uma música do Suno, ou None se o objeto não for uma."""
    if not isinstance(c, dict) or not isinstance(c.get("id"), str) or "status" not in c:
        return None
    if not any(k in c for k in ("audio_url", "image_url", "metadata")):
        return None
    meta = c.get("metadata") or {}
    return {
        "id": c["id"],
        "titulo": c.get("title") or "",
        "status": c.get("status"),
        "audio": c.get("audio_url") or "",
        "capa": c.get("image_url") or c.get("image_large_url") or "",
        "estilo": meta.get("tags") or "",
        "letra": meta.get("prompt") or "",
        "duracao": meta.get("duration"),
        "criado": c.get("created_at") or "",
        "erro": meta.get("error_message") or "",
    }


def _varrer(obj, achados, fundo=0):
    if fundo > 6:
        return
    if isinstance(obj, dict):
        c = _clip(obj)
        if c:
            achados.append(c)
            return
        for k in ("total_credits_left", "credits_left"):
            if isinstance(obj.get(k), (int, float)):
                INFO["creditos"] = obj[k]
                break
        for v in obj.values():
            _varrer(v, achados, fundo + 1)
    elif isinstance(obj, list):
        for v in obj[:200]:
            _varrer(v, achados, fundo + 1)


def _guardar(clips, pedido=None):
    with _trava:
        for c in clips:
            antigo = CLIPS.get(c["id"], {})
            # o feed às vezes manda menos campos que o detalhe: não apaga o que já sabia
            CLIPS[c["id"]] = {**antigo, **{k: v for k, v in c.items() if v not in ("", None)}}
            if pedido and c["id"] not in pedido["clips"]:
                pedido["clips"].append(c["id"])


# ------------------------------------------------------------------ o trabalhador
# O Playwright síncrono só pode ser usado pela thread que o criou: tudo passa por aqui.
_fila = queue.Queue()
_thread = None
_pw = {"p": None, "browser": None, "ctx": None, "pagina": None}
_esperando_criar = []   # pedidos aguardando a resposta do "generate"


def _pedir(acao, *args, espera=60):
    global _thread
    with _trava:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_laco, name="suno", daemon=True)
            _thread.start()
    f = Future()
    _fila.put((acao, args, f))
    return f.result(timeout=espera)


def _laco():
    from playwright.sync_api import sync_playwright
    _pw["p"] = sync_playwright().start()
    while True:
        try:
            acao, args, f = _fila.get(timeout=0.4)
        except queue.Empty:
            _bombear()
            continue
        try:
            f.set_result(acao(*args))
        except Exception as e:  # noqa: BLE001
            f.set_exception(e)


def _bombear():
    """Deixa o Playwright processar os eventos (respostas que a página recebe)."""
    pg = _pw["pagina"]
    if pg is None:
        return
    try:
        pg.wait_for_timeout(400)
    except Exception:  # noqa: BLE001
        _desligado()


def _desligado():
    _pw.update(browser=None, ctx=None, pagina=None)
    INFO["janela"] = False


def _ao_responder(resp):
    try:
        if API not in resp.url or resp.status >= 400:
            return
        if "json" not in (resp.headers.get("content-type") or ""):
            return
        dados = resp.json()
    except Exception:  # noqa: BLE001
        return
    achados = []
    _varrer(dados, achados)
    pedido = None
    if resp.request.method == "POST" and "generate" in resp.url and achados and _esperando_criar:
        pedido = _esperando_criar.pop(0)
        pedido["status"] = "gerando"
    _guardar(achados, pedido)


def _porta_aberta():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _conectar(abrir_se_fechado=True):
    """Liga-se à janela do Suno; abre o navegador se ela não existir."""
    if _pw["pagina"] is not None:
        try:
            _pw["pagina"].title()
            return _pw["pagina"]
        except Exception:  # noqa: BLE001
            _desligado()
    if not _porta_aberta():
        if not abrir_se_fechado:
            return None
        exe = navegador()
        if not exe:
            raise RuntimeError("não achei o Chrome nem o Edge neste computador")
        PERFIL.mkdir(parents=True, exist_ok=True)
        # abre escondida fora da tela; as três últimas opções impedem o Chrome de "dormir"
        # a página por ela não estar visível (senão o Suno para de atualizar)
        args = [exe, f"--remote-debugging-port={PORTA}", f"--user-data-dir={PERFIL}", "--mute-audio",
                "--no-first-run", "--no-default-browser-check", "--new-window",
                f"--window-position={ESCONDIDA['left']},{ESCONDIDA['top']}",
                f"--window-size={ESCONDIDA['width']},{ESCONDIDA['height']}",
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling", URL_CRIAR]
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 if os.name == "nt" else 0)  # DETACHED: sobrevive ao servidor
        t0 = time.time()
        while not _porta_aberta():
            if time.time() - t0 > 20:
                raise RuntimeError("o navegador abriu mas não respondeu na porta de controle")
            time.sleep(0.3)
    browser = _pw["p"].chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA}")
    browser.on("disconnected", lambda *_: _desligado())
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    ctx.on("response", _ao_responder)
    pg = next((p for p in ctx.pages if "suno.com" in p.url), None) or (ctx.pages[0] if ctx.pages else ctx.new_page())
    if "suno.com" not in pg.url:
        pg.goto(URL_CRIAR, wait_until="domcontentloaded")
    _pw.update(browser=browser, ctx=ctx, pagina=pg)
    INFO["janela"] = True
    return pg


def _janela(pg, visivel):
    """Mostra a janela (login, captcha) ou manda de volta para fora da tela."""
    if visivel and os.environ.get("JM_SUNO_NUNCA_MOSTRAR"):  # testes
        visivel = False
    try:
        cdp = pg.context.new_cdp_session(pg)
        jid = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds", {"windowId": jid, "bounds": {"windowState": "normal"}})
        cdp.send("Browser.setWindowBounds", {"windowId": jid, "bounds": NA_TELA if visivel else ESCONDIDA})
        cdp.detach()
        if visivel:
            pg.bring_to_front()
        INFO["visivel"] = visivel
    except Exception as e:  # noqa: BLE001
        print("[suno] mover a janela:", e)


def _token(pg):
    try:
        return pg.evaluate("async () => (window.Clerk && window.Clerk.session) ? await window.Clerk.session.getToken() : null")
    except Exception:  # noqa: BLE001
        return None


def _api(pg, caminho, token):
    """GET na studio-api pela própria página (mesma sessão do usuário)."""
    return pg.evaluate("""async ([url, token]) => {
        const r = await fetch(url, { headers: { Authorization: 'Bearer ' + token } });
        if (!r.ok) return { __erro: r.status };
        return await r.json();
    }""", [f"https://{API}{caminho}", token])


def _verificar(pg):
    """Atualiza logado/créditos e lê as músicas mais recentes da conta."""
    if "sign-in" in pg.url or "sign-up" in pg.url:
        INFO["logado"] = False
        return
    tk = _token(pg)
    if not tk:
        try:
            logado = pg.evaluate("() => !!(window.Clerk && window.Clerk.user)")
        except Exception:  # noqa: BLE001
            logado = None
        INFO["logado"] = bool(logado) if logado is not None else INFO["logado"]
        return
    INFO["logado"] = True
    for caminho in ("/api/billing/info/", "/api/feed/v2?page=0"):
        try:
            dados = _api(pg, caminho, tk)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(dados, dict) and "__erro" in dados:
            continue
        achados = []
        _varrer(dados, achados)
        _guardar(achados)


# ------------------------------------------------------------------ ações (rodam na thread do Suno)
def _abrir():
    INFO["erro"] = None
    pg = _conectar()
    pg.wait_for_timeout(1500)
    _verificar(pg)
    _janela(pg, INFO["logado"] is not True)
    return estado()


def _atualizar():
    pg = _conectar(abrir_se_fechado=False)
    if pg is not None:
        _verificar(pg)
        # entrou na conta (ou resolveu o captcha): a janela volta a se esconder
        if INFO["visivel"] and INFO["logado"] and not _esperando_criar:
            _janela(pg, False)
    return estado()


def _primeiro_visivel(pg, seletores):
    for s in seletores:
        try:
            loc = pg.locator(s)
            for i in range(min(loc.count(), 8)):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:  # noqa: BLE001
            continue
    return None


def _preencher(el, texto):
    el.click()
    el.fill(texto)


def _gerar(pedido):
    pg = _conectar()
    if "/create" not in pg.url:
        pg.goto(URL_CRIAR, wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)
    _verificar(pg)
    if INFO["logado"] is not True:
        pedido["status"] = "precisa_login"
        pedido["aviso"] = "entre na sua conta do Suno na janela que apareceu (só na primeira vez) e peça de novo"
        _janela(pg, True)
        return pedido
    d = pedido["dados"]
    personalizado = bool(d.get("letra") or d.get("estilo") or d.get("titulo"))
    falhas = []
    if personalizado:
        botao = _primeiro_visivel(pg, ["button:has-text('Custom')", "button:has-text('Advanced')",
                                       "button:has-text('Personalizado')", "[role=tab]:has-text('Custom')",
                                       "[role=tab]:has-text('Advanced')"])
        if botao:
            botao.click()
            pg.wait_for_timeout(800)
        campos = [("letra", ["textarea[placeholder*='lyric' i]", "textarea[aria-label*='lyric' i]",
                             "textarea[placeholder*='letra' i]"]),
                  ("estilo", ["textarea[placeholder*='style' i]", "input[placeholder*='style' i]",
                              "textarea[aria-label*='style' i]", "textarea[placeholder*='estilo' i]"]),
                  ("titulo", ["input[placeholder*='title' i]", "input[aria-label*='title' i]",
                              "input[placeholder*='título' i]"])]
        for chave, sels in campos:
            texto = d.get(chave) or ("[Instrumental]" if chave == "letra" and d.get("instrumental") else "")
            if not texto:
                continue
            el = _primeiro_visivel(pg, sels)
            if el:
                _preencher(el, texto)
            else:
                falhas.append(chave)
    else:
        el = _primeiro_visivel(pg, ["textarea[placeholder*='song' i]", "textarea[placeholder*='describe' i]",
                                    "textarea[aria-label*='song description' i]", "textarea[placeholder*='música' i]",
                                    "main textarea", "textarea"])
        if el:
            _preencher(el, d.get("descricao", ""))
        else:
            falhas.append("descricao")
    if d.get("instrumental"):
        chave = _primeiro_visivel(pg, ["button[aria-label*='instrumental' i]", "[role=switch][aria-label*='instrumental' i]",
                                       "button:has-text('Instrumental')", "label:has-text('Instrumental')"])
        if chave:
            ligado = (chave.get_attribute("aria-checked") or chave.get_attribute("aria-pressed") or "").lower() == "true"
            if not ligado:
                chave.click()
        else:
            falhas.append("instrumental")
    if falhas:
        pedido["status"] = "manual"
        pedido["aviso"] = ("o Suno mudou a página e não achei: " + ", ".join(falhas) +
                           ". Complete na janela do Suno e aperte Create; a música aparece aqui igual.")
        _janela(pg, True)
        _esperando_criar.append(pedido)
        return pedido
    criar = _primeiro_visivel(pg, ["button[aria-label='Create song']", "button[aria-label*='create' i]:not([aria-label*='playlist' i])",
                                   "button:text-is('Create')", "button:text-is('Criar')", "button:has-text('Create')"])
    if not criar:
        pedido["status"] = "manual"
        pedido["aviso"] = "preenchi o pedido, mas não achei o botão Create: aperte-o na janela do Suno"
        _janela(pg, True)
        _esperando_criar.append(pedido)
        return pedido
    _esperando_criar.append(pedido)
    criar.click()
    pedido["status"] = "enviado"
    # dá uns segundos para a resposta do "generate" chegar (ou o captcha aparecer)
    for _ in range(20):
        pg.wait_for_timeout(500)
        if pedido["clips"]:
            break
    if not pedido["clips"]:
        pedido["aviso"] = ("o Suno pediu uma confirmação (captcha ou aviso). Resolva na janela que apareceu; "
                           "ela some sozinha e a música aparece aqui.")
        _janela(pg, True)
    elif INFO["visivel"]:
        _janela(pg, False)
    return pedido


def _acompanhar():
    """Pergunta ao Suno como estão as músicas ainda sendo feitas."""
    pg = _conectar(abrir_se_fechado=False)
    if pg is None:
        return
    pendentes = [i for i, c in CLIPS.items() if c.get("status") not in ("complete", "error")]
    if not pendentes:
        return
    tk = _token(pg)
    if not tk:
        return
    for caminho in (f"/api/feed/v2?ids={','.join(pendentes[:10])}", f"/api/feed/?ids={','.join(pendentes[:10])}"):
        try:
            dados = _api(pg, caminho, tk)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(dados, dict) and "__erro" in dados:
            continue
        achados = []
        _varrer(dados, achados)
        _guardar(achados)
        if achados:
            return


# ------------------------------------------------------------------ uso externo (servidor)
def estado():
    with _trava:
        for p in PEDIDOS:
            cs = [CLIPS.get(i, {}) for i in p["clips"]]
            if cs and all(c.get("status") == "complete" for c in cs):
                p["status"] = "pronto"
            elif cs and any(c.get("status") == "error" for c in cs):
                p["status"] = "erro" if all(c.get("status") == "error" for c in cs) else p["status"]
        clips = sorted(CLIPS.values(), key=lambda c: c.get("criado") or "", reverse=True)[:40]
        return {**INFO, "navegador": bool(navegador()),
                "pedidos": [{k: v for k, v in p.items() if k != "dados"} | {"descricao": p["dados"].get("descricao")
                             or p["dados"].get("titulo") or p["dados"].get("estilo")} for p in PEDIDOS[-10:]][::-1],
                "clips": clips}


def abrir():
    try:
        return _pedir(_abrir)
    except Exception as e:  # noqa: BLE001
        INFO["erro"] = str(e)
        raise


def atualizar():
    if _pw["pagina"] is None and not _porta_aberta():  # janela fechada: nem liga o Playwright
        INFO["janela"] = False
        return estado()
    try:
        _pedir(_acompanhar, espera=30)
        return _pedir(_atualizar, espera=30)
    except Exception as e:  # noqa: BLE001
        INFO["erro"] = str(e)
        return estado()


def gerar(dados):
    pedido = {"id": f"p{int(time.time() * 1000)}", "criado": time.time(), "status": "preparando",
              "clips": [], "aviso": None, "dados": dados}
    with _trava:
        PEDIDOS.append(pedido)
    try:
        _pedir(_gerar, pedido, espera=90)
    except Exception as e:  # noqa: BLE001
        pedido["status"] = "erro"
        pedido["aviso"] = f"não consegui falar com a janela do Suno: {e}"
    return {k: v for k, v in pedido.items() if k != "dados"}


def baixar(clip_id, pasta):
    """Baixa o MP3 pronto e converte para WAV. Devolve (caminho, título)."""
    c = CLIPS.get(clip_id)
    if not c:
        raise RuntimeError("música do Suno desconhecida: atualize a lista")
    if c.get("status") != "complete":
        raise RuntimeError("essa música ainda não terminou no Suno")
    url = c.get("audio") if str(c.get("audio", "")).endswith(".mp3") else f"https://cdn1.suno.ai/{clip_id}.mp3"
    pasta = Path(pasta)
    mp3 = pasta / "suno.mp3"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(mp3, "wb") as f:
        shutil.copyfileobj(r, f)
    from . import ffmpeg
    exe = ffmpeg.garantir()
    wav = pasta / "original.wav"
    if exe:
        subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(mp3), str(wav)], check=True,
                       creationflags=0x08000000 if os.name == "nt" else 0)
        mp3.unlink(missing_ok=True)
        return wav, c.get("titulo") or "Suno"
    return mp3, c.get("titulo") or "Suno"


def salvar_info(pasta, clip_id):
    """Guarda letra e estilo junto da análise."""
    c = CLIPS.get(clip_id) or {}
    return {"id": clip_id, "estilo": c.get("estilo"), "letra": c.get("letra"), "capa": c.get("capa")}
