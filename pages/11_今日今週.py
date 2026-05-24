import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils.data_store import get_stoppages, get_operative
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme,
    plan_fact_bar, achievement_bar, gauge_chart, multi_gauge,
    calendar_heatmap, factory_status_cards_html,
    COLOR_OK, COLOR_WARN, COLOR_ERR, PALETTE_MAIN, jst_today
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="メイン", page_icon="🏠", layout="wide")
page_setup()

today      = jst_today()
yesterday  = today - timedelta(days=1)
week_start = today - timedelta(days=today.weekday())
WEEKDAYS   = ["月", "火", "水", "木", "金", "土", "日"]
FICON = {"単板工場": "🪵", "製材工場": "🪚", "ペレット工場": "🌿", "合板工場": "🏗️", "簡易製材工場": "🔨"}

# ── ヘッダー ─────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("🏠 メイン")
with col_h2:
    wd = WEEKDAYS[today.weekday()]
    st.markdown(
        f'<div style="text-align:right;padding-top:1.2rem">'
        f'<div style="font-size:1.3rem;font-weight:700">{today.strftime("%Y年%m月%d日")}（{wd}）</div>'
        f'<div style="font-size:0.82rem;opacity:0.5">今週: {week_start.strftime("%m/%d")} 〜 {today.strftime("%m/%d")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── データ取得 ────────────────────────────────────────────────
df_stop_today     = get_stoppages("", str(today), str(today))
df_op_today       = get_operative("", str(today), str(today))
df_stop_yesterday = get_stoppages("", str(yesterday), str(yesterday))
df_op_yesterday   = get_operative("", str(yesterday), str(yesterday))
df_stop_week      = get_stoppages("", str(week_start), str(today))
df_op_week        = get_operative("", str(week_start), str(today))


# ────── 生産実績セクション ─────────────────────────────────────
def _prod_section(df_op_day, label: str = ""):
    """工場別 生産実績 KPIカード + 計画／実績グラフ"""
    if df_op_day.empty:
        st.warning(f"⚠️  {label}の生産指標データが取り込まれていません。")
        return

    rows = []
    for fac in TARGET_FACTORIES:
        df_f = df_op_day[df_op_day["factory"] == fac]
        if df_f.empty:
            continue
        prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
        for p in prefixes[:1]:
            m = df_f[df_f["indicator_ru"].str.startswith(p, na=False)]
            if not m.empty:
                fact = pd.to_numeric(m["fact"], errors="coerce").sum()
                plan = pd.to_numeric(m["plan"], errors="coerce").sum()
                pct  = fact / plan * 100 if plan > 0 else None
                rows.append({
                    "工場": fac, "icon": FICON.get(fac, "🏭"),
                    "指標": m.iloc[0]["indicator_jp"] or p[:20],
                    "単位": m.iloc[0]["unit"],
                    "実績": fact, "計画": plan, "達成率": pct,
                })
                break

    if not rows:
        st.warning(f"⚠️  {label}の主要指標が見つかりません。")
        return

    # 工場別 KPIカード（大きめに）
    p_cols = st.columns(len(rows))
    for i, r in enumerate(rows):
        pct_str = f"計画比 {r['達成率']:.1f}%" if r["達成率"] is not None else None
        dc = "normal" if (r["達成率"] or 0) >= 100 else "inverse"
        with p_cols[i]:
            st.metric(
                label=f"{r['icon']} {r['工場']}",
                value=f"{r['実績']:,.0f} {r['単位']}",
                delta=pct_str, delta_color=dc,
            )

    # グラフ 2列
    g1, g2 = st.columns(2)
    with g1:
        gauge_items = [{"label": r["工場"], "value": r["達成率"] or 0, "max": 100}
                       for r in rows if r["達成率"] is not None]
        if gauge_items:
            st.plotly_chart(multi_gauge(gauge_items, height=260), use_container_width=True)
    with g2:
        agg = pd.DataFrame([{
            "表示名": f"{r['icon']} {r['工場']}",
            "plan": r["計画"], "fact": r["実績"],
        } for r in rows if r["実績"] > 0 or r["計画"] > 0])
        if not agg.empty:
            st.plotly_chart(
                plan_fact_bar(agg, title="計画／実績", height=280),
                use_container_width=True,
            )


# ────── 停止ステータスカード ──────────────────────────────────
def _factory_status_cards(df_stop_day):
    fac_cards = []
    for fac in TARGET_FACTORIES:
        df_f = df_stop_day[df_stop_day["factory"] == fac] if not df_stop_day.empty else pd.DataFrame()
        cnt = len(df_f)
        hrs = df_f["duration_minutes"].sum() / 60 if not df_f.empty else 0
        status = "ok" if cnt == 0 else ("warn" if hrs < 1 else "err")
        fac_cards.append({
            "name": fac, "icon": FICON.get(fac, "🏭"), "status": status,
            "value": "停止なし" if cnt == 0 else f"{hrs:.1f}h",
            "unit": "" if cnt == 0 else f"({cnt}件)",
            "note": "正常稼働" if cnt == 0 else f"停止 {cnt}件",
        })
    st.markdown(factory_status_cards_html(fac_cards, cols=len(TARGET_FACTORIES)), unsafe_allow_html=True)


# ── タブ ─────────────────────────────────────────────────────
tab_week, tab_yesterday, tab_today = st.tabs([
    "📊 今週のデータ", "⏪ 昨日のデータ", "📆 今日のデータ"
])

# ════════════════════════════════════════════════════════════
with tab_today:
    # ── 生産実績（最優先・トップ） ──────────────────────────
    st.markdown('<div class="section-tag">📊 生産実績（本日）</div>', unsafe_allow_html=True)
    _prod_section(df_op_today, "本日")

    st.divider()

    # ── 本日KPIサマリー ─────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    t_op   = df_op_today["factory"].nunique() if not df_op_today.empty else 0
    t_cnt  = len(df_stop_today)
    t_hrs  = df_stop_today["duration_minutes"].sum() / 60 if not df_stop_today.empty else 0
    t_fac  = df_stop_today["factory"].nunique() if not df_stop_today.empty else 0
    c1.metric("生産データ工場数", f"{t_op} / {len(TARGET_FACTORIES)} 工場")
    c2.metric("本日",             str(today))
    c3.metric("今日の停止件数",   f"{t_cnt} 件")
    c4.metric("今日の停止時間",   f"{t_hrs:.1f} 時間")
    c5.metric("停止影響工場",     f"{t_fac} / {len(TARGET_FACTORIES)} 工場")

    st.divider()

    # ── 工場停止ステータス ──────────────────────────────────
    st.markdown('<div class="section-tag">🏭 工場停止ステータス（本日）</div>', unsafe_allow_html=True)
    _factory_status_cards(df_stop_today)

    st.divider()
    st.subheader("今日の停止データ")
    if df_stop_today.empty:
        st.info("本日の停止データはありません。")
    else:
        show = df_stop_today[["factory", "area", "stop_time", "recovery_time",
                               "duration_minutes", "reason"]].copy()
        show["duration_minutes"] = (show["duration_minutes"] / 60).round(2)
        show.columns = ["工場", "エリア", "停止時刻", "復旧時刻", "停止(h)", "停止理由"]
        themed_table(show)

# ════════════════════════════════════════════════════════════
with tab_yesterday:
    wd_y = WEEKDAYS[yesterday.weekday()]
    st.markdown(
        f'<div style="font-size:1.1rem;font-weight:700;opacity:0.7;margin-bottom:12px">'
        f'📅 {yesterday.strftime("%Y年%m月%d日")}（{wd_y}）</div>',
        unsafe_allow_html=True,
    )

    # ── 生産実績（最優先・トップ） ──────────────────────────
    st.markdown('<div class="section-tag">📊 生産実績（昨日）</div>', unsafe_allow_html=True)
    _prod_section(df_op_yesterday, "昨日")

    st.divider()

    # ── 昨日KPIサマリー ─────────────────────────────────────
    y1, y2, y3, y4 = st.columns(4)
    y_op  = df_op_yesterday["factory"].nunique() if not df_op_yesterday.empty else 0
    y_cnt = len(df_stop_yesterday)
    y_hrs = df_stop_yesterday["duration_minutes"].sum() / 60 if not df_stop_yesterday.empty else 0
    y_fac = df_stop_yesterday["factory"].nunique() if not df_stop_yesterday.empty else 0
    y1.metric("生産データ工場数", f"{y_op} / {len(TARGET_FACTORIES)} 工場")
    y2.metric("昨日の停止件数", f"{y_cnt} 件")
    y3.metric("昨日の停止時間", f"{y_hrs:.1f} 時間")
    y4.metric("停止影響工場",   f"{y_fac} / {len(TARGET_FACTORIES)} 工場")

    st.divider()

    # ── 工場停止ステータス ──────────────────────────────────
    st.markdown('<div class="section-tag">🏭 工場停止ステータス（昨日）</div>', unsafe_allow_html=True)
    _factory_status_cards(df_stop_yesterday)

    st.divider()
    st.subheader("昨日の停止データ")
    if df_stop_yesterday.empty:
        st.info("昨日の停止データはありません。")
    else:
        show_y = df_stop_yesterday[["factory", "area", "stop_time", "recovery_time",
                                    "duration_minutes", "reason"]].copy()
        show_y["duration_minutes"] = (show_y["duration_minutes"] / 60).round(2)
        show_y.columns = ["工場", "エリア", "停止時刻", "復旧時刻", "停止(h)", "停止理由"]
        themed_table(show_y)

# ════════════════════════════════════════════════════════════
with tab_week:
    # ── 週間 生産実績（最優先・トップ） ─────────────────────
    st.markdown('<div class="section-tag">📊 週間 生産実績</div>', unsafe_allow_html=True)
    _prod_section(df_op_week, "今週")

    # 日別 生産トレンド
    if not df_op_week.empty:
        st.divider()
        st.markdown('<div class="section-tag">📈 日別 生産トレンド（今週）</div>', unsafe_allow_html=True)
        trend_rows = []
        for fac in TARGET_FACTORIES:
            df_f = df_op_week[df_op_week["factory"] == fac]
            prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
            for p in prefixes[:1]:
                m = df_f[df_f["indicator_ru"].str.startswith(p, na=False)]
                if not m.empty:
                    for _, row in m.iterrows():
                        fact_v = pd.to_numeric(row["fact"], errors="coerce")
                        if pd.notna(fact_v):
                            trend_rows.append({"日付": row["date"], "工場": fac, "実績": fact_v})
                    break
        if trend_rows:
            tdf = pd.DataFrame(trend_rows)
            tdf["日付"] = pd.to_datetime(tdf["日付"])
            fig_t = px.bar(
                tdf, x="日付", y="実績", color="工場", barmode="group",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"日付": "", "実績": "実績（主要指標）"},
            )
            apply_chart_theme(fig_t, height=300)
            st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    # ── 週間KPIサマリー ─────────────────────────────────────
    w1, w2, w3, w4, w5 = st.columns(5)
    w_op_days = df_op_week["date"].nunique() if not df_op_week.empty else 0
    w_cnt  = len(df_stop_week)
    w_hrs  = df_stop_week["duration_minutes"].sum() / 60 if not df_stop_week.empty else 0
    w_days = df_stop_week["date"].nunique() if not df_stop_week.empty else 0
    most   = (
        df_stop_week.groupby("factory")["duration_minutes"].sum().idxmax()
        if not df_stop_week.empty else "なし"
    )
    w1.metric("生産指標取込日数", f"{w_op_days} 日分")
    w2.metric("週間停止件数",     f"{w_cnt} 件")
    w3.metric("週間停止時間",     f"{w_hrs:.1f} 時間")
    w4.metric("停止発生日数",     f"{w_days} 日")
    w5.metric("最多停止工場",     most)

    st.divider()

    # ── 停止グラフ ──────────────────────────────────────────
    st.markdown('<div class="section-tag">🛑 週間 停止データ</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("曜日別 停止時間")
        if not df_stop_week.empty:
            df_w = df_stop_week.copy()
            df_w["date_dt"] = pd.to_datetime(df_w["date"])
            df_w["曜日"] = df_w["date_dt"].dt.strftime("%m/%d（") + \
                           df_w["date_dt"].dt.weekday.map(lambda x: WEEKDAYS[x]) + "）"
            agg = (df_w.groupby(["date_dt", "曜日"])["duration_minutes"]
                   .sum().reset_index().sort_values("date_dt"))
            agg["停止時間(h)"] = (agg["duration_minutes"] / 60).round(2)
            fig = px.bar(agg, x="曜日", y="停止時間(h)",
                         color_discrete_sequence=["#f59e0b"],
                         labels={"停止時間(h)": "停止時間 (h)"})
            apply_chart_theme(fig, height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("今週の停止データはありません。")

    with col_b:
        st.subheader("工場別 週間停止")
        if not df_stop_week.empty:
            fac_agg = (df_stop_week.groupby("factory")["duration_minutes"]
                       .sum().reset_index())
            fac_agg["停止時間(h)"] = (fac_agg["duration_minutes"] / 60).round(2)
            fac_agg = fac_agg.sort_values("停止時間(h)", ascending=True)
            fig2 = px.bar(fac_agg, y="factory", x="停止時間(h)", orientation="h",
                          color="停止時間(h)", color_continuous_scale="Reds",
                          labels={"factory": "工場"})
            apply_chart_theme(fig2, height=280)
            fig2.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("今週の停止データはありません。")

    # 停止カレンダー
    st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
    if not df_stop_week.empty:
        st.plotly_chart(calendar_heatmap(df_stop_week, today.year, today.month), use_container_width=True)

    st.divider()
    col_c, col_d = st.columns([3, 2])
    with col_c:
        st.subheader("今週の停止データ一覧")
        if not df_stop_week.empty:
            show_w = df_stop_week[["date", "factory", "area", "duration_minutes", "reason"]].copy()
            show_w["停止(h)"] = (show_w["duration_minutes"] / 60).round(2)
            show_w = show_w.drop(columns=["duration_minutes"])
            show_w.columns = ["日付", "工場", "エリア", "停止理由", "停止(h)"]
            themed_table(show_w, height=300)
        else:
            st.info("今週の停止データはありません。")
    with col_d:
        st.subheader("停止理由 内訳")
        if not df_stop_week.empty:
            r_agg = (df_stop_week[df_stop_week["reason"].str.strip() != ""]
                     .groupby("reason")["duration_minutes"].sum()
                     .sort_values(ascending=False).head(6).reset_index())
            if not r_agg.empty:
                r_agg["h"] = (r_agg["duration_minutes"] / 60).round(2)
                fig_r = px.pie(r_agg, names="reason", values="h",
                               color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_r.update_traces(textposition="inside", textinfo="percent+label")
                apply_chart_theme(fig_r, height=300, margin=dict(t=10, b=10, l=10, r=10))
                fig_r.update_layout(showlegend=False)
                st.plotly_chart(fig_r, use_container_width=True)
        else:
            st.info("今週の停止データはありません。")
