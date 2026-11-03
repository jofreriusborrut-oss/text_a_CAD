@echo off
rem ============================================================
rem  Text a CAD - double-click this file to start the app.
rem  The first time it also creates the Python environment and
rem  installs the libraries (it takes a few minutes).
rem  (ASCII only and CRLF line endings: required by cmd.exe)
rem ============================================================
setlocal
cd /d "%~dp0"

rem Claude Code (native installer) lives here: make it findable.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

if exist ".venv\Scripts\python.exe" goto venv_ok
echo Primera vegada: creant l'entorn de Python i instal.lant les llibreries...
echo Pot trigar uns minuts. No tanquis aquesta finestra.
echo.
py -3.12 -m venv .venv
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto error_python
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error_pip

:venv_ok
if not exist ".env" copy ".env.example" ".env" >nul

where claude >nul 2>nul
if errorlevel 1 echo AVIS: no trobo Claude Code. Instal.la'l i executa "claude" una vegada per iniciar la sessio.

echo Obrint Text a CAD al navegador...
echo Per tancar l'app, tanca aquesta finestra.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
exit /b 0

:error_python
echo.
echo ERROR: no s'ha pogut crear l'entorn de Python. Tens Python 3.12 instal.lat?
pause
exit /b 1

:error_pip
echo.
echo ERROR: no s'han pogut instal.lar les llibreries. Mira el missatge de dalt.
pause
exit /b 1
