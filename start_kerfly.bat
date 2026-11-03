@echo off
rem Start Kerfly on Windows. The first start creates a Python environment in
rem the .venv folder and installs the libraries (needs internet, a few minutes).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating the Python environment in .venv ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Python was not found. Install Python 3 from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during installation.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Installing the libraries failed. Check the internet connection and run this file again.
        rmdir /s /q .venv
        pause
        exit /b 1
    )
    rem optional: offset of the boundary trace; Kerfly works without it
    ".venv\Scripts\python.exe" -m pip install -r requirements-optional.txt || echo Optional library pyclipper was not installed; Kerfly works without it.
)
".venv\Scripts\python.exe" kerfly.py %*
if errorlevel 1 pause
