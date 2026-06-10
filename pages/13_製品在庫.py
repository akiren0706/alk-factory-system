import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils.data_store import get_operative, translate_unit
from utils.ui_helpers import (
    themed_table, page_setup, apply_chart_theme, jp_date_input,
    plan_fact_bar, animated_kpi_html,
    page_header_html, get_palette,
    PRIMARY, COLOR_OK, COLOR_WARN, COLOR_ERR, TEXT, TEXT_SUB, CARD, BORDER, jst_today
)

st.set_page_config(page_title="製品在庫", page_icon="🏪", layout="wide")
page_setup()

st.markdown(page_header_html(
    "製品在庫（СГП）",
    subtitle="Product Warehouse — Inventory Flow",
    icon="🏪",
    right_text=jst_today().strftime("%Y年%m月%d日"),
), unsafe_allow_html=True)

# ── フィルター ────────────────────────────────────────────────
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        date_from = jp_date_input("開始日", jst_today().replace(day=1), "sp_from")
    with c2:
        date_to = jp_date_input("終了日", jst_today(), "sp_to")

df = get_operative("製品在庫", str(date_from), str(date_to))

if df.empty:
    st.info("製品在庫データがありません。「データ取込」から1C日報をインポートしてください。")
    st.stop()

df_w = df.copy()
_sp_days = (date_to - date_from).days
_sp_daily = _sp_days <= 62
if _sp_daily:
    df_w["期間"] = df_w["date"].astype(str)
    _sp_xlabel = "日付"
    _sp_title_sfx = "日別"
else:
    df_w["期間"] = pd.to_datetime(df_w["date"], errors="coerce").dt.strftime("%Y年%m月")
    _sp_xlabel = "月"
    _sp_title_sfx = "月別"
df_w["表示名"] = df_w.apply(
    lambda r: r["indicator_jp"] if r["indicator_jp"] else r["indicator_ru"][:30], axis=1
)
df_w["fact"] = pd.to_numeric(df_w["fact"], errors="coerce")
df_w["plan"] = pd.to_numeric(df_w["plan"], errors="coerce")

def _sum(prefix: str) -> float | None:
    kdf = df_w[df_w["indicator_ru"].str.startswith(prefix, na=False)]
    v = kdf["fact"].sum() if not kdf.empty else None
    return v if (v is not None and v == v and v > 0) else None

v_in    = _sum("Поступило на склад")
v_out   = _sum("Отгружено с СГП")
days    = df["date"].nunique()
last_dt = df["date"].max()
balance = (v_in or 0) - (v_out or 0)

def _bal_color(bal: float) -> str:
    if bal >= 0: return COLOR_OK
    if bal >= -100: return COLOR_WARN
    return COLOR_ERR

# ── KPI ──────────────────────────────────────────────────────
kpi_html = (
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0">'
    + animated_kpi_html(
        f"{v_in:,.0f}" if v_in else "未取込", "入庫量（累計）",
        icon="📥", color=PRIMARY,
    )
    + animated_kpi_html(
        f"{v_out:,.0f}" if v_out else "未取込", "出荷量（累計）",
        icon="📤", color=COLOR_WARN,
    )
    + animated_kpi_html(
        f"{balance:+,.0f}", "在庫増減（入庫－出荷）",
        icon="📊", color=_bal_color(balance),
    )
    + animated_kpi_html(f"{days} 日", "取込日数", icon="📅", color=PRIMARY)
    + "</div>"
)
st.markdown(kpi_html, unsafe_allow_html=True)

st.divider()

