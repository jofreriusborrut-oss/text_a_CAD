@echo off
rem ============================================================
rem  Text a CAD - double-click this file to start the app.
rem  The first time it also creates the Python environment and
rem  installs the libraries (it takes a few minutes).
rem ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Claude Code (native installer) lives here: make it findable.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

if not exist ".venv\Scripts\python.exe" (
    echo Primera vegada: creant l'entorn de Python i instal·lant les llibreries...
    echo Pot trigar uns minuts. No tanquis aquesta finestra.
    echo.
    py -3.12 -m venv .venv 2>nul
    if not exist ".venv\Scripts\python.exe" python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo ERROR: no s'ha pogut crear l'entorn. Tens Python 3.12 instal·lat?
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: no s'han pogut instal·lar les llibreries. Mira el missatge de dalt.
        pause
        exit /b 1
    )
)

if not exist ".env" copy ".env.example" ".env" >nul

where claude >nul 2>nul
if errorlevel 1 (
    echo AVÍS: no trobo Claude Code. Instal·la'l i executa "claude" una vegada per iniciar la sessió.
    echo.
)

echo Obrint Text a CAD al navegador...
echo Per tancar l'app, tanca aquesta finestra.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
