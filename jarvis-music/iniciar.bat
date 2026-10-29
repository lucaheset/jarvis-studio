@echo off
REM J.A.R.V.I.S MUSIC: liga o servidor e abre no navegador.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8770
".venv\Scripts\python.exe" backend\servidor.py
pause
