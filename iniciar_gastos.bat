@echo off
setlocal
cd /d "%~dp0"
title Gastos - Inicio

echo.
echo ========================================
echo  Iniciando Gastos
echo ========================================
echo.

set "PYTHON_LAUNCHER="

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"

if not defined PYTHON_LAUNCHER (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_LAUNCHER=python"
)

if not defined PYTHON_LAUNCHER (
    echo Necesitas instalar Python 3 para usar esta app.
    echo Descargalo desde: https://www.python.org/downloads/
    echo Al instalarlo, marca la opcion "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual local...
    %PYTHON_LAUNCHER% -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto error

if exist "requirements.txt" (
    python -c "import flask, pandas, openpyxl" >nul 2>nul
    if errorlevel 1 (
        echo Instalando dependencias...
        python -m pip install -r requirements.txt
        if errorlevel 1 goto error
    )
) else (
    echo No se encontro requirements.txt.
    goto error
)

echo.
echo Abriendo navegador en http://127.0.0.1:5000
start "" "http://127.0.0.1:5000"
echo.
echo No cierres esta ventana mientras uses la app.
echo Para detenerla, cerra esta ventana o presiona Ctrl+C.
echo.

python app.py
if errorlevel 1 goto error

echo.
echo La app se cerro.
pause
exit /b 0

:error
echo.
echo Ocurrio un error al iniciar la app.
echo Revisa los mensajes de esta ventana.
echo.
pause
exit /b 1
