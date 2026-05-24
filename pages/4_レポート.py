import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import date as _date, timedelta
from utils.data_store import get_stoppages
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import (
    themed_table, page_setup, apply_chart_theme,
    jp_date_input, unit_radio, extract_stop_type, smart_period,
    calendar_heatmap, get_palette,
    COLOR_ERR, PRIMARY, TEXT, TEXT_SUB,
)

st.set_page_config(page_title="レポート", page_icon="📋", layout="wide")
page_setup()
st.title("📋 停止分析レポート")

# ── フィルター ────────────────────────────────────────────────
with st.container(border=True):
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
    with c1:
        date_from = jp_date_input("開始日", _date.today().replace(month=1, day=1), "rep_from")
    with c2:
        date_to = jp_date_input("終了日", _date.today(), "rep_to")
    sel_factory = c3.selectbox("工場", ["全工場"] + TARGET_FACTORIES)
    with c4:
        unit, divisor = unit_radio()

unit_label     = f"停止時間（{unit}）"
factory_filter = "" if sel_factory == "全工場" else sel_factory
df_stop = get_stoppages(factory_filter, str(date_from), str(date_to))

# 比較期間（同期間長の前期）
_period_days = max((date_to - date_from).days, 1)
_prev_to     = date_from - timedelta(days=1)
_prev_from   = _prev_to - timedelta(days=_period_days - 1)
df_prev = get_stoppages(factory_filter, str(_prev_from), str(_prev_to))

if df_stop.empty:
    st.info("停止データがありません。「データ取込」からインポートしてください。")
    st.stop()

# ── 集計（タブ間で共有） ──────────────────────────────────────
total_stops = len(df_stop)
total_h     = df_stop["duration_minutes"].sum() / divisor
avg_dur     = df_stop["duration_minutes"].mean() / divisor
most_fac    = df_stop.groupby("factory")["duration_minutes"].sum().idxmax()
prev_stops  = len(df_prev)
prev_h      = df_prev["duration_minutes"].sum() / divisor if not df_prev.empty else 0

# パレート集計（tab2 と tab4 で共有）
_reason_src = df_stop[df_stop["reason"].fillna("").str.strip() != ""]
pareto_df   = (_reason_src.groupby("reason")["duration_minutes"].sum()
               .sort_values(ascending=False).head(15).reset_index())
if not pareto_df.empty:
    pareto_df["val"]         = pareto_df["duration_minutes"] / divisor
    pareto_df["cumsum"]      = pareto_df["val"].cumsum()
    pareto_df["cumsum_pct"]  = (pareto_df["cumsum"] / pareto_df["val"].sum() * 100).round(1)
    pareto_df["label"]       = pareto_df["reason"].apply(
        lambda s: s[:21] + "…" if len(str(s)) > 22 else s
    )

# 工場別サマリー（tab1・tab4 共有）
summary = (
    df_stop.groupby("factory")
    .agg(停止件数=("id", "count"), _tot=("duration_minutes", "sum"),
         _avg=("duration_minutes", "mean"))
    .reset_index()
)
summary[f"総停止時間({unit})"]   = (summary["_tot"] / divisor).round(1)
summary[f"平均停止時間({unit})"] = (summary["_avg"] / divisor).round(1)
summary = summary.drop(columns=["_tot", "_avg"]).rename(columns={"factory": "工場"})


def _delta(curr, prev, fmt=".0f", suffix=""):
    if prev == 0:
        return None
    diff = curr - prev
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:{fmt}}{suffix}（前期比）"


# ── KPI カード ────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("停止件数",
          f"{total_stops} 件",
          delta=_delta(total_stops, prev_stops, ".0f", "件"),
          delta_color="inverse")
k2.metric(f"総停止時間（{unit}）",
          f"{total_h:.1f} {unit}",
          delta=_delta(total_h, prev_h, ".1f", unit),
          delta_color="inverse")
k3.metric(f"平均停止時間（{unit}/件）",
          f"{avg_dur:.1f} {unit}" if total_stops else "－")
k4.metric("最多停止工場",  most_fac)
k5.metric("比較前期",
          f"{_prev_from.strftime('%m/%d')}〜{_prev_to.strftime('%m/%d')}")

st.divider()

# ════════ タブ ════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs(["📊 総合分析", "🔍 原因分析", "📅 時系列", "📥 出力"])

