import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import date as _date
from utils.data_store import get_stoppages
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme,
    jp_date_input, unit_radio, extract_stop_type, smart_period,
    calendar_heatmap,
    COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_GOOD, PALETTE_MAIN, get_palette,
)

st.set_page_config(page_title="レポート", page_icon="📋", layout="wide")
page_setup()
st.title("📋 レポート・集計分析")

# ── 期間選択 ─────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
with c1:
    date_from = jp_date_input("開始日", _date.today().replace(month=1, day=1), "rep_from")
with c2:
    date_to = jp_date_input("終了日", _date.today(), "rep_to")
sel_factory = c3.selectbox("工場", ["全工場"] + TARGET_FACTORIES)
with c4:
    unit, divisor = unit_radio()

unit_label = f"停止時間({unit})"
factory_filter = "" if sel_factory == "全工場" else sel_factory
df_stop = get_stoppages(factory_filter, str(date_from), str(date_to))

st.divider()

# ── 工場別停止サマリー ────────────────────────────────────────
st.markdown('<div class="section-tag">🏭 工場別 停止サマリー</div>', unsafe_allow_html=True)
if not df_stop.empty:
    def top_reason(g):
        r = g["reason"].value_counts()
        return r.index[0] if len(r) else "－"

    summary = (
        df_stop.groupby("factory")
        .agg(停止件数=("id", "count"), _tot=("duration_minutes", "sum"), _avg=("duration_minutes", "mean"))
        .reset_index()
    )
    top_reasons = df_stop.groupby("factory").apply(top_reason).reset_index()
    top_reasons.columns = ["factory", "最多停止理由"]
    summary = summary.merge(top_reasons, on="factory", how="left")
    summary[f"総停止時間({unit})"]  = (summary["_tot"] / divisor).round(1)
    summary[f"平均停止時間({unit})"] = (summary["_avg"] / divisor).round(1)
    summary = summary.drop(columns=["_tot", "_avg"]).rename(columns={"factory": "工場"})

    # 工場別停止時間の横棒グラフ（achievement_bar スタイル）
    bar_df = summary[["工場", f"総停止時間({unit})"]].copy().sort_values(f"総停止時間({unit})", ascending=True)
    max_val = bar_df[f"総停止時間({unit})"].max()
    if max_val > 0:
        fig_fac = go.Figure(go.Bar(
            y=bar_df["工場"],
            x=bar_df[f"総停止時間({unit})"],
            orientation="h",
            marker=dict(color=COLOR_ERR, opacity=0.82),
            text=[f"{v:.1f}{unit}" for v in bar_df[f"総停止時間({unit})"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:.1f}" + unit + "<extra></extra>",
        ))
        apply_chart_theme(fig_fac, height=max(220, len(bar_df) * 42),
                          margin=dict(t=10, b=10, l=10, r=60))
        fig_fac.update_layout(xaxis_title=f"停止時間({unit})")
        st.plotly_chart(fig_fac, use_container_width=True)

    themed_table(summary)
else:
    st.info("停止データがありません。")

st.divider()

# ── 停止時間推移（停止種類別積み上げ） ─────────────────────────
st.markdown('<div class="section-tag">📈 停止時間推移（停止種類別）</div>', unsafe_allow_html=True)
if not df_stop.empty:
    df_plot, _, x_title = smart_period(df_stop, date_from, date_to)
    df_plot["stop_type"] = df_plot["reason"].apply(extract_stop_type)
    df_plot["val"] = df_plot["duration_minutes"] / divisor
    agg = (
        df_plot.groupby(["period", "period_dt", "stop_type"])["val"]
        .sum().reset_index().sort_values("period_dt")
    )
    fig = px.bar(
        agg, x="period", y="val", color="stop_type",
        barmode="stack",
        labels={"period": x_title, "val": unit_label, "stop_type": "停止種類"},
        color_discrete_sequence=get_palette(),
        category_orders={"period": agg["period"].unique().tolist()},
    )
    apply_chart_theme(fig, height=350, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("データがありません。")

st.divider()

# ── 停止理由 TOP10 ────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.markdown(f'<div class="section-tag">🔝 停止理由 TOP10（{unit}）</div>', unsafe_allow_html=True)
    if not df_stop.empty and df_stop["reason"].notna().any():
        reason_df = (
            df_stop[df_stop["reason"].str.strip().ne("")]
            .groupby("reason")["duration_minutes"].sum()
            .sort_values(ascending=True).tail(10).reset_index()
        )
        reason_df["val"] = reason_df["duration_minutes"] / divisor
        fig3 = px.bar(
            reason_df, x="val", y="reason", orientation="h",
            labels={"val": unit_label, "reason": "停止理由"},
            color="val", color_continuous_scale="RdYlGn_r",
        )
        apply_chart_theme(fig3, height=380, margin=dict(t=10, b=10, l=10, r=10))
        fig3.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("停止理由データがありません。")

with col_r:
    st.markdown('<div class="section-tag">🔝 停止理由 TOP10（件数）</div>', unsafe_allow_html=True)
    if not df_stop.empty and df_stop["reason"].notna().any():
        count_df = (
            df_stop[df_stop["reason"].str.strip().ne("")]
            .groupby("reason").size()
            .sort_values(ascending=True).tail(10).reset_index(name="件数")
        )
        fig4 = px.bar(
            count_df, x="件数", y="reason", orientation="h",
            labels={"reason": "停止理由"},
            color="件数", color_continuous_scale="RdYlGn_r",
        )
        apply_chart_theme(fig4, height=380, margin=dict(t=10, b=10, l=10, r=10))
        fig4.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("停止理由データがありません。")

st.divider()

# ── 期間別 停止時間推移 ───────────────────────────────────────
st.markdown('<div class="section-tag">⚙️ 期間別 停止時間推移</div>', unsafe_allow_html=True)
if not df_stop.empty:
    _rep_days = (date_to - date_from).days
    tmp = df_stop.copy()
    if _rep_days <= 62:
        tmp["period"] = pd.to_datetime(tmp["date"]).dt.strftime("%m月%d日")
        tmp["period_dt"] = pd.to_datetime(tmp["date"]).dt.normalize()
        _rep_xlabel = "日付"
    else:
        tmp["period"] = pd.to_datetime(tmp["date"]).dt.strftime("%Y年%m月")
        tmp["period_dt"] = pd.to_datetime(tmp["date"]).dt.to_period("M").dt.to_timestamp()
        _rep_xlabel = "月"
    months_stop = tmp.groupby(["period", "period_dt"])["duration_minutes"].sum().reset_index()
    months_stop.columns = ["period", "period_dt", "停止時間"]
    months_stop["停止時間"] /= divisor
    months_stop = months_stop.sort_values("period_dt")

    fig_s = px.bar(
        months_stop, x="period", y="停止時間",
        labels={"period": _rep_xlabel, "停止時間": unit_label},
        color_discrete_sequence=["#B83C2B"],
        category_orders={"period": months_stop["period"].tolist()},
    )
    apply_chart_theme(fig_s, height=320)
    st.plotly_chart(fig_s, use_container_width=True)
    themed_table(months_stop[["period", "停止時間"]].rename(
        columns={"period": _rep_xlabel, "停止時間": unit_label}
    ).round(1))
else:
    st.info("データがありません。")

# ── 今月の停止カレンダー ──────────────────────────────────────
if not df_stop.empty:
    st.divider()
    _today = _date.today()
    st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
    st.plotly_chart(calendar_heatmap(df_stop, _today.year, _today.month), use_container_width=True)

# ── Excelレポート出力 ─────────────────────────────────────────
st.divider()
st.markdown('<div class="section-tag">📥 Excelレポート出力</div>', unsafe_allow_html=True)
if not df_stop.empty:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_stop.drop(columns=["imported_at"], errors="ignore").to_excel(
            writer, sheet_name="停止データ", index=False)
        summary.to_excel(writer, sheet_name="工場別サマリー", index=False)
    buf.seek(0)
    st.download_button(
        "📥 Excelレポートをダウンロード", data=buf.getvalue(),
        file_name=f"ALK_レポート_{date_from}_{date_to}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
else:
    st.info("出力するデータがありません。")
