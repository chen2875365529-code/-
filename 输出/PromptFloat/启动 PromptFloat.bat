@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 goto runpython
start "" pythonw "%~dp0prompt_float.py"
exit /b
:runpython
python "%~dp0prompt_float.py"
