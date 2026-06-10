import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils.data_store import get_operative, translate_unit
from utils.ui_helpers import (
    themed_table, page_setup, apply_chart_theme, jp_date_input,
    plan_fact_bar, achievement_bar, animated_kpi_html,
    page_header_html, get_palette,
    PRIMARY, COLOR_OK, COLOR_WARN, COLOR_ERR, TEXT, TEXT_SUB, jst_today
)

st.set_page_config(page_title="土場", page_icon="🪨", layout="wide")
page_setup()

st.markdown(page_header_html(
    "土場（УПСС）",
    subtitle="Log Yard — Raw Material Flow",
    icon="🪨",
    right_text=jst_today().strftime("%Y年%m月%d日"),
), unsafe_allow_html=True)

# ── フィルター ────────────────────────────────────────────────
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        date_from = jp_date_input("開始日", jst_today().replace(day=1), "dp_from")
    with c2:
        date_to = jp_date_input("終了日", jst_today(), "dp_to")

df = get_operative("土場", str(date_from), str(date_to))

if df.empty:
    st.info("土場の生産データがありません。「データ取込」から1C日報をインポートしてください。")
    st.stop()

df_w = df.copy()
_dp_days = (date_to - date_from).days
_dp_daily = _dp_days <= 62
if _dp_daily:
    df_w["期間"] = df_w["date"].astype(str)
    _dp_xlabel = "日付"
    _dp_title_sfx = "日別"
else:
    df_w["期間"] = pd.to_datetime(df_w["date"], errors="coerce").dt.strftime("%Y年%m月")
    _dp_xlabel = "月"
    _dp_title_sfx = "月別"
df_w["表示名"] = df_w.apply(
    lambda r: r["indicator_jp"] if r["indicator_jp"] else r["indicator_ru"][:30], axis=1
)
df_w["fact"] = pd.to_numeric(df_w["fact"], errors="coerce")
df_w["plan"] = pd.to_numeric(df_w["plan"], errors="coerce")

# ── 主要指標の抽出 ─────────────────────────────────────────────
def _sum(prefix: str) -> float | None:
    kdf = df_w[df_w["indicator_ru"].str.startswith(prefix, na=False)]
    v = kdf["fact"].sum() if not kdf.empty else None
    return v if (v is not None and v == v and v > 0) else None

def _plan(prefix: str) -> float | None:
    kdf = df_w[df_w["indicator_ru"].str.startswith(prefix, na=False)]
    p = kdf["plan"].sum() if not kdf.empty else None
    return p if (p is not None and p == p and p > 0) else None

v_input   = _sum("Поступило сырья")
v_sort    = _sum("Сортировка сырья")
p_input   = _plan("Поступило сырья")
days      = df["date"].nunique()
last_date = df["date"].max()

def _pct(val, plan):
    if val and plan and plan > 0:
        return val / plan * 100
    return None

pct_input = _pct(v_input, p_input)

def _col(pct):
    if pct is None: return PRIMARY
    if pct >= 100:  return COLOR_OK
    if pct >= 80:   return PRIMARY
    if pct >= 60:   return COLOR_WARN
    return COLOR_ERR

# ── KPI ──────────────────────────────────────────────────────
kpi_html = (
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0">'
    + animated_kpi_html(
        f"{v_input:,.0f}" if v_input else "未取込", "原木入荷量（累計）",
        delta=f"計画比 {pct_input:.0f}%" if pct_input else "",
        icon="🌲", color=_col(pct_input), progress=pct_input,
    )
    + animated_kpi_html(
        f"{v_sort:,.0f}" if v_sort else "未取込", "仕分け量（累計）",
        icon="🔄", color=PRIMARY,
    )
    + animated_kpi_html(f"{days} 日", "取込日数", icon="📅", color=PRIMARY)
    + animated_kpi_html(str(last_date) if last_date else "－", "最新データ日",
                        icon="🗓️", color=PRIMARY)
    + "</div>"
)
st.markdown(kpi_html, unsafe_allow_html=True)