# ════════ 総合分析 ════════════════════════════════════════════
with tab1:
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown('<div class="section-tag">停止時間推移（停止種類別 + 3期移動平均）</div>',
                    unsafe_allow_html=True)
        df_plot, _, x_title = smart_period(df_stop, date_from, date_to)
        df_plot["停止種類"] = df_plot["reason"].apply(extract_stop_type)
        df_plot["val"]     = df_plot["duration_minutes"] / divisor
        agg = (df_plot.groupby(["period", "period_dt", "停止種類"])["val"]
               .sum().reset_index().sort_values("period_dt"))

        fig_trend = px.bar(
            agg, x="period", y="val", color="停止種類", barmode="stack",
            labels={"period": x_title, "val": unit_label, "停止種類": ""},
            color_discrete_sequence=get_palette(),
            category_orders={"period": agg["period"].unique().tolist()},
        )
        tot_per = (agg.groupby(["period", "period_dt"])["val"]
                   .sum().reset_index().sort_values("period_dt"))
        if len(tot_per) >= 3:
            tot_per["ma"] = tot_per["val"].rolling(3, min_periods=1).mean()
            fig_trend.add_scatter(
                x=tot_per["period"], y=tot_per["ma"],
                mode="lines+markers", name="3期移動平均",
                line=dict(color="#E15759", width=2.5, dash="dot"),
                marker=dict(size=6),
            )
        apply_chart_theme(fig_trend, height=340, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_trend, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-tag">工場別 停止時間</div>', unsafe_allow_html=True)
        fac_plot = summary.sort_values(f"総停止時間({unit})", ascending=True)
        fig_fac = go.Figure(go.Bar(
            y=fac_plot["工場"], x=fac_plot[f"総停止時間({unit})"],
            orientation="h", marker_color="#4E79A7",
            text=[f"{v:.1f}{unit}" for v in fac_plot[f"総停止時間({unit})"]],
            textposition="outside", cliponaxis=False,
        ))
        apply_chart_theme(fig_fac, height=280, margin=dict(t=10, b=10, l=10, r=60))
        fig_fac.update_layout(xaxis_title=unit_label, showlegend=False)
        st.plotly_chart(fig_fac, use_container_width=True)

        st.markdown('<div class="section-tag">工場別 MTTR（平均停止時間）</div>',
                    unsafe_allow_html=True)
        themed_table(summary.rename(columns={
            f"総停止時間({unit})": f"合計({unit})",
            f"平均停止時間({unit})": f"MTTR({unit})",
        }), height=200)

    st.divider()
    st.markdown('<div class="section-tag">🔧 エリア・設備別 停止時間 TOP10</div>',
                unsafe_allow_html=True)
    area_agg = (df_stop.groupby("area")["duration_minutes"].sum()
                .sort_values(ascending=True).tail(10).reset_index())
    area_agg["val"] = (area_agg["duration_minutes"] / divisor).round(1)
    fig_area = px.bar(
        area_agg, y="area", x="val", orientation="h",
        color="val", color_continuous_scale="OrRd",
        labels={"area": "エリア/設備", "val": unit_label},
        text=[f"{v:.1f}{unit}" for v in area_agg["val"]],
    )
    fig_area.update_traces(textposition="outside", cliponaxis=False)
    apply_chart_theme(fig_area, height=max(280, len(area_agg) * 38),
                      margin=dict(t=10, b=10, l=10, r=70))
    fig_area.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig_area, use_container_width=True)

