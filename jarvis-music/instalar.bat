@echo off
REM J.A.R.V.I.S MUSIC: instalacao completa (PyTorch com CUDA 12.8 para a RTX 5080).
cd /d "%~dp0"
where python >nul 2>nul || (echo Python nao encontrado no PATH. & pause & exit /b 1)

echo [1/4] criando o ambiente isolado...
python -m venv .venv || (pause & exit /b 1)

echo [2/4] atualizando o pip...
".venv\Scripts\python.exe" -m pip install -U pip

echo [3/4] instalando o PyTorch com CUDA 12.8...
".venv\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 || (pause & exit /b 1)

echo [4/4] instalando o resto...
".venv\Scripts\python.exe" -m pip install -r backend\requisitos.txt || (pause & exit /b 1)
REM basic-pitch sem dependencias: evita o TensorFlow antigo (usa o modelo ONNX)
".venv\Scripts\python.exe" -m pip install --no-deps "basic-pitch>=0.4" || (pause & exit /b 1)
REM transcritor de guitarra de alta resolucao (pesos baixados do Hugging Face no primeiro uso)
".venv\Scripts\python.exe" -m pip install --no-deps "git+https://github.com/xavriley/piano_transcription_inference.git" || (pause & exit /b 1)
REM alguma dependencia pode trocar o PyTorch pela versao sem CUDA: recoloca a de CUDA 12.8
".venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 || (pause & exit /b 1)

echo.
echo Conferindo a placa de video:
".venv\Scripts\python.exe" -c "import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA nao disponivel: a separacao vai rodar na CPU')"
echo.
echo Pronto. Rode iniciar.bat.
pause
