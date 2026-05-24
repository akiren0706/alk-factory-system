import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils.data_store import get_stoppages, get_operative
from utils.master_data import TARGET_FACTORIES, fix_indicator_name
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme,
    plan_fact_bar, achievement_bar, gauge_chart, multi_gauge,
    calendar_heatmap, factory_status_cards_html,
    COLOR_OK, COLOR_WARN, COLOR_ERR, PALETTE_MAIN, jst_today
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="週次レポート", page_icon="📋", layout="wide")
page_setup()

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
FICON = {"単板工場": "🪵", "製材工場": "🪚", "ペレット工場": "🌿", "合板工場": "🏗️", "簡易製材工場": "🔨"}
today = jst_today()


# ── 週算出（日曜始まり / 土曜終わり） ───────────────────────────
def week_bounds(ref: date) -> tuple[date, date]:
    """ref が含まれる週の日曜日〜土曜日を返す"""
    days_since_sun = (ref.weekday() + 1) % 7   # 月=1, 火=2, ..., 土=6, 日=0
    sun = ref - timedelta(days=days_since_sun)
    sat = sun + timedelta(days=6)
    return sun, sat


# セッション: 基準日（デフォルト = 前週の月曜=今週の日曜-7日前）
if "weekly_ref" not in st.session_state:
    days_since_sun = (today.weekday() + 1) % 7
    this_week_sun  = today - timedelta(days=days_since_sun)
    st.session_state.weekly_ref = this_week_sun - timedelta(days=7)  # 前週

ref_date = st.session_state.weekly_ref
w_sun, w_sat = week_bounds(ref_date)

# ── ヘッダー ─────────────────────────────────────────────────
col_h1, col_nav = st.columns([3, 2])
with col_h1:
    st.title("📋 週次レポート")
    st.caption(
        f"対象期間: {w_sun.strftime('%Y年%m月%d日（日）')} 〜 {w_sat.strftime('%m月%d日（土）')}"
    )

with col_nav:
    n1, n2, n3, n4 = st.columns(4)
    if n1.button("◀◀ 4週前"):
        st.session_state.weekly_ref -= timedelta(weeks=4)
        st.rerun()
    if n2.button("◀ 前週"):
        st.session_state.weekly_ref -= timedelta(weeks=1)
        st.rerun()
    if n3.button("次週 ▶"):
        st.session_state.weekly_ref += timedelta(weeks=1)
        st.rerun()
    if n4.button("前週に戻す"):
        days_since_sun = (today.weekday() + 1) % 7
        st.session_state.weekly_ref = today - timedelta(days=days_since_sun + 7)
        st.rerun()

st.divider()

# ── データ取得 ────────────────────────────────────────────────
df_op   = get_operative("", str(w_sun), str(w_sat))
df_stop = get_stoppages("", str(w_sun), str(w_sat))

# ── KPIサマリー ──────────────────────────────────────────────
op_days   = df_op["date"].nunique()   if not df_op.empty   else 0
op_facs   = df_op["factory"].nunique() if not df_op.empty  else 0
stop_cnt  = len(df_stop)
stop_hrs  = df_stop["duration_minutes"].sum() / 60 if not df_stop.empty else 0
stop_facs = df_stop["factory"].nunique() if not df_stop.empty else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("生産指標取込日数", f"{op_days} 日分")
k2.metric("データあり工場数", f"{op_facs} / {len(TARGET_FACTORIES)}")
k3.metric("週間停止件数",     f"{stop_cnt} 件")
k4.metric("週間停止時間",     f"{stop_hrs:.1f} h")
k5.metric("停止影響工場数",   f"{stop_facs} / {len(TARGET_FACTORIES)}")

st.divider()

# ════════════════════════════════════════════════════════════
#  生産実績 サマリー
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">📊 工場別 生産実績（週間合計）</div>', unsafe_allow_html=True)

if df_op.empty:
    st.warning("この週の生産指標データがありません。")
