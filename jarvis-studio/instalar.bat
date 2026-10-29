@echo off
REM JARVIS Studio: instala o ambiente e cria o atalho na area de trabalho.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python nao encontrado no PATH. & pause & exit /b 1)

echo [1/3] criando o ambiente isolado...
if not exist ".venv\Scripts\python.exe" python -m venv .venv || (pause & exit /b 1)

echo [2/3] instalando as dependencias...
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -r requisitos.txt || (pause & exit /b 1)

echo [3/3] criando o atalho "JARVIS Studio" na area de trabalho...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\JARVIS Studio.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='app.py'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0ui\icone.ico'; $s.Save()"

echo.
echo Placas de som encontradas (procure a sua com ASIO):
".venv\Scripts\python.exe" -c "import os; os.environ['SD_ENABLE_ASIO']='1'; import sounddevice as sd; apis=sd.query_hostapis(); [print('  ', apis[d['hostapi']]['name'], '-', d['name']) for d in sd.query_devices()]"
echo.
echo Pronto. Abra pelo atalho "JARVIS Studio" ou pelo iniciar.bat.
pause
