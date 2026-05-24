"""
1C オペレーティブサマリー（Оперативная сводка）パーサー
"""
import zipfile, io, re
import pandas as pd
from datetime import datetime

# シート名 → 工場名マッピング
_SHEET_FACTORY = {
    'УПСС': '土場',
    'ПМ':   '製材工場',
    'ЦЛП':  '製材工場',
    'ЦПШ':  '単板工場',
    'ДГ':   'ペレット工場',
    'ЦПФ':  '合板工場',
    'СГП':  '製品在庫',
    'МЛП':  '簡易製材工場',
}

# 日報で重要な指標（先頭部分一致）
KEY_INDICATOR_PREFIXES = {
    '単板工場':   ['Получено сухого шпона', 'Подано на лущение', 'Получено лущенного шпона'],
    '製材工場':   ['Производство (товарное)', 'Производство (валовое)', 'Подано в производство'],
    'ペレット工場': ['Производство пеллет', 'Упаковано всего', 'Потребление на производство'],
    '合板工場':   ['Получено необрезной фанеры', 'Подано на линии наборки', 'Полезный выход'],
    '土場':       ['Поступило сырья', 'Сортировка сырья'],
    '製品在庫':   ['Поступило на склад', 'Отгружено с СГП'],
}


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


def _factory_from_sheet(sheet_name: str) -> str:
    su = sheet_name.upper()
    for code, factory in _SHEET_FACTORY.items():
        if code in su:
            return factory
    return ''


def _extract_date(df: pd.DataFrame) -> str:
    for i in range(min(6, len(df))):
        for v in df.iloc[i]:
            if pd.isna(v):
                continue
            m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', str(v))
            if m:
                try:
                    return datetime.strptime(m.group(0), '%d.%m.%Y').strftime('%Y-%m-%d')
                except Exception:
                    pass
    return ''


def _find_cols(df: pd.DataFrame) -> tuple[int, int, int, int]:
    """unit_col, plan_col, fact_col, data_start_row を返す"""
    for ri in range(min(10, len(df))):
        row = df.iloc[ri]
        vals = [str(v).strip() if not pd.isna(v) else '' for v in row]
        vl = [v.lower() for v in vals]
        unit_col  = next((ci for ci, v in enumerate(vl) if 'ед. изм' in v or 'ед.изм' in v), -1)
        fact_col  = next((ci for ci, v in enumerate(vl) if v == 'факт'), -1)
        plan_col  = next((ci for ci, v in enumerate(vl) if 'плановое задание' in v or 'цель/план' in v), -1)
        if unit_col >= 0 and fact_col >= 0:
            return unit_col, plan_col, fact_col, ri + 1
    return -1, -1, -1, 5


def _is_eds(df: pd.DataFrame) -> bool:
    """EDS（昼/夜シフト別）フォーマットか判定"""
    for i in range(min(8, len(df))):
        vals = [str(v) if not pd.isna(v) else '' for v in df.iloc[i]]
        joined = ' '.join(vals)
        if 'День' in joined and 'Ночь' in joined:
            return True
    return False


def _is_operative_sheet(df: pd.DataFrame) -> bool:
    for i in range(min(6, len(df))):
        for v in df.iloc[i]:
            if pd.isna(v):
                continue
            s = str(v)
            if any(kw in s for kw in ('Оперативная сводка', 'Оперативный рапорт', 'Начало периода')):
                return True
    return False


def _to_num(v):
    try:
        if pd.isna(v):
            return None
        return float(str(v).strip().replace(',', '.'))
    except Exception:
        return None


def _parse_name(text: str) -> tuple[str, str]:
    """'Russian / Japanese' → (ru, jp)"""
    text = str(text).strip()
    if ' / ' in text:
        parts = text.split(' / ', 1)
        return parts[0].strip(), parts[1].strip()
    return text, ''


def _parse_daily(df, date_str, factory, unit_col, plan_col, fact_col, start_row) -> list[dict]:
    records = []
    for i in range(start_row, len(df)):
        row = df.iloc[i]
        raw = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ''
        if not raw or raw.lower() == 'nan':
            continue
        unit = str(row.iloc[unit_col]).strip() if unit_col < len(row) and not pd.isna(row.iloc[unit_col]) else ''
        if not unit or unit.lower() in ('nan', '', 'ед. изм-ия', 'ед.изм.', 'ед. изм.'):
            continue
        plan = _to_num(row.iloc[plan_col]) if plan_col >= 0 and plan_col < len(row) else None
        fact = _to_num(row.iloc[fact_col]) if fact_col < len(row) else None
        if fact is None and plan is None:
            continue
        ru, jp = _parse_name(raw)
        records.append({
            'date': date_str, 'factory': factory,
            'indicator_ru': ru, 'indicator_jp': jp,
            'unit': unit,
            'plan': plan,
            'fact': fact,
            'sheet_type': '日次',
        })
    return records