else:
    prod_rows = []
    for fac in TARGET_FACTORIES:
        df_f = df_op[df_op["factory"] == fac]
        if df_f.empty:
            continue
        prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
        for p in prefixes[:1]:
            m = df_f[df_f["indicator_ru"].str.startswith(p, na=False)]
            if not m.empty:
                fact = pd.to_numeric(m["fact"], errors="coerce").sum()
                plan = pd.to_numeric(m["plan"], errors="coerce").sum()
                pct  = fact / plan * 100 if plan > 0 else None
                prod_rows.append({
                    "工場": fac, "icon": FICON.get(fac, "🏭"),
                    "指標": fix_indicator_name(m.iloc[0]["indicator_ru"], m.iloc[0]["indicator_jp"]),
                    "単位": m.iloc[0]["unit"],
                    "実績": fact, "計画": plan, "達成率": pct,
                })
                break

    if prod_rows:
        # KPIカード
        p_cols = st.columns(len(prod_rows))
        for i, r in enumerate(prod_rows):
            pct_str = f"計画比 {r['達成率']:.1f}%" if r["達成率"] is not None else None
            dc = "normal" if (r["達成率"] or 0) >= 100 else "inverse"
            with p_cols[i]:
                st.metric(
                    label=f"{r['icon']} {r['工場']}",
                    value=f"{r['実績']:,.0f} {r['単位']}",
                    delta=pct_str, delta_color=dc,
                )

        # multi_gauge（達成率ゲージ）
        gauge_items = [{"label": r["工場"], "value": r["達成率"] or 0, "max": 100}
                       for r in prod_rows if r["達成率"] is not None]
        if gauge_items:
            st.plotly_chart(multi_gauge(gauge_items, height=200), use_container_width=True)

        # グラフ
        g1, g2 = st.columns(2)
        with g1:
            labels = [r["工場"] for r in prod_rows if r["達成率"] is not None]
            vals   = [r["達成率"] for r in prod_rows if r["達成率"] is not None]
            if labels:
                st.plotly_chart(
                    achievement_bar(labels, vals, title="達成率（%）", height=300),
                    use_container_width=True,
                )
        with g2:
            agg_df = pd.DataFrame([{
                "表示名": f"{r['icon']} {r['工場']}",
                "plan": r["計画"], "fact": r["実績"],
            } for r in prod_rows if r["実績"] > 0 or r["計画"] > 0])
            if not agg_df.empty:
                st.plotly_chart(
                    plan_fact_bar(agg_df, title="計画／実績", height=300),
                    use_container_width=True,
                )

st.divider()

# ════════════════════════════════════════════════════════════
#  日別 生産トレンド
# ════════════════════════════════════════════════════════════
if not df_op.empty:
    st.markdown('<div class="section-tag">📈 日別 生産トレンド</div>', unsafe_allow_html=True)
    trend_rows = []
    for fac in TARGET_FACTORIES:
        df_f = df_op[df_op["factory"] == fac]
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

# ════════════════════════════════════════════════════════════
#  停止データ サマリー
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">🛑 週間 停止サマリー</div>', unsafe_allow_html=True)

if df_stop.empty:
    st.info("この週の停止データはありません。")
else:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("工場別 停止時間")
        fac_agg = (df_stop.groupby("factory")["duration_minutes"]
                   .sum().reset_index())
        fac_agg["停止時間(h)"] = (fac_agg["duration_minutes"] / 60).round(2)
        fac_agg = fac_agg.sort_values("停止時間(h)", ascending=True)
        fig_f = px.bar(fac_agg, y="factory", x="停止時間(h)", orientation="h",
                       color="停止時間(h)", color_continuous_scale="Reds",
                       labels={"factory": "工場"})
        apply_chart_theme(fig_f, height=280)
        fig_f.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_f, use_container_width=True)

    with col_b:
        st.subheader("停止理由 内訳")
        r_agg = (df_stop[df_stop["reason"].str.strip() != ""]
                 .groupby("reason")["duration_minutes"].sum()
                 .sort_values(ascending=False).head(8).reset_index())
        if not r_agg.empty:
            r_agg["h"] = (r_agg["duration_minutes"] / 60).round(2)
            fig_r = px.pie(r_agg, names="reason", values="h",
                           color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_r.update_traces(textposition="inside", textinfo="percent+label")
            apply_chart_theme(fig_r, height=280, margin=dict(t=10, b=10, l=10, r=10))
            fig_r.update_layout(showlegend=False)
            st.plotly_chart(fig_r, use_container_width=True)

    # 停止一覧
    with st.expander("停止データ一覧"):
        show_s = df_stop[["date", "factory", "area", "duration_minutes", "reason"]].copy()
        show_s["停止(h)"] = (show_s["duration_minutes"] / 60).round(2)
        show_s = show_s.drop(columns=["duration_minutes"])
        show_s.columns = ["日付", "工場", "エリア", "停止理由", "停止(h)"]
        themed_table(show_s.sort_values("日付"))

    # 停止カレンダー
    st.markdown('<div class="section-tag">停止カレンダー</div>', unsafe_allow_html=True)
    if not df_stop.empty:
        st.plotly_chart(calendar_heatmap(df_stop, w_sun.year, w_sun.month), use_container_width=True)

st.divider()

# ════════════════════════════════════════════════════════════
#  工場別 詳細
# ════════════════════════════════════════════════════════════
st.markdown('<div class="section-tag">🏭 工場別 詳細</div>', unsafe_allow_html=True)

for fac in TARGET_FACTORIES:
    df_f_op   = df_op[df_op["factory"] == fac]   if not df_op.empty   else pd.DataFrame()
    df_f_stop = df_stop[df_stop["factory"] == fac] if not df_stop.empty else pd.DataFrame()

    has_op   = not df_f_op.empty
    has_stop = not df_f_stop.empty
    icon     = FICON.get(fac, "🏭")

    stop_h = df_f_stop["duration_minutes"].sum() / 60 if has_stop else 0
    stop_n = len(df_f_stop)
    label = f"{icon} {fac}　｜　停止: {stop_n}件 {stop_h:.1f}h"

    with st.expander(label, expanded=True):
        ec1, ec2 = st.columns(2)

        # 生産指標 詳細テーブル
        with ec1:
            st.markdown("**📊 生産指標（日別）**")
            if not has_op:
                st.info("生産データなし")
            else:
                prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])
                # 主要指標を日別ピボット
                if prefixes:
                    m = df_f_op[df_f_op["indicator_ru"].str.startswith(prefixes[0], na=False)].copy()
                    if not m.empty:
                        m["fact"] = pd.to_numeric(m["fact"], errors="coerce")
                        m["plan"] = pd.to_numeric(m["plan"], errors="coerce")
                        m["display_name"] = m.apply(
                            lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                        )
                        pivot_fact = m.pivot_table(index="display_name", columns="date",
                                                   values="fact", aggfunc="sum")
                        pivot_fact.columns = [str(c) for c in pivot_fact.columns]
                        # 週の全日付を強制表示（データなし日は NaN）
                        from datetime import timedelta
                        DAY_JP = ["日","月","火","水","木","金","土"]
                        all_dates = [str(w_sun + timedelta(days=i)) for i in range(7)]
                        short_names = [f"{(w_sun + timedelta(days=i)).day}({DAY_JP[i]})" for i in range(7)]
                        for d in all_dates:
                            if d not in pivot_fact.columns:
                                pivot_fact[d] = float("nan")
                        pivot_fact = pivot_fact[all_dates]
                        pivot_fact.columns = short_names
                        # 合計列
                        pivot_fact["週計"] = pivot_fact.sum(axis=1, min_count=1)
                        # 数値を文字列フォーマットしてからthemed_tableへ渡す
                        fmt_df = pivot_fact.copy()
                        for col in fmt_df.columns:
                            fmt_df[col] = fmt_df[col].apply(
                                lambda v: "－" if pd.isna(v) else f"{v:,.0f}"
                            )
                        fmt_df.index.name = "指標"
                        themed_table(fmt_df.reset_index())
                    else:
                        # 全指標一覧を表示
                        show_all = df_f_op[["indicator_ru", "indicator_jp", "date", "fact", "plan", "unit"]].copy()
                        show_all["指標"] = show_all.apply(lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1)
                        themed_table(show_all[["指標", "date", "fact", "plan", "unit"]].rename(columns={"date": "日付", "fact": "実績", "plan": "計画", "unit": "単位"}))
                else:
                    show_all = df_f_op[["indicator_ru", "indicator_jp", "date", "fact", "plan", "unit"]].copy()
                    show_all["指標"] = show_all.apply(lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1)
                    themed_table(show_all[["指標", "date", "fact", "plan", "unit"]].rename(columns={"date": "日付", "fact": "実績", "plan": "計画", "unit": "単位"}))

        # 停止データ
        with ec2:
            st.markdown("**🛑 停止一覧**")
            if not has_stop:
                st.info("停止データなし")
            else:
                show_fs = df_f_stop[["date", "area", "duration_minutes", "reason"]].copy()
                show_fs["停止(h)"] = (show_fs["duration_minutes"] / 60).round(2)
                show_fs = show_fs.drop(columns=["duration_minutes"])
                show_fs.columns = ["日付", "エリア", "停止理由", "停止(h)"]
                themed_table(show_fs.sort_values("日付"))
