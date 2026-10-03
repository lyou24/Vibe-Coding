@echo off
cd /d "%~dp0"

echo =======================================================
echo Ongeki Recommend App Starter
echo =======================================================

SET "VENV_OK=0"
IF EXIST "backend\venv\Scripts\python.exe" (
    backend\venv\Scripts\python.exe -V >nul 2>&1
    IF NOT ERRORLEVEL 1 SET "VENV_OK=1"
)

IF "%VENV_OK%"=="0" (
    echo [Setup] Creating Python virtual environment...
    IF EXIST "backend\venv" rmdir /s /q "backend\venv"
    
    python -m venv backend\venv
    if errorlevel 1 (
        py -3 -m venv backend\venv
        if errorlevel 1 (
            echo [Error] Python 3 is not installed or not in PATH.
            echo Please install Python 3.10+ from https://www.python.org/downloads/
            echo Make sure to check "Add Python to PATH" during installation.
            pause
            exit /b 1
        )
    )
    echo [Setup] Installing required libraries...
    call backend\venv\Scripts\activate
    pip install -r backend\requirements.txt
    call deactivate
    echo.
    echo [Setup] Setup completed successfully!
)

echo Starting backend server...
echo The browser will open automatically when ready.
echo Keep this window open to run the server. Close it to stop.
echo =======================================================
echo.

echo Set objShell = CreateObject("WScript.Shell") > open_browser.vbs
echo WScript.Sleep 4000 >> open_browser.vbs
echo objShell.Run "http://localhost:8000" >> open_browser.vbs
start wscript open_browser.vbs

cd backend
call venv\Scripts\activate
python -m uvicorn server:app --host 0.0.0.0 --port 8000

pause
