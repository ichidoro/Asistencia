@echo off
title Sistema de Asistencia Aguacol
echo.
echo  ===================================================
echo   Sistema de Asistencia Aguacol
echo  ===================================================
echo.
echo  Iniciando servidor... por favor espere.
echo  La aplicacion se abrira automaticamente en su navegador.
echo  Para cerrar la aplicacion, cierre esta ventana.
echo  ===================================================
echo.

:: ── 1. Buscar .venv en el mismo directorio que este .bat ─────────
set "APP_DIR=%~dp0"
if exist "%APP_DIR%.venv\Scripts\python.exe" (
    set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
    set "MAIN=%APP_DIR%backend\main.py"
    goto :run
)

:: ── 2. Buscar en la ruta de instalacion por defecto ───────────────
if exist "C:\Asistencia\.venv\Scripts\python.exe" (
    set "PYTHON=C:\Asistencia\.venv\Scripts\python.exe"
    set "MAIN=C:\Asistencia\backend\main.py"
    set "APP_DIR=C:\Asistencia\"
    goto :run
)

:: ── 3. Usar Python del sistema como ultimo recurso ────────────────
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
    set "MAIN=%APP_DIR%backend\main.py"
    goto :run
)

:: ── Sin Python: dar instrucciones claras ──────────────────────────
echo.
echo  ERROR: No se encontro Python ni el entorno virtual.
echo.
echo  Posibles causas:
echo    1. El instalador no se ejecuto correctamente.
echo    2. Este archivo fue movido fuera de C:\Asistencia
echo.
echo  Solucion: Vuelva a ejecutar Aguacol_Asistencia_Setup.exe
echo.
pause
exit /b 1

:run
cd /d "%APP_DIR%"
"%PYTHON%" "%MAIN%"
pause
