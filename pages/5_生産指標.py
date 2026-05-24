import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils.data_store import get_operative, delete_operative_bulk
from utils.master_data import TARGET_FACTORIES, fix_indicator_name
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme, jp_date_input,
    COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_GOOD, PALETTE_MAIN,
    gauge_chart,
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="生産指標", page_icon="📊", layout="wide")
page_setup()
st.title("📊 生産指標（1C日報）")

ALL_FACTORIES = ["合板工場", "製材工場", "単板工場", "ペレット工場", "土場", "製品在庫", "簡易製材工場"]

# タブ表示順（データにある工場のみ、この順で並べる）
TAB_ORDER = ["合板工場", "製材工場", "単板工場", "ペレット工場", "土場", "製品在庫", "簡易製材工場"]

# ── フィルター ───────────────────────────────────────────────
with st.expander("🔍 フィルター", expanded=True):
    c1, c2, c3 = st.columns(3)
    sel_factory = c1.selectbox("工場", ["全工場"] + ALL_FACTORIES, key="of")
    with c2:
        date_from = jp_date_input("開始日", date.today().replace(day=1), "odf")
    with c3:
        date_to = jp_date_input("終了日", date.today(), "odt")

factory_filter = "" if sel_factory == "全工場" else sel_factory
df = get_operative(factory_filter, str(date_from), str(date_to))

col_dl, col_info = st.columns([1, 4])
col_info.caption(f"検索結果: {len(df)} 件")
if not df.empty:
    col_dl.download_button(
        "📥 CSV出力",
        df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="operative_data.csv", mime="text/csv",
    )

if df.empty:
    st.info("データがありません。「データ取込」から1C生産日報（Оперативная сводка）をインポートしてください。")
    st.stop()

st.divider()

# ── 概要指標 ─────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("総指標件数", f"{len(df)} 件")
m2.metric("対象日数",   f"{df['date'].nunique()} 日")
m3.metric("対象工場",   f"{df['factory'].nunique()} 工場")

st.divider()

# ── 重要指標タブ ─────────────────────────────────────────────
st.markdown('<div class="section-tag">主要生産指標（計画／実績）</div>', unsafe_allow_html=True)

# 対象工場の重要指標を抽出
def get_key_rows(df: pd.DataFrame, factory: str) -> pd.DataFrame:
    prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
    if not prefixes:
        return df[df["factory"] == factory].head(20)
    masks = [df["indicator_ru"].str.startswith(p, na=False) for p in prefixes]
    mask = masks[0]
    for m in masks[1:]:
        mask = mask | m
    return df[(df["factory"] == factory) & mask]

factories_in_data = set(df["factory"].unique().tolist())

if sel_factory != "全工場":
    tab_factories = [sel_factory] if sel_factory in factories_in_data else []
else:
    # TAB_ORDER の順で並べ、残りを後ろに追加
    tab_factories = [f for f in TAB_ORDER if f in factories_in_data]
    tab_factories += [f for f in factories_in_data if f not in TAB_ORDER]

