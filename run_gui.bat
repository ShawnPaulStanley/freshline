@echo off
setlocal

cd /d "%~dp0"

echo =====================================
echo        FreshLine GUI Launcher
echo =====================================
echo.

set "PY_CMD="

where py >nul 2>nul
if %errorlevel%==0 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=py -3.12"
        goto :python_found
    )

    py -3.13 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=py -3.13"
        goto :python_found
    )

    set "PY_CMD=py -3"
    goto :python_found
)

where python >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=python"
    goto :python_found
)

echo Python was not found on PATH.
echo Install Python 3.12+ and try again.
echo.
pause
exit /b 1

:python_found

%PY_CMD% -c "import javalang, networkx, groq, rich, dotenv" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies detected. Installing from requirements.txt...
    %PY_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Dependency installation failed.
        echo Try running this manually in the project folder:
        echo   %PY_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

%PY_CMD% -m app.gui
if errorlevel 1 (
    echo.
    echo Failed to launch FreshLine GUI.
    echo Try running manually:
    echo   %PY_CMD% -m app.gui
    echo.
    pause
)

endlocal
