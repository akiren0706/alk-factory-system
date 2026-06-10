import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from utils.data_store import get_stoppages, get_operative, translate_unit
from utils.master_data import TARGET_FACTORIES, fix_indicator_name
from utils.ui_helpers import (
    themed_table,
    page_setup, apply_chart_theme,
    jp_date_input, unit_radio, extract_stop_type, smart_period,
    plan_fact_bar, achievement_bar, gauge_chart, multi_gauge,
    calendar_heatmap, factory_status_cards_html, page_header_html,
    COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_GOOD, PALETTE_MAIN, get_palette, jst_today,
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="ALK 工場管理システム", page_icon="🏭", layout="wide")
page_setup()

FICON = {"単板工場": "🪵", "製材工場": "🪚", "ペレット工場": "🌿", "合板工場": "🏗️", "簡易製材工場": "🔨"}

st.markdown(page_header_html(
    "ALK 工場生産管理システム",
    subtitle="Factory Operations Dashboard",
    icon="🏭",
    right_text=jst_today().strftime("%Y年%m月%d日"),
), unsafe_allow_html=True)

# ── フィルター ───────────────────────────────────────────────
with st.container(border=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    with col_f1:
        sel_factory = st.selectbox("工場", ["全工場"] + TARGET_FACTORIES, key="dash_factory")
    with col_f2:
        date_from = jp_date_input("開始日", jst_today().replace(day=1), "dash_from")
    with col_f3:
        date_to = jp_date_input("終了日", jst_today(), "dash_to")
    with col_f4:
        unit, divisor = unit_radio()

unit_label     = f"停止時間（{unit}）"
factory_filter = "" if sel_factory == "全工場" else sel_factory
with st.spinner("データを読み込み中（初回・年変更時は20〜30秒かかります）..."):
    df_stop = get_stoppages(factory_filter, str(date_from), str(date_to))
    df_op   = get_operative(factory_filter, str(date_from), str(date_to))

# ════════════════════════════════════════════════════════════
# 1. 生産データ（最上部）
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">📊 生産実績</div>', unsafe_allow_html=True)

prod_rows = []
for fac in TARGET_FACTORIES:
    df_f = df_op[df_op["factory"] == fac] if not df_op.empty else pd.DataFrame()
    if df_f.empty:
        continue
    prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
    for p in prefixes[:1]:
        m = df_f[df_f["indicator_ru"].str.startswith(p, na=False)]
        if not m.empty:
            fact_sum = pd.to_numeric(m["fact"], errors="coerce").sum()
            plan_sum = pd.to_numeric(m["plan"], errors="coerce").sum()
            pct = fact_sum / plan_sum * 100 if plan_sum > 0 else None
            prod_rows.append({
                "工場": fac, "icon": FICON.get(fac, "🏭"),
                "指標": fix_indicator_name(m.iloc[0]["indicator_ru"], m.iloc[0]["indicator_jp"]),
                "単位": m.iloc[0]["unit"],
                "計画": plan_sum, "実績": fact_sum, "達成率": pct,
            })
            break

if prod_rows:
    # KPI cards per factory
    p_cols = st.columns(len(prod_rows))
    for i, r in enumerate(prod_rows):
        pct_disp = f"{r['達成率']:.1f}%" if r["達成率"] is not None else "－"
        delta_col = "normal" if (r["達成率"] or 0) >= 100 else "inverse"
        with p_cols[i]:
            st.metric(
                label=f"{r['icon']} {r['工場']}",
                value=f"{r['実績']:,.0f} {translate_unit(r['単位'])}",
                delta=f"計画比 {pct_disp}",
                delta_color=delta_col,
            )

    st.divider()

    # 工場別達成率 マルチゲージ
    gauge_items = [
        {"label": r["工場"], "value": r["達成率"] if r["達成率"] is not None else 0, "max": 100}
        for r in prod_rows
    ]
    if gauge_items:
        st.markdown('<div class="section-tag">工場別 達成率ゲージ</div>', unsafe_allow_html=True)
        fig_mg = multi_gauge(gauge_items, height=220)
        st.plotly_chart(fig_mg, use_container_width=True)

    # 計画／実績 横棒グラフ（全幅）
    agg_df = pd.DataFrame([{
        "表示名": f"{r['icon']} {r['工場']}",
        "plan": r["計画"],
        "fact": r["実績"],
    } for r in prod_rows if r["実績"] > 0 or r["計画"] > 0])
    if not agg_df.empty:
        fig_pf = plan_fact_bar(agg_df, title="計画／実績（期間合計）", height=300)
        st.plotly_chart(fig_pf, use_container_width=True)

    # 期間別生産トレンド（≤62日→日別、>62日→月別）
    if not df_op.empty:
        _dash_days  = (date_to - date_from).days
        _dash_daily = _dash_days <= 62
        trend_df = df_op.copy()
        trend_df["fact_n"] = pd.to_numeric(trend_df["fact"], errors="coerce")

        if _dash_daily:
            trend_df["期間"] = trend_df["date"].astype(str)
            _grp_col   = "期間"
            _x_label   = "日付"
            _chart_title = "工場別 日次生産推移"
        else:
            trend_df["期間"] = pd.to_datetime(trend_df["date"], errors="coerce").dt.strftime("%Y年%m月")
            _grp_col   = "期間"
            _x_label   = "月"
            _chart_title = "工場別 月次生産推移"

        st.markdown(f'<div class="section-tag">{_chart_title}</div>', unsafe_allow_html=True)
        fac_rows = []
        for fac in TARGET_FACTORIES:
            df_f2 = trend_df[trend_df["factory"] == fac]
            prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
            for p in prefixes[:1]:
                m2 = df_f2[df_f2["indicator_ru"].str.startswith(p, na=False)]
                if not m2.empty:
                    for _, row in m2.groupby(_grp_col).agg(fact=("fact_n", "sum")).reset_index().iterrows():
                        fac_rows.append({"期間": row[_grp_col], "工場": fac,
                                         "実績": pd.to_numeric(row["fact"], errors="coerce")})
                    break
        if fac_rows:
            trend_plot = pd.DataFrame(fac_rows).dropna(subset=["実績"])
            trend_plot = trend_plot[trend_plot["実績"] > 0]
            if not trend_plot.empty:
                fig_trend = px.line(
                    trend_plot, x="期間", y="実績", color="工場",
                    markers=True,
                    color_discrete_sequence=get_palette(),
                    labels={"期間": _x_label, "実績": "実績（主要指標）"},
                    title=_chart_title,
                )
                fig_trend.update_traces(line_width=2, marker_size=7)
                apply_chart_theme(fig_trend, height=320, margin=dict(t=40, b=10, l=10, r=10))
                st.plotly_chart(fig_trend, use_container_width=True)

else:
    st.info("生産指標データが取込まれていません。「データ取込」から1C日報をインポートしてください。")

st.divider()

# ════════════════════════════════════════════════════════════
# 2. 工場別ステータス（停止）
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">🏭 工場別ステータス（停止）</div>', unsafe_allow_html=True)

df_stop_all = get_stoppages("", str(date_from), str(date_to))
fac_cards = []
for fac in TARGET_FACTORIES:
    df_f = df_stop_all[df_stop_all["factory"] == fac]
    cnt = len(df_f)
    hrs = df_f["duration_minutes"].sum() / 60 if not df_f.empty else 0
    status = "ok" if cnt == 0 else ("warn" if hrs < 2 else "err")
    fac_cards.append({
        "name": fac, "icon": FICON.get(fac, "🏭"), "status": status,
        "value": "停止なし" if cnt == 0 else f"{hrs:.1f}h",
        "unit": "" if cnt == 0 else f"({cnt}件)",
        "note": "正常稼働" if cnt == 0 else f"停止 {cnt}件",
    })
html = factory_status_cards_html(fac_cards, cols=len(TARGET_FACTORIES))
st.markdown(html, unsafe_allow_html=True)

st.divider()

# ════════════════════════════════════════════════════════════
# 3. 停止 KPI（前月比・前週比付き）
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">⏸️ 停止集計 KPI</div>', unsafe_allow_html=True)

# 比較期間の計算
_period_days  = (date_to - date_from).days + 1
_prev_to      = date_from - timedelta(days=1)
_prev_from    = _prev_to - timedelta(days=_period_days - 1)
df_stop_prev  = get_stoppages(factory_filter, str(_prev_from), str(_prev_to))

total_stops   = len(df_stop)
total_minutes = df_stop["duration_minutes"].sum() if not df_stop.empty else 0
avg_minutes   = df_stop["duration_minutes"].mean() if not df_stop.empty else 0
op_dates      = df_op["date"].nunique() if not df_op.empty else 0
most_fac = (
    df_stop.groupby("factory")["duration_minutes"].sum().idxmax()
    if not df_stop.empty else "－"
)

prev_stops   = len(df_stop_prev)
prev_minutes = df_stop_prev["duration_minutes"].sum() if not df_stop_prev.empty else 0

def _delta_str(curr, prev, unit_str="", fmt=".0f"):
    if prev == 0:
        return None
    diff = curr - prev
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:{fmt}} {unit_str}（前期比）".strip()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("停止件数",       f"{total_stops} 件",
          delta=_delta_str(total_stops, prev_stops, "件"),
          delta_color="inverse")
