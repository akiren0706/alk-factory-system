@echo off
chcp 65001 > nul
echo ALK 自動インポートを停止しています...

REM タイトル "ALK自動インポート" のウィンドウを終了
taskkill /FI "WINDOWTITLE eq ALK自動インポート" /F > nul 2>&1

REM pythonw プロセスを名前で止める（念のため）
taskkill /FI "IMAGENAME eq pythonw.exe" /F > nul 2>&1

REM ステータスファイルを「停止中」に更新
python -c "
import json; from pathlib import Path
f = Path('data/auto_import_status.json')
if f.exists():
    d = json.loads(f.read_text(encoding='utf-8'))
    d['running'] = False
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
"

echo 停止しました。
timeout /t 2 > nul
