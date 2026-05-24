"""
ペレット工場等の階層型停止レポートCSV/XLSXパーサー

フォーマット:
  - ヘッダー部: Data parameters / Filter でエリア名を取得
  - データ部: 停止タイプ → サブ分類 → 設備名 → イベント行 → 日付行 の入れ子構造
  - 時間列: "Факт, ч"（実績時間/h）→ ×60 して分に変換
"""

import re
import io
import pandas as pd

# 停止タイプのロシア語→日本語
STOP_TYPE_MAP = {
    "организационный": "組織的停止",
    "технический":     "技術的停止（設備）",
    "технологический": "工程的停止",
    "джерменное то":   "定期保全",
    "плановое то":     "計画保全",
    "то (плановое)":   "計画保全",
    "нор":             "計画停止（НОР）",
}

KNOWN_TYPE_KEYWORDS = list(STOP_TYPE_MAP.keys())

# Filter行の「Участок」名から工場を判定するキーワード（エリア名だけに適用）
_AREA_KEYWORDS = [
    ("гранул",          "ペレット工場"),
    ("пеллет",          "ペレット工場"),
    ("(дг)",            "ペレット工場"),
    ("дг)",             "ペレット工場"),
    (" дг ",            "ペレット工場"),
    ("шпон",            "単板工場"),
    ("лущ",             "単板工場"),
    ("гидротерм",       "単板工場"),
    ("фанер",           "合板工場"),
    ("прессован",       "合板工場"),
    ("пилом",           "製材工場"),
    ("лесопил",         "製材工場"),
    ("сушильн",         "製材工場"),
    ("млп",             "簡易製材工場"),
]

# エリア名キーワードで判定できない曖昧なエリアの直接マッピング
_AREA_EXACT_FACTORY = {
    "энергоцентр":                    "ペレット工場",
    "дежурный":                        "製材工場",
    "крановое хозяйство цлп":          "製材工場",
    "участок ручной сортировки":       "単板工場",
    "участок поддонов":                "単板工場",
    "компрессорная станция":           "単板工場",
}

# ヘッダー内の工場コード（短く具体的なコードのみ → 誤検知しにくい）
_HEADER_FACTORY_CODES = [
    ("(дг)",  "ペレット工場"),
    ("цлп",   "製材工場"),
    ("цпф",   "合板工場"),
    ("цпш",   "単板工場"),
    ("млп",   "簡易製材工場"),
]


def is_hierarchical_format(raw_lines: list[str]) -> bool:
    """先頭数行を見てこのフォーマットか判定する"""
    for line in raw_lines[:6]:
        if "data parameters" in line.lower() or "период отчета" in line.lower():
            return True
    return False