k2.metric("総停止時間",     f"{total_minutes/divisor:.1f} {unit}",
          delta=_delta_str(total_minutes/divisor, prev_minutes/divisor, unit, ".1f"),
          delta_color="inverse")
k3.metric("平均停止時間",   f"{avg_minutes/divisor:.1f} {unit}/件" if total_stops else "－")
k4.metric("最多停止工場",   most_fac)
k5.metric("生産指標取込日", f"{op_dates} 日分")

st.divider()

# ════════════════════════════════════════════════════════════
# 4. 停止 グラフ
# ════════════════════════════════════════════════════════════
if not df_stop.empty:
    st.markdown('<div class="section-tag">分析グラフ</div>', unsafe_allow_html=True)
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown('<div class="section-tag">停止時間推移</div>', unsafe_allow_html=True)
        df_plot, _, x_title = smart_period(df_stop, date_from, date_to)
        df_plot["停止種類"] = df_plot["reason"].apply(extract_stop_type)
        df_plot["val"]     = df_plot["duration_minutes"] / divisor
        agg = (
            df_plot.groupby(["period", "period_dt", "停止種類"])["val"]
            .sum().reset_index().sort_values("period_dt")
        )
        fig = px.bar(
            agg, x="period", y="val", color="停止種類", barmode="stack",
            labels={"period": x_title, "val": unit_label},
            color_discrete_sequence=get_palette(),
            category_orders={"period": agg["period"].unique().tolist()},
        )
        # トレンドライン（合計値）
        total_agg = agg.groupby(["period", "period_dt"])["val"].sum().reset_index().sort_values("period_dt")
        if len(total_agg) >= 3:
            import numpy as np
            x_idx = list(range(len(total_agg)))
            z = np.polyfit(x_idx, total_agg["val"].values, 1)
            trend_y = np.poly1d(z)(x_idx)
            fig.add_scatter(
                x=total_agg["period"], y=trend_y,
                mode="lines", name="トレンド",
                line=dict(color="#E15759", width=2, dash="dot"),
            )
        apply_chart_theme(fig, height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-tag">停止理由 内訳</div>', unsafe_allow_html=True)
        reason_df = (
            df_stop[df_stop["reason"].str.strip() != ""]
            .groupby("reason")["duration_minutes"].sum()
            .sort_values(ascending=False).head(8).reset_index()
        )
        if not reason_df.empty:
            reason_df["val"] = reason_df["duration_minutes"] / divisor
            reason_df["label"] = reason_df["reason"].str.split("/").str[0].str.strip().str[:18]
            fig2 = px.pie(
                reason_df, names="label", values="val",
                color_discrete_sequence=px.colors.qualitative.Pastel,
                hover_data={"reason": True, "label": False},
            )
            fig2.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate="<b>%{customdata[0]}</b><br>%{value:.1f} " + unit + "  (%{percent})<extra></extra>",
            )
            apply_chart_theme(fig2, height=340, margin=dict(t=10, b=10, l=10, r=160))
            fig2.update_layout(
                showlegend=True,
                legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)),
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # 工場別比較バーチャート
    st.markdown('<div class="section-tag">工場別比較</div>', unsafe_allow_html=True)
    fac_agg = (
        df_stop.groupby("factory")
        .agg(件数=("id", "count"), 時間=("duration_minutes", "sum"))
        .reset_index()
    )
    fac_agg["停止時間"] = (fac_agg["時間"] / divisor).round(1)
    fac_agg = fac_agg.sort_values("停止時間", ascending=True)

    col_fc1, col_fc2 = st.columns(2)
    with col_fc1:
        fig3 = px.bar(
            fac_agg, y="factory", x="停止時間", orientation="h",
            color="停止時間", color_continuous_scale="Blues",
            labels={"factory": "工場", "停止時間": unit_label},
            title="工場別 停止時間",
        )
        apply_chart_theme(fig3, height=280, margin=dict(t=40, b=10, l=100, r=10))
        fig3.update_layout(coloraxis_showscale=False, yaxis=dict(tickfont=dict(size=12)))
        st.plotly_chart(fig3, use_container_width=True)

    with col_fc2:
        fig4 = px.bar(
            fac_agg.sort_values("件数", ascending=True),
            y="factory", x="件数", orientation="h",
            color="件数", color_continuous_scale="Oranges",
            labels={"factory": "工場", "件数": "停止件数"},
            title="工場別 停止件数",
        )
        apply_chart_theme(fig4, height=280, margin=dict(t=40, b=10, l=100, r=10))
        fig4.update_layout(coloraxis_showscale=False, yaxis=dict(tickfont=dict(size=12)))
        st.plotly_chart(fig4, use_container_width=True)

    # 停止カレンダー（今月）
    today = jst_today()
    st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
    fig_cal = calendar_heatmap(df_stop, today.year, today.month)
    st.plotly_chart(fig_cal, use_container_width=True)

