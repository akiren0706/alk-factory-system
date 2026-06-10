"""
工場別ページ 共通レンダリング
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, date as _date
from utils.data_store import get_stoppages, get_operative, translate_unit
from utils.ui_helpers import (
    themed_table,
    page_setup, apply_chart_theme,
    jp_date_input, unit_radio, extract_stop_type, smart_period,
    plan_fact_bar, achievement_bar, gauge_chart, calendar_heatmap,
    page_header_html, animated_kpi_html, get_palette,
    COLOR_OK, COLOR_WARN, COLOR_ERR, PRIMARY, CARD, BORDER, TEXT, TEXT_SUB, jst_today,
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES
from utils.master_data import fix_indicator_name

FACTORY_ICON = {
    "単板工場":    "🪵",
    "製材工場":    "🪚",
    "ペレット工場": "🌿",
    "合板工場":    "🏗️",
    "簡易製材工場": "🔨",
}

FACTORY_KEY_METRIC = {
    "単板工場":    ("Получено сухого шпона",      "乾燥単板生産量"),
    "製材工場":    ("Производство (товарное)",    "梱包製材量"),
    "ペレット工場": ("Производство пеллет",        "ペレット製造量"),
    "合板工場":    ("Получено необрезной фанеры", "合板製造量"),
    "簡易製材工場": (None,                         "生産量"),
}

# 工場別 生産フロー指標（順番通りに表示）
FACTORY_FLOW: dict[str, list[tuple[str, str, str]]] = {
    "単板工場": [
        ("原木投入量",     "Подано на лущение",           "🌲"),
        ("生単板生産量",   "Получено лущенного шпона",   "🪵"),
        ("乾燥単板生産量", "Получено сухого шпона",       "✅"),
    ],
    "製材工場": [
        ("原木投入量",   "Подано в производство",       "🌲"),
        ("総製材量",     "Производство (валовое)",      "🪚"),
        ("梱包製材量",   "Производство (товарное)",     "📦"),
    ],
    "ペレット工場": [
        ("原料消費量",       "Потребление на производство", "🌿"),
        ("ペレット生産量",   "Производство пеллет",         "⚙️"),
        ("梱包済量",         "Упаковано всего",              "📦"),
    ],
    "合板工場": [
        ("ライン投入量",   "Подано на линии наборки",    "🌲"),
        ("合板生産量",     "Получено необрезной фанеры", "🏗️"),
    ],
}


def _stop_color(count: int) -> str:
    if count == 0: return COLOR_OK
    if count < 5:  return PRIMARY
    if count < 10: return COLOR_WARN
    return COLOR_ERR


def _hour_color(hours: float) -> str:
    if hours == 0:  return COLOR_OK
    if hours < 3:   return PRIMARY
    if hours < 8:   return COLOR_WARN
    return COLOR_ERR


def _ach_color(pct) -> str:
    if pct is None:  return PRIMARY
    if pct >= 100:   return COLOR_OK
    if pct >= 80:    return PRIMARY
    if pct >= 60:    return COLOR_WARN
    return COLOR_ERR


def render_factory_page(factory: str):
    page_setup()

    icon = FACTORY_ICON.get(factory, "🏭")
    st.markdown(page_header_html(
        factory,
        subtitle="Factory Detail View",
        icon=icon,
        right_text=jst_today().strftime("%Y年%m月%d日"),
    ), unsafe_allow_html=True)

    # ── フィルター ────────────────────────────────────────────
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 3, 1])
        with c1:
            date_from = jp_date_input("開始日", jst_today().replace(day=1), f"fv_from_{factory}")
        with c2:
            date_to = jp_date_input("終了日", jst_today(), f"fv_to_{factory}")
        with c3:
            unit, divisor = unit_radio(horizontal=False)

    unit_label = f"停止時間({unit})"
    df_stop = get_stoppages(factory, str(date_from), str(date_to))
    df_op   = get_operative(factory, str(date_from), str(date_to))

    # ── データ計算 ────────────────────────────────────────────
    total_stops   = len(df_stop)
    total_hours   = df_stop["duration_minutes"].sum() / divisor if not df_stop.empty else 0.0
    prod_days     = df_op["date"].nunique() if not df_op.empty else 0

    metric_prefix, metric_label = FACTORY_KEY_METRIC.get(factory, (None, "生産量"))
    prod_fact = prod_plan = ach_pct = None

    if not df_op.empty and metric_prefix:
        krows = df_op[df_op["indicator_ru"].str.startswith(metric_prefix, na=False)]
        if not krows.empty:
            prod_fact = pd.to_numeric(krows["fact"], errors="coerce").sum()
            prod_plan = pd.to_numeric(krows["plan"], errors="coerce").sum()
            if prod_plan and prod_plan > 0:
                ach_pct = prod_fact / prod_plan * 100

    # ── KPIカード（HTMLグリッド） ─────────────────────────────
    prod_val = f"{prod_fact:,.0f}" if prod_fact is not None else "未取込"
    prod_delta = f"達成率 {ach_pct:.1f}%" if ach_pct is not None else ""

    kpi_html = (
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0">'
        + animated_kpi_html(
            f"{total_stops} 件", "停止件数",
            icon="⏸️", color=_stop_color(total_stops),
        )
        + animated_kpi_html(
            f"{total_hours:.1f} {unit}", unit_label,
            icon="⏱️", color=_hour_color(total_hours),
        )
        + animated_kpi_html(
            prod_val, metric_label,
            delta=prod_delta, icon="📦",
            color=_ach_color(ach_pct),
            progress=ach_pct,
        )
        + animated_kpi_html(
            f"{prod_days} 日", "生産日数",
            icon="📅", color=PRIMARY,
        )
        + "</div>"
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── 工場別 生産フロー指標 ─────────────────────────────────
    flow_defs = FACTORY_FLOW.get(factory, [])
    if flow_defs and not df_op.empty:
        flow_cards = []
        for jp_label, ru_prefix, flow_icon in flow_defs:
            kdf_f = df_op[df_op["indicator_ru"].str.startswith(ru_prefix, na=False)]
            if not kdf_f.empty:
                val_f = pd.to_numeric(kdf_f["fact"], errors="coerce").sum()
                pln_f = pd.to_numeric(kdf_f["plan"], errors="coerce").sum()
                pct_f = val_f / pln_f * 100 if pln_f > 0 else None
                flow_cards.append(animated_kpi_html(
                    f"{val_f:,.0f}", jp_label,
                    delta=f"計画比 {pct_f:.0f}%" if pct_f else "",
                    icon=flow_icon,
                    color=_ach_color(pct_f),
                    progress=pct_f,
                ))
        if flow_cards:
            n = len(flow_cards)
            flow_html = (
                f'<div style="display:grid;grid-template-columns:repeat({n},1fr);'
                f'gap:10px;margin:4px 0 12px">'
                + "".join(flow_cards)
                + "</div>"
            )
            st.markdown(
                '<div class="section-tag" style="margin-top:4px">生産フロー</div>',
                unsafe_allow_html=True,
            )
            st.markdown(flow_html, unsafe_allow_html=True)

    # ── ゲージ＋日別ミニトレンド ──────────────────────────────
    if ach_pct is not None:
        g1, g2, g3 = st.columns([1, 1, 2])
        with g1:
            st.plotly_chart(
                gauge_chart(ach_pct, title=f"{metric_label} 達成率", max_val=100, height=240),
                use_container_width=True,
            )
        with g2:
            cap = max(total_hours * 1.5, 10)
            st.plotly_chart(
                gauge_chart(min(total_hours, cap), title=f"停止時間 ({unit})",
                            max_val=cap, height=240),
                use_container_width=True,
            )
        with g3:
            if metric_prefix and not df_op.empty:
                kd = df_op[df_op["indicator_ru"].str.startswith(metric_prefix, na=False)].copy()
                kd["fact"] = pd.to_numeric(kd["fact"], errors="coerce")
                daily = kd.groupby("date")["fact"].sum().reset_index()
                daily = daily[daily["fact"] > 0]
                if not daily.empty:
                    st.markdown(
                        f'<div class="section-tag">日別 {metric_label} 推移</div>',
                        unsafe_allow_html=True,
                    )
                    fig_mini = px.bar(
                        daily, x="date", y="fact",
                        labels={"date": "日付", "fact": "実績"},
                        color_discrete_sequence=[PRIMARY],
                    )
                    fig_mini.update_traces(marker_opacity=0.85)
                    apply_chart_theme(fig_mini, height=200, margin=dict(t=5, b=5, l=5, r=5))
                    st.plotly_chart(fig_mini, use_container_width=True)

    st.divider()

    # ── タブ ──────────────────────────────────────────────────
    tab_all, tab_chart, tab_stop, tab_prod = st.tabs([
        "🗂️ 総合ビュー", "📈 概要グラフ", "⏸️ 停止データ", "📊 生産指標"
    ])

    # ════════ 総合ビュー ════════════════════════════════════════
    with tab_all:
        # ── 生産実績 ─────────────────────────────────────────
        st.markdown('<div class="section-tag">📦 生産実績</div>', unsafe_allow_html=True)
        r1a, r1b, r1c = st.columns([1, 2, 2])

        with r1a:
            if ach_pct is not None:
                st.plotly_chart(
                    gauge_chart(ach_pct, title=f"{metric_label}\n達成率",
                                max_val=100, height=220),
                    use_container_width=True,
                )
            else:
                st.info("生産データ未取込")

        with r1b:
            if metric_prefix and not df_op.empty:
                kd2 = df_op[df_op["indicator_ru"].str.startswith(metric_prefix, na=False)].copy()
                kd2["fact"] = pd.to_numeric(kd2["fact"], errors="coerce")
                daily2 = kd2.groupby("date")["fact"].sum().reset_index()
                daily2 = daily2[daily2["fact"] > 0]
                if not daily2.empty:
                    fig_d2 = px.bar(
                        daily2, x="date", y="fact",
                        labels={"date": "日付", "fact": "実績"},
                        color_discrete_sequence=[PRIMARY],
                        title=f"日別 {metric_label} 推移",
                    )
                    fig_d2.update_traces(marker_opacity=0.85)
                    apply_chart_theme(fig_d2, height=220, margin=dict(t=36, b=5, l=5, r=5))
                    st.plotly_chart(fig_d2, use_container_width=True)
            else:
                st.info("生産データ未取込")

        with r1c:
            if not df_op.empty:
                prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
                if prefixes:
                    _mask = df_op["indicator_ru"].str.startswith(prefixes[0], na=False)
                    for _p in prefixes[1:]:
                        _mask |= df_op["indicator_ru"].str.startswith(_p, na=False)
                    _kdf = df_op[_mask].dropna(subset=["fact"]).copy()
                else:
                    _kdf = df_op.dropna(subset=["fact"]).head(10).copy()
                if not _kdf.empty:
                    _kdf["表示名"] = _kdf.apply(
                        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                    )
                    _kdf["fact"] = pd.to_numeric(_kdf["fact"], errors="coerce")
                    _kdf["plan"] = pd.to_numeric(_kdf["plan"], errors="coerce")
                    _agg = (_kdf.groupby("表示名")
                            .agg(plan=("plan", "sum"), fact=("fact", "sum"))
                            .reset_index())
                    _agg = _agg[_agg["fact"] > 0].head(6)
                    if not _agg.empty:
                        st.plotly_chart(
                            plan_fact_bar(_agg, title="計画／実績", height=220),
                            use_container_width=True,
                        )

        st.divider()

        # ── 停止状況 ─────────────────────────────────────────
        st.markdown('<div class="section-tag">⏸️ 停止状況</div>', unsafe_allow_html=True)
        r2a, r2b, r2c = st.columns([2, 2, 1])

        with r2a:
            if not df_stop.empty:
                df_plot2, _, x_title2 = smart_period(df_stop, date_from, date_to)
                df_plot2["停止種類"] = df_plot2["reason"].apply(extract_stop_type)
                df_plot2["val"] = df_plot2["duration_minutes"] / divisor
                agg_s = (df_plot2.groupby(["period", "period_dt", "停止種類"])["val"]
                         .sum().reset_index().sort_values("period_dt"))
                fig_s2 = px.bar(
                    agg_s, x="period", y="val", color="停止種類", barmode="stack",
                    labels={"period": x_title2, "val": unit_label},
                    color_discrete_sequence=get_palette(),
                    category_orders={"period": agg_s["period"].unique().tolist()},
                    title="停止時間推移",
                )
                apply_chart_theme(fig_s2, height=260)
                st.plotly_chart(fig_s2, use_container_width=True)
            else:
                st.info("停止データなし")

        with r2b:
            if not df_stop.empty:
                reason_df2 = (
                    df_stop[df_stop["reason"].fillna("").str.strip() != ""]
                    .groupby("reason")["duration_minutes"].sum()
                    .sort_values(ascending=False).head(7).reset_index()
                )
                if not reason_df2.empty:
                    reason_df2["val"] = reason_df2["duration_minutes"] / divisor
                    reason_df2["label"] = reason_df2["reason"].apply(
                        lambda s: s[:24] + "…" if len(str(s)) > 25 else s
                    )
                    fig_pie2 = px.pie(
                        reason_df2, names="label", values="val",
                        color_discrete_sequence=get_palette(),
                        hole=0.4,
                        title="停止理由 内訳",
                        hover_data={"reason": True, "label": False},
                    )
                    fig_pie2.update_traces(
                        textposition="inside", textinfo="percent",
                        textfont=dict(size=10),
                        hovertemplate="<b>%{customdata[0]}</b><br>%{value:.1f} " + unit + "  (%{percent})<extra></extra>",
                    )
                    apply_chart_theme(fig_pie2, height=260,
                                      margin=dict(t=36, b=5, l=5, r=160))
                    fig_pie2.update_layout(
                        showlegend=True,
                        legend=dict(orientation="v", x=1.02, y=0.5,
                                    font=dict(size=8, color=TEXT)),
                    )
                    st.plotly_chart(fig_pie2, use_container_width=True)
                else:
                    st.info("停止理由データなし")
            else:
                st.info("停止データなし")

        with r2c:
            # 停止サマリーカード
            stop_color_val = _stop_color(total_stops)
            hour_color_val = _hour_color(total_hours)
            st.markdown(
                animated_kpi_html(f"{total_stops} 件", "停止件数",
                                  icon="⏸️", color=stop_color_val),
                unsafe_allow_html=True,
            )
            st.markdown(
                animated_kpi_html(f"{total_hours:.1f} {unit}", unit_label,
                                  icon="⏱️", color=hour_color_val),
                unsafe_allow_html=True,
            )

        st.divider()

        # ── 達成率＋エリア別 ─────────────────────────────────
        st.markdown('<div class="section-tag">📊 指標分析</div>', unsafe_allow_html=True)
        r3a, r3b = st.columns(2)

        with r3a:
            if not df_op.empty:
                prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
                if prefixes:
                    _mask2 = df_op["indicator_ru"].str.startswith(prefixes[0], na=False)
                    for _p2 in prefixes[1:]:
                        _mask2 |= df_op["indicator_ru"].str.startswith(_p2, na=False)
                    _kdf2 = df_op[_mask2].copy()
                else:
                    _kdf2 = df_op.copy()
                _kdf2["表示名"] = _kdf2.apply(
                    lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                )
                _kdf2["fact"] = pd.to_numeric(_kdf2["fact"], errors="coerce")
                _kdf2["plan"] = pd.to_numeric(_kdf2["plan"], errors="coerce")
                _ach2 = (_kdf2.groupby("表示名")
                         .agg(plan=("plan", "sum"), fact=("fact", "sum"))
                         .reset_index())
                _ach2 = _ach2[(_ach2["plan"] > 0) & (_ach2["fact"] > 0)].head(6)
                if not _ach2.empty:
                    _ach2["達成率"] = (_ach2["fact"] / _ach2["plan"] * 100).round(1)
                    st.plotly_chart(
                        achievement_bar(_ach2["表示名"].tolist(), _ach2["達成率"].tolist(),
                                        title="生産達成率（%）", height=260),
                        use_container_width=True,
                    )
                else:
                    st.info("達成率データなし")
            else:
                st.info("生産データ未取込")

        with r3b:
            if not df_stop.empty:
                area_agg2 = (df_stop.groupby("area")
                             .agg(合計分=("duration_minutes", "sum"))
                             .reset_index().sort_values("合計分", ascending=True))
                area_agg2[unit_label] = (area_agg2["合計分"] / divisor).round(1)
                area_agg2 = area_agg2.tail(8)
                fig_area2 = px.bar(
                    area_agg2, y="area", x=unit_label, orientation="h",
                    color=unit_label, color_continuous_scale="RdYlGn_r",
                    labels={"area": "エリア/設備"},
                    title="エリア別 停止時間",
                )
                apply_chart_theme(fig_area2, height=260)
                fig_area2.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig_area2, use_container_width=True)
            else:
                st.info("停止データなし")

        # ── 停止記録テーブル ──────────────────────────────────
        if not df_stop.empty:
            st.divider()
            with st.expander("📋 停止記録一覧"):
                show_s = df_stop[["date", "area", "stop_time", "recovery_time",
                                   "duration_minutes", "reason", "response"]].copy()
                show_s["duration_minutes"] = (show_s["duration_minutes"] / divisor).round(1)
                themed_table(show_s.rename(columns={
                    "date": "日付", "area": "エリア/設備", "stop_time": "停止時刻",
                    "recovery_time": "復旧時刻", "duration_minutes": unit_label,
                    "reason": "停止理由", "response": "処置内容",
                }), height=320)

    # ════════ 概要グラフ ════════════════════════════════════════
    with tab_chart:
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown('<div class="section-tag">停止時間推移</div>', unsafe_allow_html=True)
            if not df_stop.empty:
                df_plot, _, x_title = smart_period(df_stop, date_from, date_to)
                df_plot["停止種類"] = df_plot["reason"].apply(extract_stop_type)
                df_plot["val"] = df_plot["duration_minutes"] / divisor
                agg = (df_plot.groupby(["period", "period_dt", "停止種類"])["val"]
                       .sum().reset_index().sort_values("period_dt"))
                fig = px.bar(
                    agg, x="period", y="val", color="停止種類", barmode="stack",
                    labels={"period": x_title, "val": unit_label},
                    color_discrete_sequence=get_palette(),
                    category_orders={"period": agg["period"].unique().tolist()},
                )
                apply_chart_theme(fig, height=340)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("停止データがありません。")

        with col_r:
            st.markdown('<div class="section-tag">生産指標 計画／実績</div>', unsafe_allow_html=True)
            if not df_op.empty:
                prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
                if prefixes:
                    mask = df_op["indicator_ru"].str.startswith(prefixes[0], na=False)
                    for p in prefixes[1:]:
                        mask |= df_op["indicator_ru"].str.startswith(p, na=False)
                    kdf = df_op[mask].dropna(subset=["fact"]).copy()
                else:
                    kdf = df_op.dropna(subset=["fact"]).head(10).copy()

                if not kdf.empty:
                    kdf["表示名"] = kdf.apply(
                        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                    )
                    kdf["fact"] = pd.to_numeric(kdf["fact"], errors="coerce")
                    kdf["plan"] = pd.to_numeric(kdf["plan"], errors="coerce")
                    agg2 = (kdf.groupby("表示名")
                            .agg(plan=("plan", "sum"), fact=("fact", "sum"))
                            .reset_index())
                    agg2 = agg2[agg2["fact"] > 0].head(8)
                    if not agg2.empty:
                        st.plotly_chart(plan_fact_bar(agg2, title="", height=340),
                                        use_container_width=True)
                    else:
                        st.info("生産指標データがありません。")
                else:
                    st.info("生産指標データがありません。")
            else:
                st.info("1C日報が未取込です。「データ取込」からインポートしてください。")

        st.divider()
        col_p, col_q = st.columns(2)

        with col_p:
            st.markdown('<div class="section-tag">停止理由 内訳</div>', unsafe_allow_html=True)
            if not df_stop.empty:
                reason_df = (
                    df_stop[df_stop["reason"].fillna("").str.strip() != ""]
                    .groupby("reason")["duration_minutes"].sum()
                    .sort_values(ascending=False).head(8).reset_index()
                )
                if not reason_df.empty:
                    reason_df["val"] = reason_df["duration_minutes"] / divisor
                    reason_df["label"] = reason_df["reason"].apply(
                        lambda s: s[:24] + "…" if len(str(s)) > 25 else s
                    )
                    fig_p = px.pie(
                        reason_df, names="label", values="val",
                        color_discrete_sequence=get_palette(),
                        hole=0.38,
                        hover_data={"reason": True, "label": False},
                    )
                    fig_p.update_traces(
                        textposition="inside", textinfo="percent",
                        textfont=dict(size=11),
                        hovertemplate="<b>%{customdata[0]}</b><br>%{value:.1f} " + unit + "  (%{percent})<extra></extra>",
                    )
                    apply_chart_theme(fig_p, height=320, margin=dict(t=10, b=10, l=10, r=160))
                    fig_p.update_layout(
                        showlegend=True,
                        legend=dict(
                            orientation="v", x=1.02, y=0.5,
                            font=dict(size=9, color=TEXT),
                        ),
                    )
                    st.plotly_chart(fig_p, use_container_width=True)
                else:
                    st.info("停止理由データがありません。")
            else:
                st.info("停止データがありません。")

        with col_q:
            st.markdown('<div class="section-tag">生産達成率（%）</div>', unsafe_allow_html=True)
            if not df_op.empty:
                prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
                if prefixes:
                    mask = df_op["indicator_ru"].str.startswith(prefixes[0], na=False)
                    for p in prefixes[1:]:
                        mask |= df_op["indicator_ru"].str.startswith(p, na=False)
                    kdf2 = df_op[mask].copy()
                else:
                    kdf2 = df_op.copy()

                if not kdf2.empty:
                    kdf2["表示名"] = kdf2.apply(
                        lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                    )
                    kdf2["fact"] = pd.to_numeric(kdf2["fact"], errors="coerce")
                    kdf2["plan"] = pd.to_numeric(kdf2["plan"], errors="coerce")
                    ach = (kdf2.groupby("表示名")
                           .agg(plan=("plan", "sum"), fact=("fact", "sum"))
                           .reset_index())
                    ach = ach[(ach["plan"] > 0) & (ach["fact"] > 0)].head(8)
                    if not ach.empty:
                        ach["達成率"] = (ach["fact"] / ach["plan"] * 100).round(1)
                        st.plotly_chart(
                            achievement_bar(
                                ach["表示名"].tolist(), ach["達成率"].tolist(),
                                title="指標別 達成率", height=320,
                            ),
                            use_container_width=True,
                        )
                    else:
                        st.info("達成率を計算できるデータがありません。")
                else:
                    st.info("生産指標データがありません。")
            else:
                st.info("1C日報が未取込です。")

    # ════════ 停止データ ════════════════════════════════════════
    with tab_stop:
        if df_stop.empty:
            st.info("停止データがありません。")
        else:
            _today = _date.today()
            st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
            st.plotly_chart(
                calendar_heatmap(df_stop, _today.year, _today.month, f"{factory} 停止カレンダー"),
                use_container_width=True,
            )

            st.divider()
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown('<div class="section-tag">エリア別 停止時間 TOP10</div>', unsafe_allow_html=True)
                area_agg = (df_stop.groupby("area")
                            .agg(件数=("id", "count"), 合計分=("duration_minutes", "sum"))
                            .reset_index().sort_values("合計分", ascending=True))
                area_agg[f"合計({unit})"] = (area_agg["合計分"] / divisor).round(1)
                area_agg = area_agg.tail(10)
                fig_area = px.bar(
                    area_agg, y="area", x=f"合計({unit})", orientation="h",
                    color=f"合計({unit})", color_continuous_scale="RdYlGn_r",
                    labels={"area": "エリア/設備", f"合計({unit})": unit_label},
                )
                apply_chart_theme(fig_area, height=340)
                fig_area.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig_area, use_container_width=True)

            with col_b:
                st.markdown('<div class="section-tag">理由別 件数・時間ランキング</div>', unsafe_allow_html=True)
                cnt_agg = (
                    df_stop[df_stop["reason"].fillna("").str.strip() != ""]
                    .groupby("reason")
                    .agg(件数=("id", "count"), 合計分=("duration_minutes", "sum"))
                    .reset_index()
                    .sort_values("合計分", ascending=False)
                    .head(10)
                )
                cnt_agg[f"合計({unit})"] = (cnt_agg["合計分"] / divisor).round(1)
                themed_table(
                    cnt_agg[["reason", "件数", f"合計({unit})"]].rename(
                        columns={"reason": "停止理由"}
                    ),
                    height=340,
                )

            st.divider()
            st.markdown('<div class="section-tag">停止記録一覧</div>', unsafe_allow_html=True)
            show = df_stop[["date", "area", "stop_time", "recovery_time",
                             "duration_minutes", "reason", "response"]].copy()
            show["duration_minutes"] = (show["duration_minutes"] / divisor).round(1)
            themed_table(show.rename(columns={
                "date": "日付", "area": "エリア/設備", "stop_time": "停止時刻",
                "recovery_time": "復旧時刻", "duration_minutes": unit_label,
                "reason": "停止理由", "response": "処置内容",
            }), height=400)

    # ════════ 生産指標 ══════════════════════════════════════════
    with tab_prod:
        if df_op.empty:
            st.info("1C日報が未取込です。「データ取込」からインポートしてください。")
        else:
            prefixes = KEY_INDICATOR_PREFIXES.get(factory, [])
            if prefixes:
                mask = df_op["indicator_ru"].str.startswith(prefixes[0], na=False)
                for p in prefixes[1:]:
                    mask |= df_op["indicator_ru"].str.startswith(p, na=False)
                trend_kdf = df_op[mask].copy()
            else:
                trend_kdf = df_op.copy()

            if not trend_kdf.empty:
                trend_kdf["表示名"] = trend_kdf.apply(
                    lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]), axis=1
                )
                trend_kdf["fact"] = pd.to_numeric(trend_kdf["fact"], errors="coerce")
                trend_agg = (trend_kdf.groupby(["date", "表示名"])
                             .agg(fact=("fact", "sum")).reset_index())
                trend_agg = trend_agg[trend_agg["fact"] > 0]
                if not trend_agg.empty:
                    st.markdown('<div class="section-tag">日別 生産実績トレンド</div>', unsafe_allow_html=True)
                    fig_tr = px.line(
                        trend_agg, x="date", y="fact", color="表示名",
                        markers=True,
                        color_discrete_sequence=get_palette(),
                        labels={"date": "日付", "fact": "実績"},
                    )
                    fig_tr.update_traces(line_width=2.5, marker_size=7)
                    apply_chart_theme(fig_tr, height=320)
                    st.plotly_chart(fig_tr, use_container_width=True)

            st.divider()
            kw = st.text_input("指標検索", key=f"fv_kw_{factory}",
                               placeholder="日本語またはロシア語でキーワード検索")
            show_op = df_op.copy()
            if kw:
                show_op = show_op[
                    show_op["indicator_ru"].fillna("").str.contains(kw, case=False) |
                    show_op["indicator_jp"].fillna("").str.contains(kw, case=False)
                ]
            show_op = show_op.copy()
            show_op["fact"] = pd.to_numeric(show_op["fact"], errors="coerce")
            show_op["plan"] = pd.to_numeric(show_op["plan"], errors="coerce")
            show_op["達成率(%)"] = (
                (show_op["fact"] / show_op["plan"] * 100)
                .round(1)
                .where(show_op["plan"] > 0)
            )
            show_op["指標"] = show_op.apply(
                lambda r: fix_indicator_name(r["indicator_ru"], r["indicator_jp"]),
                axis=1,
            )
            show_op["unit"] = show_op["unit"].apply(translate_unit)
            themed_table(
                show_op[["date", "指標", "unit", "plan", "fact", "達成率(%)"]].rename(columns={
                    "date": "日付", "指標": "指標", "unit": "単位",
                    "plan": "計画", "fact": "実績", "達成率(%)": "達成率(%)",
                }),
                height=420,
            )
