import streamlit as st
import json
from pathlib import Path
from streamlit_sortables import sort_items

BASE = Path(__file__).parent

ALL_PAGES = {
    "ダッシュボード": (str(BASE / "pages" / "0_ダッシュボード.py"),  "🏭"),
    "メイン":         (str(BASE / "pages" / "11_今日今週.py"),       "🏠"),
    "アラート":       (str(BASE / "pages" / "16_アラート.py"),       "🚨"),
    "週報":           (str(BASE / "pages" / "14_週報.py"),           "📋"),
    "データ取込":     (str(BASE / "pages" / "1_データ取込.py"),      "📥"),
    "停止データ":     (str(BASE / "pages" / "2_停止データ.py"),      "⏸️"),
    "生産データ":     (str(BASE / "pages" / "3_生産データ.py"),      "📦"),
    "レポート":       (str(BASE / "pages" / "4_レポート.py"),        "📋"),
    "生産指標":       (str(BASE / "pages" / "5_生産指標.py"),        "📈"),
    "単板工場":       (str(BASE / "pages" / "6_単板工場.py"),        "🪵"),
    "製材工場":       (str(BASE / "pages" / "7_製材工場.py"),        "🪚"),
    "ペレット工場":   (str(BASE / "pages" / "8_ペレット工場.py"),    "🌿"),
    "合板工場":       (str(BASE / "pages" / "9_合板工場.py"),        "🏗️"),
    "簡易製材工場":   (str(BASE / "pages" / "10_簡易製材工場.py"),   "🔨"),
    "土場":           (str(BASE / "pages" / "12_土場.py"),           "🪨"),
    "製品在庫":       (str(BASE / "pages" / "13_製品在庫.py"),       "🏪"),
}

ALLOWED_PAGES = set(ALL_PAGES.keys())

DEFAULT_ORDER = {
    "メイン":     ["ダッシュボード", "メイン", "アラート", "週報", "データ取込"],
    "データ管理": ["生産指標", "生産データ", "停止データ", "レポート"],
    "工場別":     ["単板工場", "製材工場", "ペレット工場", "合板工場", "簡易製材工場", "土場", "製品在庫"],
}

SETTINGS_FILE = BASE / "settings" / "nav_order.json"


def load_order() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            # 設定ページが残っている場合は除外
            data.pop("システム", None)
            for section in data:
                data[section] = [n for n in data[section] if n in ALLOWED_PAGES]
            return {k: v for k, v in data.items() if v}
        except Exception:
            pass
    return DEFAULT_ORDER


def save_order(order: dict) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_nav(order: dict) -> dict:
    nav = {}
    for section, names in order.items():
        pages = []
        for name in names:
            if name not in ALL_PAGES:
                continue
            path, icon = ALL_PAGES[name]
            if Path(path).exists():
                pages.append(st.Page(path, title=name, icon=icon))
        if pages:
            nav[section] = pages
    return nav


order = load_order()
nav = build_nav(order)
pg = st.navigation(nav)

# ─── サイドバー：ドラッグ&ドロップで順番変更 ───────────────────
with st.sidebar:
    with st.expander("🔀 順番"):
        tabs = st.tabs(list(order.keys()))
        for tab, (section, names) in zip(tabs, order.items()):
            with tab:
                result = sort_items(names, multi_containers=False, key=f"ns_{section}")
                if result != names:
                    new_order = dict(order)
                    new_order[section] = result
                    save_order(new_order)
                    st.rerun()

pg.run()
