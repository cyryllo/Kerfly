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
    copy /y requirements.txt ".venv\kerfly-requirements.txt" >nul
)
rem after an update: install libraries that were added since the last start
fc /b requirements.txt ".venv\kerfly-requirements.txt" >nul 2>nul
if errorlevel 1 (
    echo Updating the libraries ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt && copy /y requirements.txt ".venv\kerfly-requirements.txt" >nul
)
rem the optional libraries (pyclipper: offsets and the boundary trace; spyrrow: nesting by outlines), also
rem those added in an update; tried once for each change of the list: Kerfly works without them
fc /b requirements-optional.txt ".venv\kerfly-requirements-optional.txt" >nul 2>nul
if errorlevel 1 (
    echo Installing the optional libraries ...
    ".venv\Scripts\python.exe" -m pip install -r requirements-optional.txt || echo Some optional libraries were not installed; Kerfly works without them, with fewer functions.
    copy /y requirements-optional.txt ".venv\kerfly-requirements-optional.txt" >nul
)
".venv\Scripts\python.exe" kerfly.py %*
if errorlevel 1 pause
