@echo off
cd /d "%~dp0"
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0start_smartcart.py"
if errorlevel 1 pause
