@echo off
cd /d "%~dp0"
py -m pip install --user -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Is Python installed? https://www.python.org/downloads/
  pause
  exit /b 1
)
start "" pyw Roadhub.pyw
