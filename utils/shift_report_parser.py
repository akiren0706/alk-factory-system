"""
Сменный рапорт мастера ЦЛП パーサー
製材工場のシフトレポートから停止データを抽出する
"""
import zipfile, io, re
import pandas as pd
from datetime import datetime

FACTORY = '製材工場'

# 停止データの列インデックス（25列構成）
_COL_AREA     = 0
_COL_START    = 15   # Время начала
_COL_END      = 18   # Время завершения
_COL_DURATION = 21   # Простой (HH:MM:SS)
_COL_TYPE     = 22   # Тип простоя
_COL_COMMENT  = 23   # Комментарий
_COL_MACHINE  = 24   # Машинный центр


def _fix_xlsx(file_buffer) -> io.BytesIO:
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


def _cell(row, col) -> str:
    if col >= len(row):
        return ''
    v = row.iloc[col]
    if pd.isna(v):
        return ''
    return str(v).strip()


def _parse_date(s: str) -> str:
    s = s.strip()
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', s)
    if m:
        try:
            return datetime.strptime(m.group(0), '%d.%m.%Y').strftime('%Y-%m-%d')
        except Exception:
            pass
    return ''


def _duration_to_minutes(s: str):
    """HH:MM:SS → float minutes、変換失敗時は None"""
    s = str(s).strip()
    if not s or s.lower() == 'nan':
        return None
    m = re.match(r'(\d+):(\d{2}):(\d{2})', s)
    if m:
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
        total = h * 60 + mi + sec / 60
        return round(total, 2)
    return None


def is_shift_report_format(file_buffer) -> bool:
    """Сменный рапорト ファイルか判定"""
    try:
        file_buffer.seek(0)
        buf = _fix_xlsx(file_buffer)
        xl = pd.ExcelFile(buf, engine='openpyxl')
        if 'TDSheet' not in xl.sheet_names:
            return False
        buf.seek(0)
        df = pd.read_excel(buf, sheet_name='TDSheet', header=None, nrows=5, dtype=str, engine='openpyxl')
        for i in range(min(3, len(df))):
            for v in df.iloc[i]:
                if not pd.isna(v) and 'Сменный рапорт' in str(v):
                    return True
        return False
    except Exception:
        return False
    finally:
        try:
            file_buffer.seek(0)
        except Exception:
            pass


def parse_shift_report(file_buffer) -> tuple[list[dict], str, list[str]]:
    """
    Сменный рапорт から停止データを抽出。
    Returns: (records, detected_date, errors)
    """
    records, errors = [], []
    detected_date = ''

    try:
        file_buffer.seek(0)
        buf = _fix_xlsx(file_buffer)
        xl = pd.ExcelFile(buf, engine='openpyxl')

        if 'TDSheet' not in xl.sheet_names:
            errors.append('TDSheet シートが見つかりません')
            return records, detected_date, errors

        buf.seek(0)
        df = pd.read_excel(buf, sheet_name='TDSheet', header=None, dtype=str, engine='openpyxl')

        # 日付を取得（行2〜4のセルから探す）
        for ri in range(2, min(6, len(df))):
            for ci in range(min(5, df.shape[1])):
                v = _cell(df.iloc[ri], ci)
                d = _parse_date(v)
                if d:
                    detected_date = d
                    break
            if detected_date:
                break

        if not detected_date:
            errors.append('日付を検出できませんでした')
            return records, detected_date, errors

        # 停止データのヘッダー行を探す（「Время начала」を含む行）
        header_row = -1
        for ri in range(len(df)):
            row_str = ' '.join(str(v) for v in df.iloc[ri] if not pd.isna(v))
            if 'Время начала' in row_str and 'Время завершения' in row_str:
                header_row = ri
                break

        if header_row < 0:
            # 停止データなし（正常ケース）
            return records, detected_date, errors

        # ヘッダー行の列番号を動的に解決
        hrow = df.iloc[header_row]
        col_start = col_end = col_dur = col_type = col_comment = col_machine = -1
        for ci, v in enumerate(hrow):
            s = str(v).strip() if not pd.isna(v) else ''
            if s == 'Время начала':
                col_start = ci
            elif s == 'Время завершения':
                col_end = ci
            elif s == 'Простой':
                col_dur = ci
            elif s == 'Тип простоя':
                col_type = ci
            elif s == 'Комментарий':
                col_comment = ci
            elif s == 'Машинный центр':
                col_machine = ci

        if col_start < 0 or col_dur < 0:
            errors.append('停止データの列構成を解析できませんでした')
            return records, detected_date, errors

        # 停止データ行を読む（Выполнение задания まで）
        current_area = ''
        for ri in range(header_row + 1, len(df)):
            row = df.iloc[ri]
            area_val = _cell(row, _COL_AREA)
            start_val = _cell(row, col_start) if col_start >= 0 else ''
            end_val   = _cell(row, col_end)   if col_end   >= 0 else ''
            dur_val   = _cell(row, col_dur)   if col_dur   >= 0 else ''
            type_val  = _cell(row, col_type)  if col_type  >= 0 else ''
            comment_val  = _cell(row, col_comment)  if col_comment  >= 0 else ''
            machine_val  = _cell(row, col_machine)  if col_machine  >= 0 else ''

            # 終了判定
            if area_val and 'Выполнение задания' in area_val:
                break

            if area_val:
                current_area = area_val

            # 実績行（停止開始時刻あり＆所要時間あり）のみ取込み
            if not start_val or not dur_val:
                continue

            duration_min = _duration_to_minutes(dur_val)
            if duration_min is None:
                continue

            notes_parts = [p for p in [comment_val, machine_val] if p]
            notes = ' / '.join(notes_parts)

            records.append({
                'date': detected_date,
                'factory': FACTORY,
                'area': current_area,
                'stop_time': start_val,
                'recovery_time': end_val,
                'duration_minutes': duration_min,
                'reason': type_val,
                'response': '',
                'notes': notes,
            })

    except Exception as e:
        errors.append(f'ファイル解析エラー: {e}')

    return records, detected_date, errors
