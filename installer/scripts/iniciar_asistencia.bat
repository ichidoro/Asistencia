@echo off
title Sistema de Asistencia Aguacol
cd /d "%~dp0"
echo.
echo  ===================================================
echo   Sistema de Asistencia Aguacol
echo  ===================================================
echo.
echo  Iniciando servidor... por favor espere.
echo  La aplicacion se abrira automaticamente en su navegador.
echo.
echo  Para cerrar la aplicacion, cierre esta ventana.
echo  ===================================================
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0backend\main.py"
pause
