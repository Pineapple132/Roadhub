@echo off
cd /d "%~dp0"
py -m pip install --user -r requirements.txt pyinstaller
py -m PyInstaller --noconsole --onefile --add-data "roadhub\europe_shapes.json;roadhub" --name Roadhub Roadhub.pyw
echo.
echo Done: dist\Roadhub.exe
pause
