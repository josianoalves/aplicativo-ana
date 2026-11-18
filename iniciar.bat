@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call instalar.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "import imageio_ffmpeg" >nul 2>&1
if errorlevel 1 call instalar.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m radar.server %*
if errorlevel 1 pause