if tab_factories:
    tabs = st.tabs(tab_factories)
    for tab, fac in zip(tabs, tab_factories):
        with tab:
            fac_df = get_key_rows(df, fac)
            if fac_df.empty:
                st.info("データがありません。")
                continue

            # 日付別・指標別の集計（複数日ある場合）
            dates = sorted(fac_df["date"].unique())
            if len(dates) == 1:
                # 1日分: 横棒グラフで計画 vs 実績
                day_df = fac_df[fac_df["date"] == dates[0]].dropna(subset=["fact"])
                day_df = day_df[day_df["fact"] > 0].head(12)
                if not day_df.empty:
                    # 指標表示名: indicator_jp があれば日本語、なければロシア語（先頭30文字）
                    day_df = day_df.copy()
                    day_df["表示名"] = day_df.apply(
                        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                    )
                    fig = go.Figure()
                    fig.add_bar(y=day_df["表示名"], x=day_df["plan"],  name="計画", orientation="h",
                                marker_color="#90CAF9", opacity=0.8)
                    fig.add_bar(y=day_df["表示名"], x=day_df["fact"],  name="実績", orientation="h",
                                marker_color="#1E88E5")
                    fig.update_layout(
                        barmode="overlay",
                        xaxis_title="数量",
                        legend=dict(orientation="h", y=1.05),
                    )
                    apply_chart_theme(fig, height=max(300, len(day_df) * 28 + 80),
                                      margin=dict(t=10, b=10, l=10, r=10))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                # 複数日: 時系列で実績推移
                top_indicators = (
                    fac_df.dropna(subset=["fact"])
                    .groupby("indicator_ru")["fact"].sum()
                    .sort_values(ascending=False).head(5).index.tolist()
                )
                trend_df = fac_df[fac_df["indicator_ru"].isin(top_indicators)].copy()
                trend_df["表示名"] = trend_df.apply(
                    lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                )
                if not trend_df.empty:
                    fig = px.line(
                        trend_df.sort_values("date"),
                        x="date", y="fact", color="表示名", markers=True,
                        labels={"date": "日付", "fact": "実績", "表示名": "指標"},
                    )
                    apply_chart_theme(fig, height=320, margin=dict(t=10, b=10, l=10, r=10))
                    st.plotly_chart(fig, use_container_width=True)

            # 達成率ゲージ（主要指標の平均達成率）
            tbl = fac_df.dropna(subset=["fact"]).copy()
            tbl["達成率(%)"] = (tbl["fact"] / tbl["plan"] * 100).round(1).where(tbl["plan"] > 0)
            tbl["表示名"] = tbl.apply(
                lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
            )
            ach_tbl = tbl[tbl["達成率(%)"].notna() & (tbl["達成率(%)"] > 0)]
            if not ach_tbl.empty:
                avg_ach = ach_tbl["達成率(%)"].mean()
                st.markdown('<div class="section-tag">平均達成率</div>', unsafe_allow_html=True)
                gc1, gc2, gc3 = st.columns([1, 2, 1])
                with gc2:
                    st.plotly_chart(
                        gauge_chart(avg_ach, title=f"{fac}  平均達成率", max_val=100, height=220),
                        use_container_width=True,
                    )

            # 達成率テーブル
            disp = tbl[["date", "表示名", "unit", "plan", "fact", "達成率(%)"]].rename(columns={
                "date": "日付", "表示名": "指標", "unit": "単位",
                "plan": "計画", "fact": "実績",
            })
            themed_table(disp, height=300)

st.divider()

# ── 全指標テーブル ────────────────────────────────────────────
with st.expander("📋 全指標一覧"):
    keyword = st.text_input("指標名で検索（日本語/ロシア語）", key="ind_kw")
    show = df.copy()
    if keyword:
        mask = (
            show["indicator_ru"].fillna("").str.contains(keyword, case=False) |
            show["indicator_jp"].fillna("").str.contains(keyword, case=False)
        )
        show = show[mask]
    show["達成率(%)"] = (show["fact"] / show["plan"] * 100).round(1).where(show["plan"] > 0)
    show["指標"] = show.apply(
        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
    )
    col_labels = {
        "date": "日付", "factory": "工場", "指標": "指標",
        "unit": "単位", "plan": "計画", "fact": "実績", "達成率(%)": "達成率(%)", "sheet_type": "種別",
    }
    disp_cols = [c for c in ["date", "factory", "指標", "unit", "plan", "fact", "達成率(%)", "sheet_type"] if c in show.columns or c == "指標"]
    themed_table(show[disp_cols].rename(columns=col_labels), height=450)

# ── 削除 ────────────────────────────────────────────────────
with st.expander("🗑️ データを削除"):
    dc1, dc2, dc3 = st.columns(3)
    del_fac = dc1.selectbox("工場", [""] + ALL_FACTORIES,
                            format_func=lambda v: "すべての工場" if v == "" else v, key="od_fac")
    with dc2:
        del_from = jp_date_input("開始日", date.today().replace(day=1), "od_from")
    with dc3:
        del_to = jp_date_input("終了日", date.today(), "od_to")
    if st.button(f"⚠️  条件に一致するデータを削除（取り消し不可）", type="primary", key="od_del"):
        deleted = delete_operative_bulk(del_fac, str(del_from), str(del_to))
        st.success(f"✅  {deleted} 件を削除しました。")
        st.rerun()
