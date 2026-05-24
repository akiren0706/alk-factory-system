@echo off
set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
set SCRIPT=%~dp01c_outlook_download.py
"%PYTHON%" "%SCRIPT%"
pause