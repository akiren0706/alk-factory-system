import streamlit as st
import pandas as pd
import json
from pathlib import Path
from utils.master_data import TARGET_FACTORIES, STOPPAGE_FIELDS, PRODUCTION_FIELDS, translate
from utils.importer import read_excel, auto_detect_mapping, apply_mapping
from utils.data_store import (
    add_stoppages, add_production,
    check_duplicates_stoppages, check_duplicates_production,
    add_operative,
)
from utils.hierarchical_parser import is_hierarchical_format, parse_hierarchical_stoppage
from utils.operative_parser import is_operative_format, parse_operative_file
from utils.ui_helpers import page_setup, themed_table

st.set_page_config(page_title="データ取込", page_icon="📥", layout="wide")
page_setup()
st.title("📥 データ取込")
st.caption("ファイルをアップロードするだけで種別を自動判定して取込みます")

# ── 自動インポート ステータス ─────────────────────────────────
_STATUS_FILE = Path(__file__).resolve().parent.parent / "data" / "auto_import_status.json"
_BASE_DIR    = Path(__file__).resolve().parent.parent

st.markdown('<div class="section-tag">🤖 自動インポート</div>', unsafe_allow_html=True)

if _STATUS_FILE.exists():
    try:
        _s = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        _running = _s.get("running", False)
        _icon    = "🟢" if _running else "🔴"
        _status  = "稼働中" if _running else "停止中"
        _border  = "#40916C" if _running else "#C0392B"

        st.markdown(f"""
<div style="background:#FFFFFF;border:1px solid #D4C5A9;border-left:4px solid {_border};
            border-radius:8px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);
            margin-bottom:12px">
  <div style="font-size:0.85rem;font-weight:700;color:#2C2C2C;margin-bottom:10px">
    {_icon} 自動インポート {_status}
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;font-size:0.78rem">
    <div><span style="color:#6B5B45">最終チェック</span><br>
         <b style="color:#2C2C2C">{_s.get('last_check','－') or '－'}</b></div>
    <div><span style="color:#6B5B45">最終取込</span><br>
         <b style="color:#2C2C2C">{_s.get('last_import','－') or '－'}</b></div>
    <div><span style="color:#6B5B45">本日取込件数</span><br>
         <b style="color:#2C2C2C">{_s.get('today_count',0)} 件</b></div>
    <div><span style="color:#6B5B45">最終ファイル</span><br>
         <b style="font-size:0.70rem;color:#2C2C2C">{_s.get('last_file','－') or '－'}</b></div>
  </div>
</div>
""", unsafe_allow_html=True)
        if _s.get("last_error"):
            st.error(f"エラー: {_s['last_error']}")
    except Exception:
        pass
else:
    st.warning("自動インポートが未起動です。下のボタンで起動してください。")

# 操作ボタン
_col1, _col2, _col3 = st.columns(3)
with _col1:
    if st.button("▶ 自動インポートを起動", type="primary", key="start_daemon"):
        import subprocess
        _start = _BASE_DIR / "scripts" / "start.bat"
        if _start.exists():
            subprocess.Popen(str(_start), shell=True, cwd=str(_BASE_DIR))
            st.success("起動しました。数秒後にステータスが更新されます。")
            st.rerun()
        else:
            st.error(f"start.bat が見つかりません: {_start}")
with _col2:
    if st.button("⏹ 停止", type="secondary", key="stop_daemon"):
        import subprocess
        _stop = _BASE_DIR / "scripts" / "stop.bat"
        if _stop.exists():
            subprocess.Popen(str(_stop), shell=True, cwd=str(_BASE_DIR))
            st.success("停止シグナルを送信しました。")
        else:
            subprocess.run(
                ["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq auto_import*"],
                capture_output=True, shell=True,
            )
            st.info("プロセス終了を試みました。")
with _col3:
    if st.button("📅 Windows起動時に自動開始", type="secondary", key="setup_scheduler"):
        import subprocess
        _ps = _BASE_DIR / "scripts" / "setup_autostart.ps1"
        if _ps.exists():
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(_ps)],
                capture_output=True, text=True, encoding="utf-8",
            )
            if result.returncode == 0:
                st.success("✅ Windowsタスクスケジューラーに登録しました。PC起動時に自動開始します。")
            else:
                st.error(f"登録失敗: {(result.stderr or result.stdout or '不明なエラー')[:200]}")
        else:
            st.error("setup_autostart.ps1 が見つかりません。")

st.divider()

