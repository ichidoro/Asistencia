@echo off
title Compilar Instalador - Aguacol Asistencia
echo.
echo  =====================================================
echo   GENERADOR DE INSTALADOR - Aguacol Asistencia
echo  =====================================================
echo.

:: Verificar que Inno Setup está instalado
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist %ISCC% (
    echo ERROR: No se encontro Inno Setup 6.
    echo Descargue e instale Inno Setup desde: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

:: Crear carpeta de salida
if not exist "dist" mkdir dist

:: Verificar assets requeridos
if not exist "assets\logo.ico" (
    echo ADVERTENCIA: assets\logo.ico no encontrado.
    echo Por favor coloque el icono de la aplicacion en installer\assets\logo.ico
    echo Puede usar cualquier archivo .ico de 256x256 pixeles.
    echo.
    pause
)

echo  Compilando instalador...
echo  Esto tomara aproximadamente 1-2 minutos.
echo.
%ISCC% setup.iss

if %ERRORLEVEL% EQU 0 (
    echo.
    echo  =====================================================
    echo   EXITO: Aguacol_Asistencia_Setup.exe generado en:
    echo   installer\dist\Aguacol_Asistencia_Setup.exe
    echo  =====================================================
    echo.
    echo  Distribuya ese archivo a los usuarios.
    start "" "dist\"
) else (
    echo.
    echo  ERROR al compilar el instalador.
    echo  Revise los mensajes de error arriba.
)
echo.
pause