def _read_raw(file_buffer) -> list[list[str]]:
    """ファイルバッファから全行をリストとして読む（CSV/XLSX両対応）"""
    name = getattr(file_buffer, "name", "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "csv"

    if ext in ("xlsx", "xls"):
        df = pd.read_excel(file_buffer, header=None, dtype=str)
        df = df.fillna("")
        return df.values.tolist()
    else:
        raw = file_buffer.read()
        text = raw.decode("utf-8-sig", errors="replace")
        file_buffer.seek(0)
        reader_buf = io.StringIO(text)
        rows = []
        import csv
        for row in csv.reader(reader_buf):
            rows.append(row)
        return rows


def _get_cell(row: list, idx: int) -> str:
    if idx < len(row):
        v = str(row[idx]).strip()
        return v if v.lower() not in ("nan", "none") else ""
    return ""


def _parse_filter_area(rows: list[list[str]]) -> str:
    """Filter行から Участок 名を抽出する"""
    for row in rows[:10]:
        for cell in row:
            cell_str = str(cell)
            m = re.search(r'Участок Equal to "([^"]+)"', cell_str)
            if m:
                return m.group(1).strip()
    return ""


def _detect_factory(rows: list[list[str]], area_ru: str) -> str:
    """
    Filter行のエリア名（Участок）からどの工場か自動判定する。
    ヘッダー全体をスキャンすると他工場エリア名が混入するため、
    エリア名のみに絞って判定する。
    """
    area_lower = area_ru.strip().lower()

    # ステップ1: エリア名の完全一致（曖昧なエリア用）
    for key, factory in _AREA_EXACT_FACTORY.items():
        if area_lower == key or area_lower.startswith(key):
            return factory

    # ステップ2: エリア名のキーワードマッチ
    for kw, factory in _AREA_KEYWORDS:
        if kw in area_lower:
            return factory

    # ステップ3: ヘッダー先頭10行を短い工場コードのみでスキャン（最終手段）
    header_text = " ".join(
        str(cell).strip()
        for row in rows[:10]
        for cell in row
        if str(cell).strip().lower() not in ("", "nan")
    ).lower()
    for kw, factory in _HEADER_FACTORY_CODES:
        if kw in header_text:
            return factory

    return ""


def _find_header_row(rows: list[list[str]]) -> tuple[int, dict]:
    """
    Факт / Комментарий などを含む列ヘッダー行のインデックスと
    各フィールドの列インデックスを返す
    """
    for i, row in enumerate(rows[:15]):
        for j, cell in enumerate(row):
            if "факт" in str(cell).lower():
                col_map = {"name": 0, "fact": j, "comment": -1}
                for k, c in enumerate(row):
                    if "коммент" in str(c).lower():
                        col_map["comment"] = k
                return i, col_map
    return -1, {"name": 0, "fact": 3, "comment": 9}


def parse_hierarchical_stoppage(
    file_buffer, factory: str = ""
) -> tuple[list[dict], str, str]:
    """
    階層型停止レポートをパースして停止レコードのリストを返す。

    Returns:
        (records, area_jp, factory_detected)
        factory_detected: ファイルから自動検出した工場名（引数 factory が指定された場合はそちらを優先）
    """
    rows = _read_raw(file_buffer)
    if not rows:
        return [], "", factory

    area_ru = _parse_filter_area(rows)
    from utils.master_data import translate
    area_jp = translate(area_ru) if area_ru else ""

    # 工場の自動検出
    factory_detected = factory if factory else _detect_factory(rows, area_ru)

    header_idx, col_map = _find_header_row(rows)
    col_fact    = col_map["fact"]
    col_comment = col_map["comment"]

    data_rows = rows[header_idx + 1:] if header_idx >= 0 else rows[10:]

    records = []
    current_type    = ""
    current_subcat  = ""
    current_equip   = ""
    pending_event   = None

    EVENT_RE = re.compile(r"простой\s+оборудования\s+([А-ЯA-ZРP]\d+)", re.IGNORECASE)
    DATE_RE  = re.compile(r"^(\d{4})[/\-](\d{2})[/\-](\d{2})$")

    for row in data_rows:
        name_val    = _get_cell(row, col_map["name"])
        fact_val    = _get_cell(row, col_fact)
        comment_val = _get_cell(row, col_comment) if col_comment >= 0 else ""

        if not name_val and not fact_val:
            continue

        name_lower = name_val.lower()

        # ── 日付行（イベントの実際の停止日） ────────────────────
        m_date = DATE_RE.match(name_val)
        if m_date and pending_event is not None:
            y, mo, d = m_date.group(1), m_date.group(2), m_date.group(3)
            date_str = f"{y}-{mo}-{d}"
            hours   = _parse_float(fact_val or pending_event["fact_raw"])
            minutes = round(hours * 60) if hours else None

            reason_parts = []
            if current_type:   reason_parts.append(current_type)
            if current_subcat: reason_parts.append(current_subcat)
            if comment_val or pending_event["comment"]:
                reason_parts.append(comment_val or pending_event["comment"])
            reason = " / ".join(filter(None, reason_parts))

            records.append({
                "date":             date_str,
                "factory":          factory_detected,
                "area":             current_equip or area_jp,
                "stop_time":        "",
                "recovery_time":    "",
                "duration_minutes": minutes if minutes else "",
                "reason":           reason,
                "response":         "",
                "notes":            pending_event["reg_id"],
            })
            pending_event = None
            continue

        # ── イベント行（Простой оборудования...） ────────────────
        m_event = EVENT_RE.search(name_lower)
        if m_event:
            pending_event = {
                "reg_id":   m_event.group(1).upper(),
                "fact_raw": fact_val,
                "comment":  comment_val,
            }
            continue

        # ── タイプ行か判定 ───────────────────────────────────────
        matched_type = _match_type(name_lower)
        if matched_type:
            current_type   = matched_type
            current_subcat = ""
            current_equip  = ""
            pending_event  = None
            continue

        # ── その他の分類行（サブカテゴリ or 設備名） ─────────────
        if fact_val or name_val:
            if re.match(r"^[A-ZА-Яa-zа-я#№]", name_val) and name_val not in ("", " "):
                if len(name_val) > 40 or "пресс" in name_lower or "конвейер" in name_lower \
                        or "транспортер" in name_lower or "станок" in name_lower \
                        or "линия" in name_lower or "установка" in name_lower \
                        or "аспирац" in name_lower:
                    current_equip  = translate(name_val)
                    current_subcat = ""
                else:
                    current_subcat = translate(name_val)
                    current_equip  = ""

    return records, area_jp, factory_detected


def _match_type(name_lower: str) -> str:
    for ru, jp in STOP_TYPE_MAP.items():
        if name_lower.startswith(ru):
            return jp
    return ""


def _parse_float(val: str) -> float:
    if not val:
        return 0.0
    s = str(val).replace(",", ".").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0
