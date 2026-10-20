@echo off
REM Double-click this file to start the Smart Sugarcane Irrigation dashboard
cd /d "%~dp0"
where python >NUL 2>NUL && (python main.py) || (py main.py)
if errorlevel 1 pause
