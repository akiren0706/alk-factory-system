import pandas as pd
import uuid
from datetime import datetime
import streamlit as st
from supabase import create_client, Client

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


def _is_blank(v) -> bool:
    return str(v).strip().lower() in ("", "nan", "none")


@st.cache_resource
def _sb() -> Client:
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])


def _to_df(data: list, cols: list) -> pd.DataFrame:
    if not data:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(data)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].reset_index(drop=True)


# ── 停止データ ──────────────────────────────────────────────
def get_stoppages(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    q = _sb().table("stoppages").select("*")
    if factory:   q = q.eq("factory", factory)
    if date_from: q = q.gte("date", date_from)
    if date_to:   q = q.lte("date", date_to)
    res = q.order("date", desc=True).execute()
    df = _to_df(res.data, STOPPAGE_COLS)
    if not df.empty:
        df["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")
    return df


def _stop_key_sets_db():
    res = _sb().table("stoppages").select("factory,notes,date,area,duration_minutes").execute()
    rows = res.data or []
    notes_set = set(
        f"{r['factory']}|{r['notes']}" for r in rows if not _is_blank(r.get("notes", ""))
    )
    composite_set = set(
        f"{r['date']}|{r['factory']}|{r['area']}|{r['duration_minutes']}"
        for r in rows if _is_blank(r.get("notes", ""))
    )
    return notes_set, composite_set


def check_duplicates_stoppages(records: list[dict]) -> tuple[list[dict], int]:
    existing_notes, existing_composite = _stop_key_sets_db()
    new_records, skipped = [], 0
    for r in records:
        notes = str(r.get("notes", "")).strip()
        fact  = str(r.get("factory", ""))
        notes_key = f"{fact}|{notes}" if notes else ""
        if notes_key and notes_key in existing_notes:
            skipped += 1; continue
        if not notes:
            key = f"{r.get('date','')}|{fact}|{r.get('area','')}|{r.get('duration_minutes','')}"
            if key in existing_composite:
                skipped += 1; continue
        new_records.append(r)
        if notes_key: existing_notes.add(notes_key)
        else: existing_composite.add(f"{r.get('date','')}|{fact}|{r.get('area','')}|{r.get('duration_minutes','')}")
    return new_records, skipped


def add_stoppages(records: list[dict]) -> tuple[int, int]:
    existing_notes, existing_composite = _stop_key_sets_db()
    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0
    for r in records:
        notes = str(r.get("notes", "")).strip()
        fact  = str(r.get("factory", ""))
        notes_key = f"{fact}|{notes}" if notes else ""
        if notes_key and notes_key in existing_notes:
            skipped += 1; continue
        if not notes:
            key = f"{r.get('date','')}|{fact}|{r.get('area','')}|{r.get('duration_minutes','')}"
            if key in existing_composite:
                skipped += 1; continue
        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in STOPPAGE_COLS: r.setdefault(c, "")
        new_records.append(r)
        if notes_key: existing_notes.add(notes_key)
        else: existing_composite.add(f"{r.get('date','')}|{fact}|{r.get('area','')}|{r.get('duration_minutes','')}")
    if new_records:
        rows = [pd.Series(r).where(pd.notna(pd.Series(r)), other=None).to_dict() for r in new_records]
        _sb().table("stoppages").insert(rows).execute()
    return len(new_records), skipped


def delete_stoppage(row_id: str):
    _sb().table("stoppages").delete().eq("id", row_id).execute()


def delete_stoppages_bulk(factory: str = "", date_from: str = "", date_to: str = "") -> int:
    preview = preview_delete_stoppages(factory, date_from, date_to)
    count = len(preview)
    if count > 0:
        q = _sb().table("stoppages").delete()
        if factory:   q = q.eq("factory", factory)
        if date_from: q = q.gte("date", date_from)
        if date_to:   q = q.lte("date", date_to)
        q.execute()
    return count


def preview_delete_stoppages(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    q = _sb().table("stoppages").select("*")
    if factory:   q = q.eq("factory", factory)
    if date_from: q = q.gte("date", date_from)
    if date_to:   q = q.lte("date", date_to)
    res = q.execute()
    df = _to_df(res.data, STOPPAGE_COLS)
    if not df.empty:
        df["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")
    return df


# ── 生産データ ──────────────────────────────────────────────
def get_production(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    q = _sb().table("production").select("*")
    if factory:   q = q.eq("factory", factory)
    if date_from: q = q.gte("date", date_from)
    if date_to:   q = q.lte("date", date_to)
    res = q.order("date", desc=True).execute()
    df = _to_df(res.data, PRODUCTION_COLS)
    if not df.empty:
        df["quantity"]        = pd.to_numeric(df["quantity"], errors="coerce")
        df["operating_hours"] = pd.to_numeric(df["operating_hours"], errors="coerce")
    return df


def check_duplicates_production(records: list[dict]) -> tuple[list[dict], int]:
    res = _sb().table("production").select("date,factory,area,product").execute()
    existing = set(f"{r['date']}|{r['factory']}|{r['area']}|{r['product']}" for r in (res.data or []))
    new_records, skipped = [], 0
    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('area','')}|{r.get('product','')}"
        if key in existing: skipped += 1; continue
        new_records.append(r); existing.add(key)
    return new_records, skipped


def add_production(records: list[dict]) -> tuple[int, int]:
    res = _sb().table("production").select("date,factory,area,product").execute()
    existing = set(f"{r['date']}|{r['factory']}|{r['area']}|{r['product']}" for r in (res.data or []))
    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0
    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('area','')}|{r.get('product','')}"
        if key in existing: skipped += 1; continue
        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in PRODUCTION_COLS: r.setdefault(c, "")
        new_records.append(r); existing.add(key)
    if new_records:
        _sb().table("production").insert(new_records).execute()
    return len(new_records), skipped


def delete_production(row_id: str):
    _sb().table("production").delete().eq("id", row_id).execute()


# ── 生産指標データ（1C日報） ──────────────────────────────────
def get_operative(factory: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    q = _sb().table("operative_data").select("*")
    if factory:   q = q.eq("factory", factory)
    if date_from: q = q.gte("date", date_from)
    if date_to:   q = q.lte("date", date_to)
    res = q.order("date", desc=True).execute()
    df = _to_df(res.data, OPERATIVE_COLS)
    if not df.empty:
        df["plan"] = pd.to_numeric(df["plan"], errors="coerce")
        df["fact"] = pd.to_numeric(df["fact"], errors="coerce")
    return df


def add_operative(records: list[dict]) -> tuple[int, int]:
    res = _sb().table("operative_data").select("date,factory,indicator_ru,sheet_type").execute()
    existing = set(
        f"{r['date']}|{r['factory']}|{r['indicator_ru']}|{r['sheet_type']}"
        for r in (res.data or [])
    )
    now = datetime.now().isoformat(timespec="seconds")
    new_records, skipped = [], 0
    for r in records:
        key = f"{r.get('date','')}|{r.get('factory','')}|{r.get('indicator_ru','')}|{r.get('sheet_type','')}"
        if key in existing: skipped += 1; continue
        r["id"] = str(uuid.uuid4())[:8]
        r["imported_at"] = now
        for c in OPERATIVE_COLS: r.setdefault(c, "")
        new_records.append(r); existing.add(key)
    if new_records:
        chunk = 500
        for i in range(0, len(new_records), chunk):
            _sb().table("operative_data").insert(new_records[i:i+chunk]).execute()
    return len(new_records), skipped


def delete_operative_bulk(factory: str = "", date_from: str = "", date_to: str = "") -> int:
    q_count = _sb().table("operative_data").select("id", count="exact")
    if factory:   q_count = q_count.eq("factory", factory)
    if date_from: q_count = q_count.gte("date", date_from)
    if date_to:   q_count = q_count.lte("date", date_to)
    res = q_count.execute()
    count = res.count or 0
    if count > 0:
        q = _sb().table("operative_data").delete()
        if factory:   q = q.eq("factory", factory)
        if date_from: q = q.gte("date", date_from)
        if date_to:   q = q.lte("date", date_to)
        q.execute()
    return count