# ── 入出庫対比グラフ ─────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.markdown(f'<div class="section-tag">{_sp_title_sfx} 入庫・出荷 推移</div>', unsafe_allow_html=True)
    df_in  = df_w[df_w["indicator_ru"].str.startswith("Поступило на склад", na=False)].copy()
    df_out = df_w[df_w["indicator_ru"].str.startswith("Отгружено с СГП", na=False)].copy()

    agg_in  = df_in.groupby("期間")["fact"].sum().reset_index().rename(columns={"fact": "入庫"})
    agg_out = df_out.groupby("期間")["fact"].sum().reset_index().rename(columns={"fact": "出荷"})
    inout = pd.merge(agg_in, agg_out, on="期間", how="outer").fillna(0)
    inout = inout[(inout["入庫"] > 0) | (inout["出荷"] > 0)]

    if not inout.empty:
        fig = go.Figure()
        fig.add_bar(x=inout["期間"], y=inout["入庫"], name="入庫",
                    marker_color=PRIMARY, opacity=0.85)
        fig.add_bar(x=inout["期間"], y=inout["出荷"], name="出荷",
                    marker_color=COLOR_WARN, opacity=0.85)
        fig.update_layout(barmode="group")
        apply_chart_theme(fig, height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("入出庫データがありません。")

with col_b:
    st.markdown('<div class="section-tag">日別 在庫増減トレンド</div>', unsafe_allow_html=True)
    daily_in  = df_in.groupby("date")["fact"].sum().reset_index().rename(columns={"fact": "入庫"})
    daily_out = df_out.groupby("date")["fact"].sum().reset_index().rename(columns={"fact": "出荷"})
    daily = pd.merge(daily_in, daily_out, on="date", how="outer").fillna(0)
    daily["増減"] = daily["入庫"] - daily["出荷"]
    daily = daily[(daily["入庫"] > 0) | (daily["出荷"] > 0)]

    if not daily.empty:
        daily_m = daily.melt(id_vars="date", value_vars=["入庫", "出荷"],
                             var_name="種別", value_name="数量")
        daily_m = daily_m[daily_m["数量"] > 0]
        fig2 = px.line(
            daily_m, x="date", y="数量", color="種別",
            markers=True,
            color_discrete_map={"入庫": PRIMARY, "出荷": COLOR_WARN},
            labels={"date": "日付", "数量": "数量"},
        )
        fig2.update_traces(line_width=2, marker_size=5)
        apply_chart_theme(fig2, height=320)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("日別トレンドデータがありません。")

st.divider()
col_c, col_d = st.columns(2)

with col_c:
    st.markdown('<div class="section-tag">計画／実績 比較</div>', unsafe_allow_html=True)
    agg2 = df_w.groupby("表示名").agg(plan=("plan", "sum"), fact=("fact", "sum")).reset_index()
    agg2 = agg2[agg2["fact"] > 0].head(8)
    if not agg2.empty:
        st.plotly_chart(plan_fact_bar(agg2, title="", height=300), use_container_width=True)
    else:
        st.info("計画／実績データがありません。")

with col_d:
    st.markdown('<div class="section-tag">指標別 実績割合</div>', unsafe_allow_html=True)
    pie_df = df_w.groupby("表示名")["fact"].sum().reset_index()
    pie_df = pie_df[pie_df["fact"] > 0]
    if not pie_df.empty:
        fig_pie = px.pie(
            pie_df, names="表示名", values="fact",
            color_discrete_sequence=get_palette(),
            hole=0.38,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label",
                              textfont=dict(size=10))
        apply_chart_theme(fig_pie, height=300, margin=dict(t=10, b=10, l=10, r=10))
        fig_pie.update_layout(showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("指標データがありません。")

st.divider()

# ── 詳細テーブル ──────────────────────────────────────────────
with st.expander("📋 詳細データ一覧"):
    kw = st.text_input("指標検索", key="sp_kw", placeholder="キーワードで絞り込み")
    show = df.copy()
    if kw:
        show = show[
            show["indicator_ru"].fillna("").str.contains(kw, case=False) |
            show["indicator_jp"].fillna("").str.contains(kw, case=False)
        ]
    show["達成率(%)"] = (
        pd.to_numeric(show["fact"], errors="coerce") /
        pd.to_numeric(show["plan"], errors="coerce") * 100
    ).round(1).where(pd.to_numeric(show["plan"], errors="coerce") > 0)
    show["unit"] = show["unit"].apply(translate_unit)
    show_disp = show[["date", "indicator_jp", "indicator_ru", "unit", "plan", "fact", "達成率(%)"]].copy()
    show_disp.columns = ["日付", "指標(日)", "指標(露)", "単位", "計画", "実績", "達成率(%)"]
    themed_table(show_disp, height=400)
    csv = show_disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("📥 CSV出力", csv, file_name="製品在庫_operative.csv", mime="text/csv")
