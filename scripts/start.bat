@echo off
chcp 65001 > nul
echo ALK 自動インポートを起動しています...

cd /d "%~dp0.."

REM 既に起動中かチェック
tasklist /FI "WINDOWTITLE eq ALK自動インポート" 2>nul | find "pythonw" >nul
if %errorlevel% == 0 (
    echo すでに起動中です。
    pause
    exit /b
)

start "ALK自動インポート" /min pythonw scripts\auto_import.py

echo 起動しました。バックグラウンドで動作中です。
echo （タスクバーには表示されません）
echo.
echo 停止するには stop.bat を実行してください。
timeout /t 3 > nul
