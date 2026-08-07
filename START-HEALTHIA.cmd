@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================
echo              HealthIA ONE
echo ==============================================
echo [L] Local seguro - 0 llamadas a Google AI
echo [G] Gemini controlado - limite de 10 llamadas
echo.

choice /C LG /N /M "Selecciona L o G: "
if errorlevel 2 goto guarded

echo.
echo Iniciando modo local seguro...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\run-local-secure.ps1"
goto finish

:guarded
echo.
echo Iniciando Gemini controlado con limite de 10 solicitudes...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\run-local-secure.ps1" -GuardedAi -RequestLimit 10

:finish
if errorlevel 1 (
  echo.
  echo HealthIA no pudo iniciar. Revisa el mensaje anterior.
  pause
)
endlocal