# ── ファイルアップロード ───────────────────────────────────────
st.subheader("ファイルを選択（複数可）")
st.caption("停止データ・生産データ・1C日報 すべて自動判定します")
uploaded_files = st.file_uploader(
    "ファイルをドラッグ＆ドロップ（.xlsx / .xls / .csv）",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if not uploaded_files:
    st.info("ファイルをアップロードしてください。種別は自動で判定されます。")
    st.stop()

# ── フォーマット自動判定 ──────────────────────────────────────
def _detect_hierarchical(f) -> bool:
    name = getattr(f, "name", "")
    ext  = name.rsplit(".", 1)[-1].lower() if "." in name else "csv"
    try:
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(f, header=None, dtype=str, nrows=10)
            f.seek(0)
            lines = [" ".join(str(v) for v in row if str(v).lower() not in ("nan", ""))
                     for _, row in df.iterrows()]
        else:
            raw  = f.read(4096)
            f.seek(0)
            text = raw.decode("utf-8-sig", errors="replace")
            lines = text.splitlines()[:10]
    except Exception:
        try: f.seek(0)
        except Exception: pass
        return False
    return is_hierarchical_format(lines)


def _detect_flat_dtype(columns: list[str]) -> str:
    """列名から停止 or 生産を自動判定。スコアの高い方を返す"""
    stop_map = auto_detect_mapping(columns, "stoppage")
    prod_map = auto_detect_mapping(columns, "production")
    stop_score = sum(1 for v in stop_map.values() if v != "_ignore")
    prod_score = sum(1 for v in prod_map.values() if v != "_ignore")
    return "stoppage" if stop_score >= prod_score else "production"


operative_files, hier_files, flat_files = [], [], []
for f in uploaded_files:
    if is_operative_format(f):
        operative_files.append(f)
    elif _detect_hierarchical(f):
        hier_files.append(f)
    else:
        flat_files.append(f)

# 判定結果サマリー
if uploaded_files:
    c1, c2, c3 = st.columns(3)
    c1.metric("1C日報（生産指標）", f"{len(operative_files)} ファイル")
    c2.metric("階層型停止レポート",  f"{len(hier_files)} ファイル")
    c3.metric("フラット表形式",      f"{len(flat_files)} ファイル")
    st.divider()

# ════════════════════════════════════════════════════════════════
#  O: 1C日報フォーマット（Оперативная сводка）
# ════════════════════════════════════════════════════════════════
if operative_files:
    st.info(f"📊  **1C生産日報** {len(operative_files)} ファイルを自動検出しました。")

    all_op_records: list[dict] = []
    op_file_stats: list[dict]  = []
    op_errors: list[str]       = []

    with st.spinner("日報を解析中..."):
        for f in operative_files:
            f.seek(0)
            recs, detected_date, errs = parse_operative_file(f)
            all_op_records.extend(recs)
            op_file_stats.append({
                "ファイル名": f.name,
                "日付（自動検出）": detected_date or "⚠️ 未検出",
                "指標数": len(recs),
            })
            op_errors.extend(errs)

    for msg in op_errors:
        st.warning(f"⚠️  {msg}")

    if all_op_records:
        st.subheader("解析結果")
        themed_table(pd.DataFrame(op_file_stats))

        m1, m2 = st.columns(2)
        m1.metric("抽出指標合計", f"{len(all_op_records)} 件")
        factories_found = sorted(set(r["factory"] for r in all_op_records))
        m2.metric("検出工場", "・".join(factories_found))

        with st.expander("プレビュー（先頭15件）"):
            prev = pd.DataFrame(all_op_records[:15])
            lbl = {"date":"日付","factory":"工場","indicator_ru":"指標(露)","indicator_jp":"指標(日)",
                   "unit":"単位","plan":"計画","fact":"実績","sheet_type":"種別"}
            disp_cols = [c for c in lbl if c in prev.columns]
            themed_table(prev[disp_cols].rename(columns=lbl))

        st.divider()
        if st.button("✅  日報データを取込む", type="primary", use_container_width=True, key="op_import"):
            added, skipped = add_operative(all_op_records)
            st.success(f"🎉  {added} 件の生産指標を取り込みました！（重複スキップ: {skipped} 件）")
            st.balloons()
    else:
        st.error("指標データを抽出できませんでした。")

    st.divider()

# ════════════════════════════════════════════════════════════════
#  A: 階層型フォーマット（停止データ・工場名自動検出）
# ════════════════════════════════════════════════════════════════
if hier_files:
    st.info(f"🔍  **階層型停止レポート** {len(hier_files)} ファイルを自動検出しました。")

    all_records: list[dict] = []
    file_stats: list[dict]  = []
    parse_errors: list[str] = []
    unknown_factory_files: list[str] = []

    with st.spinner("解析中..."):
        for f in hier_files:
            f.seek(0)
            try:
                recs, area_jp, fac = parse_hierarchical_stoppage(f)
                all_records.extend(recs)
                file_stats.append({
                    "ファイル名":       f.name,
                    "工場（自動検出）": fac or "⚠️ 未検出",
                    "エリア（自動検出）": area_jp or "（未検出）",
                    "抽出件数":         len(recs),
                })
                if not fac:
                    unknown_factory_files.append(f.name)
            except Exception as e:
                parse_errors.append(f"{f.name}: {e}")

    for msg in parse_errors:
        st.error(f"❌  {msg}")

    if not all_records:
        st.error("データを抽出できませんでした。ファイル形式を確認してください。")
    else:
        st.subheader("解析結果")
        themed_table(pd.DataFrame(file_stats))

        if unknown_factory_files:
            st.warning(f"⚠️  {len(unknown_factory_files)} ファイルで工場名を自動検出できませんでした。手動で選択してください。")
            manual_factory = st.selectbox("工場（手動選択）", TARGET_FACTORIES, key="manual_fac")
            for r in all_records:
                if not r.get("factory"):
                    r["factory"] = manual_factory

        new_records, dup_count = check_duplicates_stoppages(all_records)

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("抽出合計",        f"{len(all_records)} 件")
        col_b.metric("新規（取込対象）", f"{len(new_records)} 件")
        col_c.metric("重複スキップ",     f"{dup_count} 件")

        if new_records:
            with st.expander("データプレビュー（新規先頭10件）"):
                preview_df = pd.DataFrame(new_records[:10])
                display_cols = [c for c in ["date", "factory", "area", "duration_minutes", "reason", "notes"]
                                if c in preview_df.columns]
                label_map = {"date": "日付", "factory": "工場", "area": "エリア/設備",
                             "duration_minutes": "停止時間(分)", "reason": "停止理由", "notes": "登録番号"}
                themed_table(preview_df[display_cols].rename(columns=label_map))

        st.divider()
        if new_records:
            if st.button("✅  停止データを取込む", type="primary", use_container_width=True, key="hier_import"):
                added, skipped = add_stoppages(new_records)
                st.success(f"🎉  {added} 件の停止データを取り込みました！（重複スキップ: {skipped} 件）")
                st.balloons()
        else:
            st.info("すべてのレコードは既に取込済みです。")

    st.divider()

# ════════════════════════════════════════════════════════════════
#  B: フラット表形式（停止 or 生産を列名から自動判定）
# ════════════════════════════════════════════════════════════════
if flat_files:
    for f in flat_files:
        f.seek(0)
        df_raw, err = read_excel(f)
        if err:
            st.error(f"{f.name}: 読込エラー — {err}")
            continue
        if df_raw.empty:
            st.warning(f"{f.name}: データなし")
            continue

        # データ種別を自動判定
        dtype_key = _detect_flat_dtype(list(df_raw.columns))
        dtype_label = "停止データ" if dtype_key == "stoppage" else "生産データ"
        fields = STOPPAGE_FIELDS if dtype_key == "stoppage" else PRODUCTION_FIELDS
        field_options = {key: label for key, label, _ in fields}
        field_options["_ignore"] = "--- 無視 ---"

        st.info(f"📄  **{f.name}** → **{dtype_label}** として自動判定しました")

        # 工場選択（フラット形式のみ必要）
        factory = st.selectbox(f"工場（{f.name}）", TARGET_FACTORIES, key=f"fac_{f.name}")

        # 列マッピング（自動検出済み・変更可能）
        auto_map = auto_detect_mapping(list(df_raw.columns), dtype_key)
        with st.expander(f"列マッピングを確認・修正（{f.name}）"):
            mapping: dict[str, str] = {}
            cols_ui = st.columns(3)
            for i, col_name in enumerate(df_raw.columns):
                auto_val   = auto_map.get(col_name, "_ignore")
                translated = translate(col_name)
                label = f"{col_name}" + (f"  →  {translated}" if translated != col_name else "")
                idx   = list(field_options.keys()).index(auto_val) if auto_val in field_options else len(field_options) - 1
                selected = cols_ui[i % 3].selectbox(
                    label, options=list(field_options.keys()),
                    format_func=lambda k: field_options[k],
                    index=idx, key=f"map_{f.name}_{i}",
                )
                mapping[col_name] = selected

        # プレビュー
        active_cols = {col: field for col, field in mapping.items() if field != "_ignore"}
        if active_cols:
            with st.expander(f"データプレビュー（先頭5行）— {f.name}"):
                preview = df_raw.head(5)[list(active_cols.keys())].copy()
                preview.columns = [field_options.get(v, v) for v in active_cols.values()]
                themed_table(preview)

        # 取込ボタン
        if st.button(f"✅  {f.name} を取込む", type="primary",
                     use_container_width=True, key=f"flat_import_{f.name}"):
            records = apply_mapping(df_raw, mapping, factory, dtype_key)
            if not records:
                st.error("有効なデータが見つかりませんでした。「日付」列のマッピングを確認してください。")
            else:
                if dtype_key == "stoppage":
                    added, skipped = add_stoppages(records)
                    st.success(f"🎉  {added} 件の停止データを取り込みました！（重複スキップ: {skipped} 件）")
                else:
                    added, skipped = add_production(records)
                    st.success(f"🎉  {added} 件の生産データを取り込みました！（重複スキップ: {skipped} 件）")
                st.balloons()

        st.divider()
