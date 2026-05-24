# ALK 未取込データ詳細レポート

operative_data.csvを分析して未取込日付の詳細レポートを生成する。

## 実行内容

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
from pathlib import Path
from datetime import date, timedelta

csv = Path(r'C:\Users\r-akiyama\Desktop\ALK工場生産管理システム\data\operative_data.csv')
watch = Path(r'C:\Users\r-akiyama\Desktop\１C生産データ')

df = pd.read_csv(csv, dtype=str)
imported = set(df['date'].unique())

date_from = date(2025, 1, 1)
today = date.today()
all_dates = [(date_from + timedelta(days=i)).isoformat() for i in range((today - date_from).days + 1)]
missing = [d for d in all_dates if d not in imported]

# フォルダにファイルがあるか確認
import re
dated_files = {}
for f in watch.rglob('*.xlsx'):
    m = re.match(r'(\d{4}-\d{2}-\d{2})', f.name)
    if m:
        d = m.group(1)
        if d not in dated_files:
            dated_files[d] = []
        dated_files[d].append(f.name)

print(f"取込済み日数: {len(imported)}")
print(f"未取込日数: {len(missing)}")
print()

# 連続する欠損期間をグループ化
if missing:
    groups = []
    start = missing[0]
    prev = missing[0]
    for d in missing[1:]:
        curr = date.fromisoformat(d)
        prev_d = date.fromisoformat(prev)
        if (curr - prev_d).days == 1:
            prev = d
        else:
            groups.append((start, prev))
            start = d
            prev = d
    groups.append((start, prev))
    
    print("=== 未取込期間（連続グループ） ===")
    for s, e in groups:
        days = (date.fromisoformat(e) - date.fromisoformat(s)).days + 1
        in_folder = sum(1 for d in (s, e) if d in dated_files)
        print(f"  {s} 〜 {e} ({days}日間) | フォルダあり:{in_folder}日")
```

このスクリプトを実行して、以下の形式で報告すること：

1. **取込済み・未取込のサマリー**
2. **未取込期間のグループ一覧**（連続した欠損をまとめる）
3. **フォルダにファイルがある未取込日** → 取込可能なものはその場で取込む
4. **フォルダにもファイルがない日** → 「1Cシステムからのデータが届いていない」と説明
