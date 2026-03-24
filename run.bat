@echo off
cd /d "%~dp0"
echo Starting POE2 Flipper...
echo Browser will open automatically at http://localhost:5000
echo Press Ctrl+C to stop the server.
echo.
python app.py
pause
