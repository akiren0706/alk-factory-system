import pandas as pd
from pathlib import Path
import uuid
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

STOPPAGE_FILE   = DATA_DIR / "stoppages.csv"
PRODUCTION_FILE = DATA_DIR / "production.csv"
OPERATIVE_FILE  = DATA_DIR / "operative_data.csv"

OPERATIVE_COLS = [
    "id", "imported_at", "date", "factory",
    "indicator_ru", "indicator_jp", "unit", "plan", "fact", "sheet_type",
]

STOPPAGE_COLS = [
    "id", "imported_at", "date", "factory", "area",
    "stop_time", "recovery_time", "duration_minutes",
    "reason", "response", "notes",
]
PRODUCTION_COLS = [
    "id", "imported_at", "date", "factory", "area",
    "product", "quantity", "unit", "operating_hours", "shift", "notes",
]


def _load(path: Path, cols: list) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def _save(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _is_blank(v) -> bool:
    return str(v).strip().lower() in ("", "nan", "none")


# ── 停止データ ──────────────────────────────────────────────
def get_stoppages(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if factory:
        df = df[df["factory"] == factory]
    if date_from:
        df = df[df["date"] >= date_from]
    if date_to:
        df = df[df["date"] <= date_to]
    df["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def _build_stoppage_key_sets(df: pd.DataFrame):
    # notes がある場合は "factory|notes" を一意キーとする（工場誤選択→削除→再取込に対応）
    existing_notes = set(
        f"{r.factory}|{r.notes}"
        for r in df.itertuples()
        if not _is_blank(r.notes)
    )
    existing_composite = set(
        f"{r.date}|{r.factory}|{r.area}|{r.duration_minutes}"
        for r in df.itertuples()
        if _is_blank(r.notes)
    )
    return existing_notes, existing_composite


def check_duplicates_stoppages(records: list[dict]) -> tuple[list[dict], int]:
    """重複しないレコードと重複件数を返す（保存しない）"""
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    existing_notes, existing_composite = _build_stoppage_key_sets(df)

    new_records, skipped = [], 0
    for r in records:
        notes = str(r.get("notes", "")).strip()
        date  = str(r.get("date", ""))
        fact  = str(r.get("factory", ""))
        area  = str(r.get("area", ""))
        dur   = str(r.get("duration_minutes", ""))

        notes_key = f"{fact}|{notes}" if notes else ""
        if notes_key and notes_key in existing_notes:
            skipped += 1
            continue
        if not notes:
            key = f"{date}|{fact}|{area}|{dur}"
            if key in existing_composite:
                skipped += 1
                continue

        new_records.append(r)
        if notes_key:
            existing_notes.add(notes_key)
        else:
            existing_composite.add(f"{date}|{fact}|{area}|{dur}")

    return new_records, skipped


def add_stoppages(records: list[dict]) -> tuple[int, int]:
    """Returns (added, skipped_duplicates)"""
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    existing_notes, existing_composite = _build_stoppage_key_sets(df)

    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0

    for r in records:
        notes = str(r.get("notes", "")).strip()
        date  = str(r.get("date", ""))
        fact  = str(r.get("factory", ""))
        area  = str(r.get("area", ""))
        dur   = str(r.get("duration_minutes", ""))

        notes_key = f"{fact}|{notes}" if notes else ""
        if notes_key and notes_key in existing_notes:
            skipped += 1
            continue
        if not notes:
            key = f"{date}|{fact}|{area}|{dur}"
            if key in existing_composite:
                skipped += 1
                continue

        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in STOPPAGE_COLS:
            r.setdefault(c, "")
        new_records.append(r)
        if notes_key:
            existing_notes.add(notes_key)
        else:
            existing_composite.add(f"{date}|{fact}|{area}|{dur}")

    if new_records:
        new_df = pd.DataFrame(new_records)[STOPPAGE_COLS]
        df = pd.concat([df, new_df], ignore_index=True)
        _save(df, STOPPAGE_FILE)

    return len(new_records), skipped


def delete_stoppage(row_id: str):
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    df = df[df["id"] != row_id]
    _save(df, STOPPAGE_FILE)


def delete_stoppages_bulk(
    factory: str = "", date_from: str = "", date_to: str = ""
) -> int:
    """条件に一致する停止データをまとめて削除。削除件数を返す。"""
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    if df.empty:
        return 0
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    mask = pd.Series([True] * len(df), index=df.index)
    if factory:
        mask &= df["factory"] == factory
    if date_from:
        mask &= df["date"] >= date_from
    if date_to:
        mask &= df["date"] <= date_to
    count = int(mask.sum())
    _save(df[~mask].reset_index(drop=True), STOPPAGE_FILE)
    return count


def preview_delete_stoppages(
    factory: str = "", date_from: str = "", date_to: str = ""
) -> pd.DataFrame:
    """削除対象になるレコードのプレビューを返す（実際には削除しない）。"""
    df = _load(STOPPAGE_FILE, STOPPAGE_COLS)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    mask = pd.Series([True] * len(df), index=df.index)
    if factory:
        mask &= df["factory"] == factory
    if date_from:
        mask &= df["date"] >= date_from
    if date_to:
        mask &= df["date"] <= date_to
    df["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")
    return df[mask].reset_index(drop=True)


# ── 生産データ ──────────────────────────────────────────────
def get_production(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    df = _load(PRODUCTION_FILE, PRODUCTION_COLS)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if factory:
        df = df[df["factory"] == factory]
    if date_from:
        df = df[df["date"] >= date_from]
    if date_to:
        df = df[df["date"] <= date_to]
    df["quantity"]        = pd.to_numeric(df["quantity"], errors="coerce")
    df["operating_hours"] = pd.to_numeric(df["operating_hours"], errors="coerce")
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def _build_production_key_set(df: pd.DataFrame) -> set:
    return set(
        f"{r.date}|{r.factory}|{r.area}|{r.product}"
        for r in df.itertuples()
    )


def check_duplicates_production(records: list[dict]) -> tuple[list[dict], int]:
    """重複しないレコードと重複件数を返す（保存しない）"""
    df = _load(PRODUCTION_FILE, PRODUCTION_COLS)
    existing = _build_production_key_set(df)

    new_records, skipped = [], 0
    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('area','')}|{r.get('product','')}"
        if key in existing:
            skipped += 1
            continue
        new_records.append(r)
        existing.add(key)

    return new_records, skipped


def add_production(records: list[dict]) -> tuple[int, int]:
    """Returns (added, skipped_duplicates)"""
    df = _load(PRODUCTION_FILE, PRODUCTION_COLS)
    existing = _build_production_key_set(df)

    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0

    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('area','')}|{r.get('product','')}"
        if key in existing:
            skipped += 1
            continue
        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in PRODUCTION_COLS:
            r.setdefault(c, "")
        new_records.append(r)
        existing.add(key)

    if new_records:
        new_df = pd.DataFrame(new_records)[PRODUCTION_COLS]
        df = pd.concat([df, new_df], ignore_index=True)
        _save(df, PRODUCTION_FILE)

    return len(new_records), skipped


def delete_production(row_id: str):
    df = _load(PRODUCTION_FILE, PRODUCTION_COLS)
    df = df[df["id"] != row_id]
    _save(df, PRODUCTION_FILE)


# ── 生産指標データ（1C日報） ──────────────────────────────────
def get_operative(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    df = _load(OPERATIVE_FILE, OPERATIVE_COLS)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if factory:
        df = df[df["factory"] == factory]
    if date_from:
        df = df[df["date"] >= date_from]
    if date_to:
        df = df[df["date"] <= date_to]
    df["plan"] = pd.to_numeric(df["plan"], errors="coerce")
    df["fact"] = pd.to_numeric(df["fact"], errors="coerce")
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def add_operative(records: list[dict]) -> tuple[int, int]:
    """Returns (added, skipped_duplicates)"""
    df = _load(OPERATIVE_FILE, OPERATIVE_COLS)
    existing = set(
        f"{r.date}|{r.factory}|{r.indicator_ru}|{r.sheet_type}"
        for r in df.itertuples()
    )
    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0

    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('indicator_ru','')}|{r.get('sheet_type','')}"
        if key in existing:
            skipped += 1
            continue
        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in OPERATIVE_COLS:
            r.setdefault(c, "")
        new_records.append(r)
        existing.add(key)

    if new_records:
        new_df = pd.DataFrame(new_records)[OPERATIVE_COLS]
        df = pd.concat([df, new_df], ignore_index=True)
        _save(df, OPERATIVE_FILE)

    return len(new_records), skipped


def delete_operative_bulk(factory: str = "", date_from: str = "", date_to: str = "") -> int:
    df = _load(OPERATIVE_FILE, OPERATIVE_COLS)
    if df.empty:
        return 0
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    mask = pd.Series([True] * len(df), index=df.index)
    if factory:
        mask &= df["factory"] == factory
    if date_from:
        mask &= df["date"] >= date_from
    if date_to:
        mask &= df["date"] <= date_to
    count = int(mask.sum())
    _save(df[~mask].reset_index(drop=True), OPERATIVE_FILE)
    return count
