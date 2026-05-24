import streamlit as st
import json
from pathlib import Path
import pandas as pd
from utils.ui_helpers import page_setup

st.set_page_config(page_title="設定", page_icon="⚙️", layout="wide")
page_setup()
st.title("⚙️ 設定")

SETTINGS_FILE = Path(__file__).parent.parent / "settings" / "nav_order.json"
ALL_SECTIONS  = ["メイン", "データ管理", "工場別", "システム"]

BLOCKED_PAGES = {"製パン工場", "パン工場"}

ALL_PAGES = [
    "ダッシュボード", "メイン", "アラート", "週報", "データ取込",
    "停止データ", "生産データ", "生産指標", "レポート",
    "単板工場", "製材工場", "ペレット工場", "合板工場", "簡易製材工場",
    "土場", "製品在庫",
    "設定",
]

DEFAULT_ORDER = {
    "メイン":     ["ダッシュボード", "メイン", "アラート", "週報", "データ取込"],
    "データ管理": ["停止データ", "生産データ", "生産指標", "レポート"],
    "工場別":     ["単板工場", "製材工場", "ペレット工場", "合板工場", "簡易製材工場", "土場", "製品在庫"],
    "システム":   ["設定"],
}


def load_order():
    if SETTINGS_FILE.exists():
        try:
            order = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {
                sec: [p for p in pages if p not in BLOCKED_PAGES]
                for sec, pages in order.items()
            }
        except Exception:
            pass
    return DEFAULT_ORDER


def save_order(order: dict):
    clean = {
        sec: [p for p in pages if p not in BLOCKED_PAGES]
        for sec, pages in order.items()
        if pages
    }
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


current_order = load_order()

st.subheader("📋 ページ順序・セクション設定")
st.caption("セクションと順序を編集して「保存」を押すとサイドバーが変わります。（反映はページ再読み込み後）")

rows = []
for section, pages in current_order.items():
    for i, page in enumerate(pages):
        if page in BLOCKED_PAGES:
            continue
        rows.append({"セクション": section, "ページ名": page, "順序": i + 1})

registered = [r["ページ名"] for r in rows]
for p in ALL_PAGES:
    if p not in registered and p not in BLOCKED_PAGES:
        rows.append({"セクション": "システム", "ページ名": p, "順序": 99})

df_order = pd.DataFrame(rows)

edited = st.data_editor(
    df_order,
    column_config={
        "セクション": st.column_config.SelectboxColumn(
            "セクション", options=ALL_SECTIONS, required=True,
        ),
        "ページ名": st.column_config.TextColumn("ページ名", disabled=True),
        "順序":     st.column_config.NumberColumn("順序", min_value=1, max_value=99, step=1),
    },
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
)

st.caption("💡 「セクション」列でグループを変更、「順序」列で並び順を変更できます。")

if st.button("💾 保存する", type="primary"):
    new_order: dict[str, list[str]] = {s: [] for s in ALL_SECTIONS}
    for _, row in edited.sort_values(["セクション", "順序"]).iterrows():
        sec  = row["セクション"]
        page = row["ページ名"]
        if page in BLOCKED_PAGES:
            continue
        if sec in new_order:
            new_order[sec].append(page)
    new_order = {k: v for k, v in new_order.items() if v}
    save_order(new_order)
    st.success("✅ 保存しました。ブラウザをリロード（F5）すると反映されます。")
    st.json(new_order)

st.divider()
if st.button("🔄 デフォルトに戻す", type="secondary"):
    save_order(DEFAULT_ORDER)
    st.success("デフォルト設定に戻しました。ブラウザをリロードしてください。")