else:
    st.info("停止データがありません。「データ取込」からインポートしてください。")

st.divider()

# ════════════════════════════════════════════════════════════
# 予測セクション — 翌週停止時間推計（指数平滑法）
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">🔮 翌週 停止時間予測</div>', unsafe_allow_html=True)

_history_from = str(jst_today().replace(year=jst_today().year - 2))
_df_all = get_stoppages(factory_filter, _history_from, str(jst_today()))
if not _df_all.empty and len(_df_all) >= 7:
    import numpy as np

    _df_all["_dt"] = pd.to_datetime(_df_all["date"], errors="coerce")
    _df_all["_week"] = _df_all["_dt"].dt.to_period("W").dt.start_time
    weekly = (
        _df_all.groupby("_week")["duration_minutes"]
        .sum().reset_index().sort_values("_week")
    )
    weekly["hours"] = weekly["duration_minutes"] / 60

    # 指数平滑法（alpha=0.3）で翌週予測
    alpha = 0.3
    smoothed = weekly["hours"].ewm(alpha=alpha, adjust=False).mean()
    forecast = float(smoothed.iloc[-1])

    # 95%信頼区間（簡易：過去標準偏差）
    std = float(weekly["hours"].std())
    lo  = max(0, forecast - 1.96 * std)
    hi  = forecast + 1.96 * std

    # 過去8週 + 予測1週のグラフ
    plot_w = weekly.tail(8).copy()
    next_week = plot_w["_week"].iloc[-1] + pd.Timedelta(weeks=1)
    forecast_row = pd.DataFrame([{"_week": next_week, "hours": forecast}])
    plot_w["label"] = plot_w["_week"].dt.strftime("%m/%d週")
    forecast_label = next_week.strftime("%m/%d週")

    from utils.ui_helpers import CARD, BORDER, TEXT, TEXT_SUB

    pc1, pc2, pc3 = st.columns([1, 2, 1])
    with pc1:
        trend_dir = "↑ 増加傾向" if forecast > float(smoothed.iloc[-2]) else "↓ 減少傾向"
        trend_col = "#C0392B" if "増加" in trend_dir else "#40916C"
        st.markdown(f"""
<div style="background:{CARD};border:1px solid {BORDER};border-left:4px solid {trend_col};
            border-radius:8px;padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
  <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;
              color:{TEXT_SUB};margin-bottom:6px">翌週 予測停止時間</div>
  <div style="font-size:2.4rem;font-weight:800;color:{TEXT};letter-spacing:-0.04em;line-height:1">
    {forecast:.1f}<span style="font-size:1rem;font-weight:500;margin-left:4px">時間</span>
  </div>
  <div style="font-size:0.75rem;color:{TEXT_SUB};margin-top:8px">
    95%区間: {lo:.1f} 〜 {hi:.1f} h
  </div>
  <div style="font-size:0.78rem;font-weight:600;color:{trend_col};margin-top:6px">
    {trend_dir}
  </div>
</div>
""", unsafe_allow_html=True)

    with pc2:
        fig_fc = go.Figure()
        # 実績（棒）
        fig_fc.add_bar(
            x=plot_w["label"], y=plot_w["hours"],
            name="実績", marker_color="#4E79A7", opacity=0.85,
        )
        # 予測（棒：色違い）
        fig_fc.add_bar(
            x=[forecast_label], y=[forecast],
            name="予測", marker_color="#F28E2B", opacity=0.9,
        )
        # 信頼区間（エラーバー）
        fig_fc.add_scatter(
            x=[forecast_label], y=[forecast],
            error_y=dict(type="data", array=[hi - forecast],
                         arrayminus=[forecast - lo], visible=True,
                         color="#F28E2B", thickness=2, width=8),
            mode="markers", showlegend=False,
            marker=dict(color="#F28E2B", size=8),
        )
        fig_fc.update_layout(
            barmode="group",
            legend=dict(orientation="h", y=1.05),
            xaxis_title="週",
            yaxis_title="停止時間（時間）",
        )
        apply_chart_theme(fig_fc, height=260, margin=dict(t=30, b=10, l=10, r=10))
        st.plotly_chart(fig_fc, use_container_width=True)

    with pc3:
        st.markdown(f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:16px 20px;
            box-shadow:0 1px 3px rgba(0,0,0,0.06);font-size:0.78rem;color:{TEXT_SUB}">
  <div style="font-weight:700;color:{TEXT};margin-bottom:8px">📊 予測モデル</div>
  <div>手法: 指数平滑法</div>
  <div style="margin-top:4px">平滑化係数 α = {alpha}</div>
  <div style="margin-top:4px">学習週数: {len(weekly)}週</div>
  <div style="margin-top:12px;font-size:0.70rem;opacity:0.6">
    ※データが少ないほど<br>予測精度は低くなります
  </div>
</div>
""", unsafe_allow_html=True)
else:
    st.info("予測には過去7日以上の停止データが必要です。")

st.divider()

# ════════════════════════════════════════════════════════════
# 5. サマリーテーブル
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">工場別サマリー</div>', unsafe_allow_html=True)
if not df_stop.empty:
    summary = (
        df_stop.groupby("factory")
        .agg(停止件数=("id", "count"), _tot=("duration_minutes", "sum"), _avg=("duration_minutes", "mean"))
        .reset_index().rename(columns={"factory": "工場"})
    )
    summary[f"総停止時間（{unit}）"]  = (summary["_tot"] / divisor).round(1)
    summary[f"平均停止時間（{unit}）"] = (summary["_avg"] / divisor).round(1)
    themed_table(summary.drop(columns=["_tot", "_avg"]))
else:
    st.info("停止データがありません。")

st.divider()
st.markdown('<div class="section-tag">直近の停止データ（最新20件）</div>', unsafe_allow_html=True)
if not df_stop.empty:
    show = df_stop.head(20).copy()
    show["停止時間"] = (show["duration_minutes"] / divisor).round(1)
    disp_cols  = ["date", "factory", "area", "stop_time", "recovery_time", "停止時間", "reason"]
    col_labels = {
        "date": "日付", "factory": "工場", "area": "エリア/設備",
        "stop_time": "停止時刻", "recovery_time": "復旧時刻",
        "停止時間": unit_label, "reason": "停止理由",
    }
    themed_table(show[[c for c in disp_cols if c in show.columns]].rename(columns=col_labels))
else:
    st.info("データがありません。")
