import streamlit as st
from pathlib import Path

BASE = Path(__file__).parent

NAV = {
    "メイン": [
        st.Page(str(BASE / "pages" / "0_ダッシュボード.py"),  title="ダッシュボード", icon="🏭"),
        st.Page(str(BASE / "pages" / "11_今日今週.py"),        title="メイン",         icon="🏠"),
        st.Page(str(BASE / "pages" / "14_週報.py"),            title="週次レポート",   icon="📋"),
        st.Page(str(BASE / "pages" / "1_データ取込.py"),       title="データ取込",     icon="📥"),
    ],
    "データ管理": [
        st.Page(str(BASE / "pages" / "5_生産指標.py"),         title="生産指標",       icon="📈"),
        st.Page(str(BASE / "pages" / "3_生産データ.py"),       title="生産データ",     icon="📦"),
        st.Page(str(BASE / "pages" / "2_停止データ.py"),       title="停止データ",     icon="⏸️"),
        st.Page(str(BASE / "pages" / "4_レポート.py"),         title="レポート",       icon="📋"),
    ],
    "工場別": [
        st.Page(str(BASE / "pages" / "6_単板工場.py"),         title="単板工場",       icon="🪵"),
        st.Page(str(BASE / "pages" / "7_製材工場.py"),         title="製材工場",       icon="🪚"),
        st.Page(str(BASE / "pages" / "8_ペレット工場.py"),     title="ペレット工場",   icon="🌿"),
        st.Page(str(BASE / "pages" / "9_合板工場.py"),         title="合板工場",       icon="🏗️"),
        st.Page(str(BASE / "pages" / "10_簡易製材工場.py"),    title="簡易製材工場",   icon="🔨"),
        st.Page(str(BASE / "pages" / "12_土場.py"),            title="土場",           icon="🪨"),
        st.Page(str(BASE / "pages" / "13_製品在庫.py"),        title="製品在庫",       icon="🏪"),
    ],
}

pg = st.navigation(NAV)

st.markdown("""
<style>
[data-testid="stSidebarNavViewButton"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

pg.run()
