@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto erro
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto erro
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Configuracao inicial concluida.
exit /b 0
:erro
echo.
echo Falha na instalacao. Instale Python 3.10 ou mais recente e verifique a conexao.
pause
exit /b 1