st.divider()

# ── グラフセクション ──────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.markdown(f'<div class="section-tag">{_dp_title_sfx} 原木入荷量 推移</div>', unsafe_allow_html=True)
    agg_input = (
        df_w[df_w["indicator_ru"].str.startswith("Поступило сырья", na=False)]
        .groupby("期間")["fact"].sum().reset_index()
    )
    agg_input = agg_input[agg_input["fact"] > 0]
    if not agg_input.empty:
        fig = px.bar(
            agg_input, x="期間", y="fact",
            labels={"fact": "入荷量", "期間": _dp_xlabel},
            color_discrete_sequence=[PRIMARY],
        )
        fig.update_traces(marker_opacity=0.85)
        apply_chart_theme(fig, height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("入荷量データがありません。")

with col_b:
    st.markdown(f'<div class="section-tag">{_dp_title_sfx} 仕分け量 推移</div>', unsafe_allow_html=True)
    agg_sort = (
        df_w[df_w["indicator_ru"].str.startswith("Сортировка сырья", na=False)]
        .groupby("期間")["fact"].sum().reset_index()
    )
    agg_sort = agg_sort[agg_sort["fact"] > 0]
    if not agg_sort.empty:
        fig2 = px.bar(
            agg_sort, x="期間", y="fact",
            labels={"fact": "仕分け量", "期間": _dp_xlabel},
            color_discrete_sequence=["#8B5E3C"],
        )
        fig2.update_traces(marker_opacity=0.85)
        apply_chart_theme(fig2, height=320)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("仕分けデータがありません。")

st.divider()
col_c, col_d = st.columns(2)

with col_c:
    st.markdown('<div class="section-tag">計画／実績 比較</div>', unsafe_allow_html=True)
    agg2 = df_w.groupby("表示名").agg(plan=("plan", "sum"), fact=("fact", "sum")).reset_index()
    agg2 = agg2[agg2["fact"] > 0].head(8)
    if not agg2.empty:
        st.plotly_chart(plan_fact_bar(agg2, title="", height=320), use_container_width=True)
    else:
        st.info("計画／実績データがありません。")

with col_d:
    st.markdown('<div class="section-tag">日別 入荷量トレンド</div>', unsafe_allow_html=True)
    daily_in = (
        df_w[df_w["indicator_ru"].str.startswith("Поступило сырья", na=False)]
        .groupby("date")["fact"].sum().reset_index()
    )
    daily_in = daily_in[daily_in["fact"] > 0]
    if not daily_in.empty:
        fig_d = px.area(
            daily_in, x="date", y="fact",
            labels={"date": "日付", "fact": "入荷量"},
            color_discrete_sequence=[PRIMARY],
        )
        fig_d.update_traces(fill="tozeroy", opacity=0.7, line_width=2)
        apply_chart_theme(fig_d, height=320)
        st.plotly_chart(fig_d, use_container_width=True)
    else:
        st.info("日別トレンドデータがありません。")

st.divider()

# ── 達成率 ────────────────────────────────────────────────────
st.markdown('<div class="section-tag">指標別 達成率</div>', unsafe_allow_html=True)
ach = df_w.groupby("表示名").agg(plan=("plan", "sum"), fact=("fact", "sum")).reset_index()
ach = ach[(ach["plan"] > 0) & (ach["fact"] > 0)].head(8)
if not ach.empty:
    ach["達成率"] = (ach["fact"] / ach["plan"] * 100).round(1)
    st.plotly_chart(
        achievement_bar(ach["表示名"].tolist(), ach["達成率"].tolist(),
                        title="", height=280),
        use_container_width=True,
    )
else:
    st.info("達成率データがありません。")

st.divider()

# ── 詳細テーブル ──────────────────────────────────────────────
with st.expander("📋 詳細データ一覧"):
    kw = st.text_input("指標検索", key="dp_kw", placeholder="キーワードで絞り込み")
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
    st.download_button("📥 CSV出力", csv, file_name="土場_operative.csv", mime="text/csv")
