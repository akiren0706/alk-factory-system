@echo off
cd /d "%~dp0"

set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PYTHON%" set PYTHON=python

"%PYTHON%" -m pip install -r requirements.txt -q 2>nul

"%PYTHON%" -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
pause
