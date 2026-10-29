"""JARVIS Studio: estúdio de gravação com efeitos, fora do navegador.

A janela é só a tela. Todo o áudio passa pelo motor em Python, direto na placa
de som (ASIO), então o WebView nunca abre o dispositivo de áudio.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

import webview  # noqa: E402

from estudio.api import Api  # noqa: E402


def main():
    dados = Path(os.environ.get("JS_DADOS", RAIZ / "dados"))
    api = Api(dados)
    janela = webview.create_window(
        "J.A.R.V.I.S STUDIO", str(RAIZ / "ui" / "index.html"), js_api=api,
        width=1500, height=900, min_size=(1100, 650), background_color="#020912",
    )
    janela.events.closed += api._encerrar
    icone = RAIZ / "ui" / "icone.ico"
    webview.start(api._iniciar, (janela,), gui="edgechromium" if sys.platform == "win32" else None,
                  storage_path=str(dados / "webview"),
                  icon=str(icone) if icone.exists() else None,
                  debug=bool(os.environ.get("JS_DEBUG")))


if __name__ == "__main__":
    main()
