@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 scripts\launch.py %*
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python is not installed or is not on PATH.
    echo Install Python 3.13 from python.org and enable Add Python to PATH.
    echo Then run this file again. No Google account password is required.
    pause
    exit /b 1
  )
  python scripts\launch.py %*
)
echo.
echo Xcomify has stopped. Review any messages above.
pause