# ════════ 原因分析 ════════════════════════════════════════════
with tab2:
    col_p, col_q = st.columns([3, 2])

    with col_p:
        st.markdown('<div class="section-tag">📊 停止原因 パレート分析（累積80%ライン付き）</div>',
                    unsafe_allow_html=True)
        if not pareto_df.empty:
            fig_par = go.Figure()
            fig_par.add_bar(
                x=pareto_df["label"], y=pareto_df["val"],
                name="停止時間", marker_color="#4E79A7",
                hovertext=pareto_df["reason"], hoverinfo="text+y",
            )
            fig_par.add_scatter(
                x=pareto_df["label"], y=pareto_df["cumsum_pct"],
                mode="lines+markers+text", name="累積割合",
                yaxis="y2", line=dict(color="#F28E2B", width=2.5),
                marker=dict(size=7),
                text=[f"{v:.0f}%" for v in pareto_df["cumsum_pct"]],
                textposition="top center", textfont=dict(size=9),
            )
            fig_par.add_hline(
                y=80, yref="y2",
                line=dict(color="#E15759", dash="dash", width=1.5),
                annotation_text=" 80%", annotation_position="right",
            )
            fig_par.update_layout(
                yaxis=dict(title=unit_label),
                yaxis2=dict(title="累積割合(%)", overlaying="y", side="right",
                            range=[0, 115], ticksuffix="%"),
                xaxis=dict(tickangle=-30),
                legend=dict(orientation="h", y=1.08),
            )
            apply_chart_theme(fig_par, height=420, margin=dict(t=20, b=90, l=10, r=60))
            st.plotly_chart(fig_par, use_container_width=True)
        else:
            st.info("停止理由データがありません。")

    with col_q:
        st.markdown('<div class="section-tag">停止種類 内訳</div>', unsafe_allow_html=True)
        type_df = df_stop.copy()
        type_df["停止種類"] = type_df["reason"].apply(extract_stop_type)
        type_grp = (type_df.groupby("停止種類")["duration_minutes"].sum()
                    .reset_index().sort_values("duration_minutes", ascending=False))
        type_grp["val"] = (type_grp["duration_minutes"] / divisor).round(1)
        fig_pie = px.pie(
            type_grp, names="停止種類", values="val",
            color_discrete_sequence=get_palette(), hole=0.42,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label",
                              textfont=dict(size=11))
        apply_chart_theme(fig_pie, height=260, margin=dict(t=10, b=10, l=10, r=10))
        fig_pie.update_layout(showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown('<div class="section-tag">理由別 件数・時間ランキング</div>',
                    unsafe_allow_html=True)
        cnt_rank = (
            _reason_src.groupby("reason")
            .agg(件数=("id", "count"), 合計=("duration_minutes", "sum"))
            .reset_index().sort_values("合計", ascending=False).head(8)
        )
        cnt_rank[unit_label] = (cnt_rank["合計"] / divisor).round(1)
        themed_table(cnt_rank[["reason", "件数", unit_label]].rename(
            columns={"reason": "停止理由"}), height=280)

    st.divider()

    # 工場 × 停止理由 ヒートマップ
    st.markdown('<div class="section-tag">🔥 工場 × 停止理由 ヒートマップ</div>',
                unsafe_allow_html=True)
    cross = df_stop.copy()
    cross["reason_s"] = cross["reason"].fillna("不明").apply(
        lambda s: s[:21] + "…" if len(str(s)) > 22 else s
    )
    top_r = (cross.groupby("reason_s")["duration_minutes"].sum()
             .sort_values(ascending=False).head(10).index.tolist())
    cross_sub = cross[cross["reason_s"].isin(top_r)]
    cross_piv = cross_sub.pivot_table(
        index="factory", columns="reason_s",
        values="duration_minutes", aggfunc="sum", fill_value=0,
    )
    cross_h = (cross_piv / divisor).round(1)
    if not cross_h.empty:
        fig_cr = go.Figure(data=go.Heatmap(
            z=cross_h.values,
            x=list(cross_h.columns),
            y=list(cross_h.index),
            colorscale=[[0, "#F7F7F7"], [0.25, "#FBBF24"], [1, "#C0392B"]],
            text=[[f"{v:.1f}" for v in row] for row in cross_h.values],
            texttemplate="%{text}", textfont=dict(size=10),
            showscale=True,
            colorbar=dict(title=unit, len=0.8),
        ))
        fig_cr.update_layout(
            xaxis=dict(tickangle=-30, title="停止理由"),
            yaxis_title="工場",
        )
        apply_chart_theme(fig_cr,
                          height=max(200, len(cross_h) * 52 + 80),
                          margin=dict(t=10, b=90, l=10, r=80))
        st.plotly_chart(fig_cr, use_container_width=True)

# ════════ 時系列 ══════════════════════════════════════════════
with tab3:
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="section-tag">曜日別 停止パターン</div>', unsafe_allow_html=True)
        wd_df = df_stop.copy()
        wd_df["weekday_n"] = pd.to_datetime(wd_df["date"]).dt.dayofweek
        WDAY = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
        wd_df["曜日"] = wd_df["weekday_n"].map(WDAY)
        wd_agg = (wd_df.groupby(["weekday_n", "曜日"])
                  .agg(件数=("id", "count"), 合計=("duration_minutes", "sum"))
                  .reset_index().sort_values("weekday_n"))
        wd_agg["停止時間"] = (wd_agg["合計"] / divisor).round(1)

        fig_wd = go.Figure()
        fig_wd.add_bar(x=wd_agg["曜日"], y=wd_agg["停止時間"],
                       marker_color="#4E79A7", name="停止時間",
                       text=[f"{v:.1f}" for v in wd_agg["停止時間"]],
                       textposition="outside")
        fig_wd.add_scatter(
            x=wd_agg["曜日"], y=wd_agg["件数"],
            mode="lines+markers", name="件数",
            yaxis="y2", line=dict(color="#F28E2B", width=2.5),
            marker=dict(size=8),
        )
        fig_wd.update_layout(
            yaxis=dict(title=unit_label),
            yaxis2=dict(title="件数", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.08),
        )
        apply_chart_theme(fig_wd, height=320, margin=dict(t=20, b=10, l=10, r=50))
        st.plotly_chart(fig_wd, use_container_width=True)

    with col_b:
        st.markdown('<div class="section-tag">月別 停止時間推移</div>', unsafe_allow_html=True)
        mon_df = df_stop.copy()
        mon_df["month"]    = pd.to_datetime(mon_df["date"]).dt.strftime("%Y年%m月")
        mon_df["month_dt"] = (pd.to_datetime(mon_df["date"])
                              .dt.to_period("M").dt.to_timestamp())
        mon_agg = (mon_df.groupby(["month", "month_dt"])["duration_minutes"]
                   .sum().reset_index().sort_values("month_dt"))
        mon_agg["val"] = (mon_agg["duration_minutes"] / divisor).round(1)

        fig_mon = px.bar(
            mon_agg, x="month", y="val",
            labels={"month": "月", "val": unit_label},
            color="val", color_continuous_scale="Blues",
            text=[f"{v:.1f}" for v in mon_agg["val"]],
            category_orders={"month": mon_agg["month"].tolist()},
        )
        fig_mon.update_traces(textposition="outside", cliponaxis=False)
        apply_chart_theme(fig_mon, height=320, margin=dict(t=10, b=10, l=10, r=60))
        fig_mon.update_layout(coloraxis_showscale=False, xaxis=dict(tickangle=-30))
        st.plotly_chart(fig_mon, use_container_width=True)

    st.divider()
    st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
    _today = _date.today()
    st.plotly_chart(calendar_heatmap(df_stop, _today.year, _today.month),
                    use_container_width=True)

    st.divider()
    st.markdown('<div class="section-tag">停止記録一覧</div>', unsafe_allow_html=True)
    show = df_stop[["date", "factory", "area", "stop_time", "recovery_time",
                    "duration_minutes", "reason", "response"]].copy()
    show["duration_minutes"] = (show["duration_minutes"] / divisor).round(1)
    themed_table(show.rename(columns={
        "date": "日付", "factory": "工場", "area": "エリア/設備",
        "stop_time": "停止時刻", "recovery_time": "復旧時刻",
        "duration_minutes": unit_label, "reason": "停止理由", "response": "処置内容",
    }), height=420)

# ════════ 出力 ════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-tag">📥 Excelレポート出力</div>', unsafe_allow_html=True)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_stop.drop(columns=["imported_at"], errors="ignore").to_excel(
            writer, sheet_name="停止データ", index=False)
        summary.to_excel(writer, sheet_name="工場別サマリー", index=False)
        if not pareto_df.empty:
            pareto_df[["reason", "val", "cumsum_pct"]].rename(columns={
                "reason": "停止理由", "val": unit_label, "cumsum_pct": "累積割合(%)",
            }).to_excel(writer, sheet_name="パレート分析", index=False)
    buf.seek(0)

    st.download_button(
        "📥 Excelレポートをダウンロード",
        data=buf.getvalue(),
        file_name=f"ALK_レポート_{date_from}_{date_to}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    st.divider()
    st.markdown('<div class="section-tag">工場別サマリー</div>', unsafe_allow_html=True)
    themed_table(summary)
