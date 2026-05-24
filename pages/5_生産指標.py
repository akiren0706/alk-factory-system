import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import numpy as np
from utils.data_store import get_operative, delete_operative_bulk
from utils.master_data import TARGET_FACTORIES, fix_indicator_name
from utils.ui_helpers import (
    themed_table, page_setup, apply_chart_theme, jp_date_input,
    gauge_chart, get_palette,
    COLOR_OK, COLOR_WARN, COLOR_ERR, PRIMARY, TEXT, TEXT_SUB,
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="生産指標", page_icon="📊", layout="wide")
page_setup()
st.title("📊 生産指標（1C日報）")

ALL_FACTORIES = ["合板工場", "製材工場", "単板工場", "ペレット工場", "土場", "製品在庫", "簡易製材工場"]
TAB_ORDER     = ["合板工場", "製材工場", "単板工場", "ペレット工場", "土場", "製品在庫", "簡易製材工場"]

# ── フィルター ────────────────────────────────────────────────
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

# ── 数値変換 ─────────────────────────────────────────────────
df["fact_n"] = pd.to_numeric(df["fact"], errors="coerce")
df["plan_n"] = pd.to_numeric(df["plan"], errors="coerce")
df["ach"]    = (df["fact_n"] / df["plan_n"] * 100).where(df["plan_n"] > 0)

# ── グローバル KPI ────────────────────────────────────────────
avg_ach_all = df["ach"].dropna().mean()
n_over      = (df["ach"] >= 100).sum()
n_under     = (df["ach"] < 80).sum()

g1, g2, g3, g4, g5 = st.columns(5)
g1.metric("総指標件数",       f"{len(df):,} 件")
g2.metric("対象日数",         f"{df['date'].nunique()} 日")
g3.metric("対象工場数",       f"{df['factory'].nunique()} 工場")
g4.metric("全体平均達成率",   f"{avg_ach_all:.1f} %" if pd.notna(avg_ach_all) else "－")
g5.metric("達成 / 未達指標",  f"{n_over} / {n_under} 件")

st.divider()
st.markdown('<div class="section-tag">工場別 生産指標分析</div>', unsafe_allow_html=True)


def get_key_rows(src: pd.DataFrame, factory: str) -> pd.DataFrame:
    prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
    if not prefixes:
        return src[src["factory"] == factory].head(20)
    mask = src["indicator_ru"].str.startswith(prefixes[0], na=False)
    for p in prefixes[1:]:
        mask |= src["indicator_ru"].str.startswith(p, na=False)
    return src[(src["factory"] == factory) & mask]


factories_in_data = set(df["factory"].unique())
if sel_factory != "全工場":
    tab_factories = [sel_factory] if sel_factory in factories_in_data else []
else:
    tab_factories = [f for f in TAB_ORDER if f in factories_in_data]
    tab_factories += [f for f in factories_in_data if f not in tab_factories]

