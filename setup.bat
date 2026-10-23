@echo off
rem Creates .venv for the PeerCam Bridge script and installs its packages.
rem Usage: setup.bat [path\to\python.exe]
rem The Python must be the same version (and 64-bit) as the one set in
rem OBS > Tools > Scripts > Python Settings.
setlocal
cd /d "%~dp0"

set "PY=%~1"
if not "%PY%"=="" goto have_python
py -3.12 -c "" >nul 2>nul && set "PY=py -3.12" && goto have_python
python -c "" >nul 2>nul && set "PY=python" && goto have_python
echo Python was not found. Install 64-bit Python 3.12 from https://www.python.org/downloads/
echo or run: setup.bat C:\path\to\python.exe
exit /b 1

:have_python
for /f "delims=" %%v in ('%PY% -c "import sys; print('%%d.%%d' %% sys.version_info[:2])"') do set "PYVER=%%v"
for /f "delims=" %%p in ('%PY% -c "import sys; print(sys.base_prefix)"') do set "PYHOME=%%p"
echo Using Python %PYVER% from %PYHOME%

%PY% -c "import struct, sys; sys.exit(struct.calcsize('P') != 8)"
if errorlevel 1 (
    echo ERROR: this Python is 32-bit. OBS needs 64-bit Python.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv ...
    %PY% -m venv .venv
    if errorlevel 1 exit /b 1
) else (
    echo Reusing existing .venv. Delete the .venv folder to recreate it.
)

".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Done. Next, in OBS:
echo   1. Tools ^> Scripts ^> Python Settings: set the install path to
echo        %PYHOME%
echo   2. Scripts tab: press + and choose %~dp0peercam_bridge.py
endlocal
