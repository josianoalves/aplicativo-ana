@echo off
choice /m "Iniciar o Radar automaticamente ao entrar no Windows"
if errorlevel 2 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0inicio-windows.ps1" -Desativar
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0inicio-windows.ps1"
)
pause