if tab_factories:
    tabs = st.tabs(tab_factories)
    for tab, fac in zip(tabs, tab_factories):
        with tab:
            fac_df = get_key_rows(df, fac).copy()
            if fac_df.empty:
                st.info("データがありません。")
                continue

            fac_df["表示名"] = fac_df.apply(
                lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
            )
            dates       = sorted(fac_df["date"].unique())
            n_days      = len(dates)
            total_fact  = fac_df["fact_n"].sum()
            total_plan  = fac_df["plan_n"].sum()
            avg_ach_fac = fac_df["ach"].dropna().mean()
            n_below_fac = int((fac_df["ach"] < 80).sum())

            # ── KPI row ───────────────────────────────────────
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("平均達成率",
                      f"{avg_ach_fac:.1f} %" if pd.notna(avg_ach_fac) else "－",
                      delta_color="normal" if (avg_ach_fac or 0) >= 100 else "inverse")
            k2.metric("計画合計",       f"{total_plan:,.0f}" if pd.notna(total_plan) else "－")
            k3.metric("実績合計",       f"{total_fact:,.0f}" if pd.notna(total_fact) else "－")
            k4.metric("データ日数",     f"{n_days} 日",
                      delta=f"未達指標 {n_below_fac} 件" if n_below_fac else None,
                      delta_color="inverse" if n_below_fac else "normal")

            st.divider()

            # ── 1日分: 計画 vs 実績 バー + ゲージ ────────────────
            if n_days == 1:
                day_df = fac_df[fac_df["date"] == dates[0]].dropna(subset=["fact_n"])
                day_df = day_df[day_df["fact_n"] > 0].head(12)

                ch_l, ch_r = st.columns([2, 1])
                with ch_l:
                    st.markdown('<div class="section-tag">計画 vs 実績</div>', unsafe_allow_html=True)
                    if not day_df.empty:
                        fig = go.Figure()
                        fig.add_bar(y=day_df["表示名"], x=day_df["plan_n"], name="計画",
                                    orientation="h", marker_color="#90CAF9", opacity=0.85)
                        fig.add_bar(y=day_df["表示名"], x=day_df["fact_n"], name="実績",
                                    orientation="h", marker_color="#1E88E5")
                        fig.update_layout(barmode="overlay", xaxis_title="数量",
                                          legend=dict(orientation="h", y=1.08))
                        apply_chart_theme(fig, height=max(300, len(day_df) * 32 + 80),
                                          margin=dict(t=10, b=10, l=10, r=10))
                        st.plotly_chart(fig, use_container_width=True)

                with ch_r:
                    gauge_max = max(120, int(round(max(avg_ach_fac or 0, 100) * 1.3 / 20) * 20))
                    if pd.notna(avg_ach_fac):
                        st.plotly_chart(
                            gauge_chart(avg_ach_fac, title="平均達成率",
                                        max_val=gauge_max, height=220),
                            use_container_width=True,
                        )
                    if not day_df.empty:
                        ach_map = day_df.set_index("表示名")["ach"]
                        stat_one = pd.DataFrame({
                            "指標":   day_df["表示名"].values,
                            "実績":   day_df["fact_n"].apply(lambda v: f"{v:,.0f}").values,
                            "達成率": day_df["表示名"].map(ach_map).apply(
                                lambda v: f"{v:.1f}%" if pd.notna(v) else "－").values,
                        })
                        themed_table(stat_one, height=220)

            # ── 複数日: トレンド + 散布図 + ヒートマップ ─────────
            else:
                top_inds = (
                    fac_df.dropna(subset=["fact_n"])
                    .groupby("indicator_ru")["fact_n"].sum()
                    .sort_values(ascending=False).head(5).index.tolist()
                )
                trend_df = fac_df[fac_df["indicator_ru"].isin(top_inds)].copy()
                trend_df = trend_df.sort_values("date")

                ch_l, ch_r = st.columns([3, 2])
                with ch_l:
                    st.markdown('<div class="section-tag">日別実績トレンド（棒グラフ + 3日移動平均）</div>',
                                unsafe_allow_html=True)
                    if not trend_df.empty:
                        palette = get_palette()
                        fig_tr = go.Figure()
                        for i, ind in enumerate(trend_df["表示名"].unique()):
                            sub = trend_df[trend_df["表示名"] == ind].copy()
                            sub["date_str"] = pd.to_datetime(sub["date"]).dt.strftime("%m/%d")
                            col = palette[i % len(palette)]
                            fig_tr.add_bar(x=sub["date_str"], y=sub["fact_n"],
                                           name=ind, marker_color=col, opacity=0.65)
                            if len(sub) >= 3:
                                sub["ma"] = sub["fact_n"].rolling(3, min_periods=1).mean()
                                fig_tr.add_scatter(
                                    x=sub["date_str"], y=sub["ma"],
                                    mode="lines+markers", name=f"MA: {ind}",
                                    line=dict(color=col, width=2, dash="dot"),
                                    marker=dict(size=5), showlegend=False,
                                )
                        fig_tr.update_layout(
                            barmode="group", xaxis_title="日付", yaxis_title="実績",
                            legend=dict(orientation="h", y=-0.3, font=dict(size=8)),
                        )
                        apply_chart_theme(fig_tr, height=340,
                                          margin=dict(t=10, b=100, l=10, r=10))
                        st.plotly_chart(fig_tr, use_container_width=True)

                with ch_r:
                    st.markdown('<div class="section-tag">指標別 達成率</div>',
                                unsafe_allow_html=True)
                    ach_sum = (
                        fac_df.groupby("表示名")
                        .agg(plan=("plan_n", "sum"), fact=("fact_n", "sum"))
                        .reset_index()
                    )
                    ach_sum = ach_sum[ach_sum["plan"] > 0].copy()
                    ach_sum["達成率"] = (ach_sum["fact"] / ach_sum["plan"] * 100).round(1)
                    ach_sum = ach_sum.sort_values("達成率", ascending=True)
                    if not ach_sum.empty:
                        bar_colors = [
                            "#27AE60" if v >= 100 else "#F39C12" if v >= 80 else "#C0392B"
                            for v in ach_sum["達成率"]
                        ]
                        fig_ach = go.Figure(go.Bar(
                            y=ach_sum["表示名"], x=ach_sum["達成率"],
                            orientation="h", marker_color=bar_colors,
                            text=[f"{v:.1f}%" for v in ach_sum["達成率"]],
                            textposition="outside", cliponaxis=False,
                        ))
                        fig_ach.add_vline(x=100,
                                          line=dict(color="#555", dash="dash", width=1.5),
                                          annotation_text=" 目標100%",
                                          annotation_font_size=10)
                        apply_chart_theme(fig_ach, height=340,
                                          margin=dict(t=20, b=10, l=10, r=60))
                        fig_ach.update_layout(xaxis_title="達成率（%）", showlegend=False)
                        st.plotly_chart(fig_ach, use_container_width=True)

                # ── 達成率ヒートマップ ─────────────────────────
                st.markdown('<div class="section-tag">達成率ヒートマップ（指標 × 日付）</div>',
                            unsafe_allow_html=True)
                heat_df = fac_df[fac_df["plan_n"] > 0].copy()
                if not heat_df.empty and heat_df["ach"].notna().any():
                    heat_piv = heat_df.pivot_table(
                        index="表示名", columns="date", values="ach", aggfunc="mean"
                    )
                    heat_piv.columns = [
                        pd.to_datetime(str(c)).strftime("%m/%d")
                        for c in heat_piv.columns
                    ]
                    z_arr   = heat_piv.values
                    txt_arr = [[f"{v:.0f}%" if pd.notna(v) else "－" for v in row]
                               for row in z_arr]
                    cell_h  = max(50, min(80, 400 // max(len(heat_piv), 1)))
                    fig_h = go.Figure(data=go.Heatmap(
                        z=z_arr, x=list(heat_piv.columns), y=list(heat_piv.index),
                        colorscale=[
                            [0.0,  "#C0392B"],
                            [0.5,  "#F39C12"],
                            [0.75, "#27AE60"],
                            [1.0,  "#1A5276"],
                        ],
                        zmid=100, zmin=0, zmax=150,
                        text=txt_arr, texttemplate="%{text}",
                        textfont=dict(size=max(9, min(13, cell_h // 4))),
                        showscale=True,
                        colorbar=dict(title="達成率(%)", ticksuffix="%", len=0.8),
                    ))
                    fig_h.update_layout(xaxis=dict(title="日付"), yaxis_title="")
                    apply_chart_theme(
                        fig_h,
                        height=max(180, len(heat_piv) * cell_h + 60),
                        margin=dict(t=10, b=40, l=10, r=80),
                    )
                    st.plotly_chart(fig_h, use_container_width=True)

            # ── 統計サマリーテーブル ───────────────────────────
            st.divider()
            st.markdown('<div class="section-tag">統計サマリー</div>', unsafe_allow_html=True)
            stat_df = (
                fac_df.dropna(subset=["fact_n"])
                .groupby("表示名")
                .agg(
                    日数=("date", "nunique"),
                    計画合計=("plan_n", lambda x: round(x.sum(), 1)),
                    実績合計=("fact_n", lambda x: round(x.sum(), 1)),
                    日平均=("fact_n", lambda x: round(x.mean(), 1)),
                    最大=("fact_n", lambda x: round(x.max(), 1)),
                    最小=("fact_n", lambda x: round(x.min(), 1)),
                    変動係数CV=("fact_n", lambda x: (
                        round(x.std() / x.mean() * 100, 1)
                        if len(x) > 1 and x.mean() > 0 else 0.0
                    )),
                )
                .reset_index()
            )
            stat_df["達成率(%)"] = stat_df.apply(
                lambda r: round(r["実績合計"] / r["計画合計"] * 100, 1)
                if r["計画合計"] > 0 else None, axis=1
            )
            themed_table(stat_df.rename(columns={"表示名": "指標"}), height=260)

            with st.expander("📋 詳細データ一覧"):
                disp = fac_df[["date", "表示名", "unit", "plan_n", "fact_n", "ach"]].copy()
                disp["ach"] = disp["ach"].round(1)
                themed_table(disp.rename(columns={
                    "date": "日付", "表示名": "指標", "unit": "単位",
                    "plan_n": "計画", "fact_n": "実績", "ach": "達成率(%)",
                }).sort_values("日付"), height=380)

st.divider()

# ── 全工場 全指標一覧 ─────────────────────────────────────────
with st.expander("📋 全工場 全指標一覧"):
    keyword = st.text_input("指標名で検索（日本語/ロシア語）", key="ind_kw")
    show = df.copy()
    if keyword:
        show = show[
            show["indicator_ru"].fillna("").str.contains(keyword, case=False) |
            show["indicator_jp"].fillna("").str.contains(keyword, case=False)
        ]
    show["指標"] = show.apply(
        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
    )
    show["達成率(%)"] = show["ach"].round(1)
    themed_table(
        show[["date", "factory", "指標", "unit", "plan_n", "fact_n", "達成率(%)"]].rename(columns={
            "date": "日付", "factory": "工場", "unit": "単位",
            "plan_n": "計画", "fact_n": "実績",
        }),
        height=450,
    )

# ── データ削除 ────────────────────────────────────────────────
with st.expander("🗑️ データを削除"):
    dc1, dc2, dc3 = st.columns(3)
    del_fac = dc1.selectbox("工場", [""] + ALL_FACTORIES,
                            format_func=lambda v: "すべての工場" if v == "" else v, key="od_fac")
    with dc2:
        del_from = jp_date_input("開始日", date.today().replace(day=1), "od_from")
    with dc3:
        del_to = jp_date_input("終了日", date.today(), "od_to")
    if st.button("⚠️  条件に一致するデータを削除（取り消し不可）", type="primary", key="od_del"):
        deleted = delete_operative_bulk(del_fac, str(del_from), str(del_to))
        st.success(f"✅  {deleted} 件を削除しました。")
        st.rerun()
