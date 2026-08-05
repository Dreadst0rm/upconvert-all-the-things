@echo off
setlocal
cd /d "%~dp0"

REM Prefer `py -3`, then `python` on PATH
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo ERROR: Python was not found on PATH.
  echo Install Python 3.11+ and re-open this window, or run:
  echo   py -3 -m pip install -e ".[dev]"
  pause
  exit /b 1
)

echo Starting UpConvert All The Things...
%PY% -m upconvert_all --gui
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo Launcher exited with code %ERR%.
  echo If the module is missing, run:
  echo   %PY% -m pip install -e ".[dev]"
  pause
)
exit /b %ERR%
