import pandas as pd
import io
import zipfile
import re
from datetime import datetime
from utils.master_data import translate, detect_field, STOPPAGE_FIELDS, PRODUCTION_FIELDS


def _fix_xlsx(file_buffer) -> io.BytesIO:
    """1C xlsx の SharedStrings.xml 大文字問題を修正"""
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(file_buffer, 'r') as zin:
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    new_name = item.filename.replace('xl/SharedStrings.xml', 'xl/sharedStrings.xml')
                    if item.filename.endswith('.xml') or item.filename.endswith('.rels'):
                        data = data.replace(b'SharedStrings.xml', b'sharedStrings.xml')
                    item.filename = new_name
                    zout.writestr(item, data)
    except Exception:
        try:
            file_buffer.seek(0)
        except Exception:
            pass
        return file_buffer
    buf.seek(0)
    return buf


def read_excel(uploaded_file) -> tuple[pd.DataFrame, str]:
    """
    アップロードされたExcelファイルを読み込む。
    Returns: (DataFrame, error_message)
    """
    try:
        ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            df = pd.read_csv(uploaded_file, dtype=str, encoding_errors="replace")
        else:
            uploaded_file.seek(0)
            raw = io.BytesIO(uploaded_file.read())
            fixed = _fix_xlsx(raw)
            df = pd.read_excel(fixed, dtype=str, header=None, engine='openpyxl')
            # ヘッダー行を検出（最初の非空行）
            header_idx = 0
            for i, row in df.iterrows():
                if row.notna().any() and any(str(v).strip() for v in row if pd.notna(v)):
                    header_idx = i
                    break
            df.columns = [str(v).strip() if pd.notna(v) else f"列{i+1}"
                          for i, v in enumerate(df.iloc[header_idx])]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)
            df = df.dropna(how="all")
        return df, ""
    except Exception as e:
        return pd.DataFrame(), str(e)


def auto_detect_mapping(columns: list[str], data_type: str) -> dict[str, str]:
    """列名からフィールドマッピングを自動検出する"""
    return {col: detect_field(col, data_type) for col in columns}


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str], factory: str, data_type: str) -> list[dict]:
    """
    マッピングに従ってDataFrameをシステムレコードのリストに変換する。
    """
    records = []
    fields = STOPPAGE_FIELDS if data_type == "stoppage" else PRODUCTION_FIELDS

    # フィールドキー → 列名の逆マッピング（最初にマッチしたものを使う）
    field_to_col: dict[str, str] = {}
    for col, field in mapping.items():
        if field != "_ignore" and field not in field_to_col:
            field_to_col[field] = col

    for _, row in df.iterrows():
        record: dict = {}

        for field_key, _, _ in fields:
            col = field_to_col.get(field_key)
            val = str(row[col]).strip() if col and col in row.index and pd.notna(row[col]) else ""

            if field_key == "date":
                val = _parse_date(row[col] if col and col in row.index else "")
            elif field_key in ("factory",):
                val = translate(val) or factory
            elif field_key == "area":
                val = translate(val)
            elif field_key in ("duration_minutes", "quantity", "operating_hours"):
                val = _parse_number(val)

            record[field_key] = val if val is not None else ""

        # 工場は選択値で上書き（列マッピングより優先）
        record["factory"] = factory

        # 停止時間を自動計算（duration が空で stop/recovery がある場合）
        if data_type == "stoppage":
            if not record.get("duration_minutes") and record.get("stop_time") and record.get("recovery_time"):
                record["duration_minutes"] = _calc_duration(record["stop_time"], record["recovery_time"])

        # 日付がある行だけ追加
        if record.get("date"):
            records.append(record)

    return records


def _parse_date(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return ""
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    # DD.MM.YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # Excelシリアル値
    try:
        n = float(s)
        if 1 < n < 100000:
            d = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(n))
            return d.strftime("%Y-%m-%d")
    except ValueError:
        pass
    return ""


def _parse_number(val) -> float | str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return ""


def _calc_duration(stop_time: str, recovery_time: str) -> float | str:
    def to_minutes(t):
        m = re.search(r"(\d{1,2}):(\d{2})", str(t))
        if not m:
            return None
        return int(m.group(1)) * 60 + int(m.group(2))

    s, e = to_minutes(stop_time), to_minutes(recovery_time)
    if s is None or e is None:
        return ""
    diff = e - s
    if diff < 0:
        diff += 1440  # 翌日またぎ
    return diff
