# ALK データ一括取込

`C:\Users\r-akiyama\Desktop\１C生産データ` フォルダ内の全XLSXを解析し、
operative_data.csv に未取込のデータを取り込む。

## 手順

1. フォルダ内の全XLSXをスキャン（サブフォルダも含む）
2. operative_data.csv の既存データと照合
3. 新規レコードがあるファイルのみ取込実行
4. 結果を報告

## 実行スクリプト

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\Users\r-akiyama\Desktop\ALK工場生産管理システム')
from pathlib import Path
import io as _io
import pandas as pd
from utils.operative_parser import is_operative_format, parse_operative_file
from utils.data_store import add_operative

watch = Path(r'C:\Users\r-akiyama\Desktop\１C生産データ')
csv = Path(r'C:\Users\r-akiyama\Desktop\ALK工場生産管理システム\data\operative_data.csv')
df_db = pd.read_csv(csv, dtype=str)
db_keys = set(zip(df_db['date'], df_db['factory'], df_db['indicator_ru']))

all_xlsx = sorted(watch.rglob('*.xlsx'))
total_added = 0
new_files = 0

for fpath in all_xlsx:
    try:
        buf = _io.BytesIO(fpath.read_bytes())
        if not is_operative_format(buf):
            continue
        buf.seek(0)
        records, detected_date, errors = parse_operative_file(buf)
        if not records:
            continue
        new_recs = [r for r in records
                    if (r.get('date',''), r.get('factory',''), r.get('indicator_ru','')) not in db_keys]
        if new_recs:
            added, _ = add_operative(records)
            if added > 0:
                total_added += added
                new_files += 1
                print(f'✅ {fpath.name}: {added}件追加 (日付={detected_date})')
                for r in records:
                    db_keys.add((r.get('date',''), r.get('factory',''), r.get('indicator_ru','')))
    except Exception as e:
        print(f'❌ {fpath.name}: {e}')

print(f'\n合計: {new_files}ファイル / {total_added}件追加')
```

このスクリプトをPythonで実行して結果を報告すること。
