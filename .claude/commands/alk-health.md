# ALK システム ヘルスチェック

システム全体の状態を診断して報告する。以下を順番に確認すること：

## 1. データファイル確認
```python
# 実行してCSVの状態を確認
import pandas as pd
from pathlib import Path

base = Path(r"C:\Users\r-akiyama\Desktop\ALK工場生産管理システム\data")
for f in ["operative_data.csv", "stoppages.csv", "production.csv"]:
    p = base / f
    if p.exists():
        df = pd.read_csv(p, dtype=str)
        print(f"{f}: {len(df)}行, 日付範囲={df['date'].min() if 'date' in df.columns else 'N/A'}〜{df['date'].max() if 'date' in df.columns else 'N/A'}")
    else:
        print(f"{f}: ❌ 存在しない")
```

## 2. 未取込日付チェック
2025年1月1日から本日までで、operative_data.csvに存在しない日付を洗い出す。
未取込が100日以上ある場合は「2025年1月〜5月は1Cシステムのデータが存在しない」と説明する。

## 3. 自動インポートステータス
`data/auto_import_status.json` を読んで稼働状態を報告する。

## 4. 監視フォルダ確認
`C:\Users\r-akiyama\Desktop\１C生産データ` のルートに処理待ちXLSXがないか確認する。

## 5. レポート形式
以下の形式で出力すること：

```
=== ALK システム ヘルスチェック ===
📊 生産指標DB : X件 (YYYY-MM-DD 〜 YYYY-MM-DD)
⏸️ 停止データDB: X件
📦 生産データDB: X件

⚠️ 未取込日数: X日
  - 2025-01-01〜05-21: データ未存在（1C送信なし）
  - YYYY-MM-DD〜: 要確認

🤖 自動インポート: 稼働中 / 停止中
   最終チェック: YYYY-MM-DD HH:MM
   最終取込: YYYY-MM-DD HH:MM

📁 処理待ちファイル: X件
```