def _parse_eds(df, date_str, factory) -> list[dict]:
    """EDS昼夜合計形式をパース"""
    records = []
    unit_col = day_fact = night_fact = day_plan = -1
    start_row = 5

    for ri in range(min(10, len(df))):
        row = df.iloc[ri]
        vals = [str(v).strip() if not pd.isna(v) else '' for v in row]
        vl = [v.lower() for v in vals]
        uc = next((ci for ci, v in enumerate(vl) if 'ед. изм' in v or 'ед.изм' in v), -1)
        facts = [ci for ci, v in enumerate(vl) if v == 'факт']
        plans = [ci for ci, v in enumerate(vl) if 'цель/план' in v or 'плановое' in v]
        if uc >= 0 and len(facts) >= 1:
            unit_col  = uc
            day_fact  = facts[0]
            night_fact = facts[1] if len(facts) >= 2 else -1
            day_plan  = plans[0] if plans else -1
            start_row = ri + 1
            break

    if unit_col < 0:
        return []

    for i in range(start_row, len(df)):
        row = df.iloc[i]
        raw = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ''
        if not raw or raw.lower() == 'nan':
            continue
        unit = str(row.iloc[unit_col]).strip() if unit_col < len(row) and not pd.isna(row.iloc[unit_col]) else ''
        if not unit or unit.lower() in ('nan', ''):
            continue
        df_val = _to_num(row.iloc[day_fact])  if day_fact   >= 0 and day_fact   < len(row) else None
        nf_val = _to_num(row.iloc[night_fact]) if night_fact >= 0 and night_fact < len(row) else None
        dp_val = _to_num(row.iloc[day_plan])   if day_plan   >= 0 and day_plan   < len(row) else None

        fact = (df_val or 0) + (nf_val or 0) if (df_val is not None or nf_val is not None) else None
        if fact is None:
            continue
        ru, jp = _parse_name(raw)
        records.append({
            'date': date_str, 'factory': factory,
            'indicator_ru': ru, 'indicator_jp': jp,
            'unit': unit,
            'plan': None if dp_val is None else dp_val * 2,
            'fact': fact,
            'sheet_type': 'EDS昼夜合計',
        })
    return records


def is_operative_format(file_buffer) -> bool:
    """1C日報ファイルか判定"""
    try:
        file_buffer.seek(0)
        buf = _fix_xlsx(file_buffer)
        xl = pd.ExcelFile(buf, engine='openpyxl')
        for sheet in xl.sheet_names[:4]:
            buf.seek(0)
            df = pd.read_excel(buf, sheet_name=sheet, header=None, nrows=10, dtype=str, engine='openpyxl')
            if _is_operative_sheet(df):
                return True
        return False
    except Exception:
        return False
    finally:
        try:
            file_buffer.seek(0)
        except Exception:
            pass


def parse_operative_file(file_buffer) -> tuple[list[dict], str, list[str]]:
    """
    1C日報ファイルをパース。
    Returns: (records, detected_date, errors)
    """
    records, errors = [], []
    detected_date = ''

    try:
        file_buffer.seek(0)
        buf = _fix_xlsx(file_buffer)
        xl = pd.ExcelFile(buf, engine='openpyxl')

        for sheet_name in xl.sheet_names:
            buf.seek(0)
            try:
                df = pd.read_excel(buf, sheet_name=sheet_name, header=None, dtype=str, engine='openpyxl')
            except Exception as e:
                errors.append(f'[{sheet_name}] 読込エラー: {e}')
                continue

            if not _is_operative_sheet(df):
                continue

            date_str = _extract_date(df)
            if not date_str:
                errors.append(f'[{sheet_name}] 日付を検出できませんでした')
                continue
            if not detected_date:
                detected_date = date_str

            factory = _factory_from_sheet(sheet_name)
            if not factory:
                errors.append(f'[{sheet_name}] 工場名を自動検出できませんでした（スキップ）')
                continue

            if _is_eds(df):
                recs = _parse_eds(df, date_str, factory)
            else:
                unit_col, plan_col, fact_col, start_row = _find_cols(df)
                if unit_col < 0 or fact_col < 0:
                    errors.append(f'[{sheet_name}] 列構造を検出できませんでした')
                    continue
                recs = _parse_daily(df, date_str, factory, unit_col, plan_col, fact_col, start_row)

            records.extend(recs)

    except Exception as e:
        errors.append(f'ファイル解析エラー: {e}')

    return records, detected_date, errors
