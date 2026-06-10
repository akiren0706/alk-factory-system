import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils.data_store import get_operative
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme,
    jp_date_input, plan_fact_bar, achievement_bar,
    COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_GOOD, PALETTE_MAIN, get_palette, jst_today
)
from utils.operative_parser import KEY_INDICATOR_PREFIXES

st.set_page_config(page_title="生産データ", page_icon="📦", layout="wide")
page_setup()
st.title("📦 生産データ")

# ── フィルター ───────────────────────────────────────────────
with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    sel_factory = c1.selectbox("工場", ["全工場"] + TARGET_FACTORIES, key="pf")
    with c2:
        date_from = jp_date_input("開始日", jst_today().replace(day=1), "pdf")
    with c3:
        date_to = jp_date_input("終了日", jst_today(), "pdt")

factory_filter = "" if sel_factory == "全工場" else sel_factory

if st.button("🔄 データ更新", key="pd_refresh"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("データを読み込み中（初回・年変更時は20〜30秒かかります）..."):
    df_op   = get_operative(factory_filter, str(date_from), str(date_to))

# ── KPI ───────────────────────────────────────────────────────
st.divider()
k1, k2, k3 = st.columns(3)
op_days  = df_op["date"].nunique() if not df_op.empty else 0
op_facs  = df_op["factory"].nunique() if not df_op.empty else 0
k1.metric("1Cデータ取込日数",  f"{op_days} 日分")
k2.metric("工場数",            f"{op_facs} 工場")
k3.metric("指標レコード数",    f"{len(df_op)} 件")

st.divider()

# ── 1C 生産実績（メイン） ─────────────────────────────────────
st.markdown('<div class="section-tag">1C 生産実績</div>', unsafe_allow_html=True)

if df_op.empty:
    st.info("データがありません。「データ取込」から1C日報ファイルをインポートしてください。")
else:
    # ─ 全工場サマリーグラフ（タブ上部） ──────────────────────
    st.markdown('<div class="section-tag">全工場サマリー</div>', unsafe_allow_html=True)
    summary_rows = []
    for fac in TARGET_FACTORIES:
        df_f = df_op[df_op["factory"] == fac]
        if df_f.empty:
            continue
        for p in KEY_INDICATOR_PREFIXES.get(fac, [])[:1]:
            m = df_f[df_f["indicator_ru"].str.startswith(p, na=False)]
            if not m.empty:
                fact = pd.to_numeric(m["fact"], errors="coerce").sum()
                plan = pd.to_numeric(m["plan"], errors="coerce").sum()
                summary_rows.append({
                    "工場": fac,
                    "表示名": fac,
                    "指標": m.iloc[0]["indicator_jp"] or p[:20],
                    "単位": m.iloc[0]["unit"],
                    "plan": plan, "fact": fact,
                    "達成率": fact / plan * 100 if plan > 0 else None,
                })
                break

    if summary_rows:
        sg1, sg2, sg3 = st.columns(3)
        sdf = pd.DataFrame(summary_rows)

        with sg1:
            st.plotly_chart(
                plan_fact_bar(sdf[["表示名", "plan", "fact"]].rename(columns={"表示名": "表示名"}),
                              title="計画／実績（工場別）", height=280),
                use_container_width=True,
            )
        with sg2:
            ach_labels = sdf[sdf["達成率"].notna()]["工場"].tolist()
            ach_vals   = sdf[sdf["達成率"].notna()]["達成率"].tolist()
            if ach_labels:
                st.plotly_chart(
                    achievement_bar(ach_labels, ach_vals, title="工場別 達成率（%）", height=280),
                    use_container_width=True,
                )
        with sg3:
            # 期間に応じて日別 / 月別を自動切り替え
            _days = (date_to - date_from).days
            _use_daily = _days <= 62
            trend_rows = []
            for _, r in sdf.iterrows():
                fac = r["工場"]
                df_f2 = df_op[df_op["factory"] == fac]
                for p in KEY_INDICATOR_PREFIXES.get(fac, [])[:1]:
                    m2 = df_f2[df_f2["indicator_ru"].str.startswith(p, na=False)]
                    if not m2.empty:
                        m2 = m2.copy()
                        m2["fact"] = pd.to_numeric(m2["fact"], errors="coerce")
                        if _use_daily:
                            for _, row in m2.groupby("date").agg(fact=("fact", "sum")).reset_index().iterrows():
                                trend_rows.append({"期間": row["date"], "工場": fac, "実績": row["fact"]})
                        else:
                            m2["期間"] = pd.to_datetime(m2["date"], errors="coerce").dt.strftime("%Y年%m月")
                            for _, row in m2.groupby("期間").agg(fact=("fact", "sum")).reset_index().iterrows():
                                trend_rows.append({"期間": row["期間"], "工場": fac, "実績": row["fact"]})
                    break
            if trend_rows:
                tdf = pd.DataFrame(trend_rows).dropna(subset=["実績"])
                _title = "日別 生産トレンド" if _use_daily else "月別 生産トレンド"
                fig_t = px.line(
                    tdf, x="期間", y="実績", color="工場", markers=True,
                    color_discrete_sequence=get_palette(),
                    labels={"期間": "日付" if _use_daily else "月", "実績": "実績（主要指標）"},
                    title=_title,
                )
                fig_t.update_traces(line_width=2, marker_size=6)
                apply_chart_theme(fig_t, height=280)
                st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    # ─ 工場別タブ ─────────────────────────────────────────────
    facs_in_data = [f for f in TARGET_FACTORIES if f in df_op["factory"].values]
    tab_labels = facs_in_data if facs_in_data else ["（データなし）"]
    tabs = st.tabs(tab_labels)

    for i, fac in enumerate(facs_in_data):
        with tabs[i]:
            df_f = df_op[df_op["factory"] == fac].copy()
            prefixes = KEY_INDICATOR_PREFIXES.get(fac, [])

            if prefixes:
                mask = pd.Series(False, index=df_f.index)
                for p in prefixes:
                    mask |= df_f["indicator_ru"].str.startswith(p, na=False)
                kdf = df_f[mask].copy()
            else:
                kdf = df_f.copy()

            if kdf.empty:
                st.info(f"{fac} の生産指標データがありません。")
                continue

            # 期間に応じて日別 / 月別を自動切り替え
            _tab_days = (date_to - date_from).days
            _tab_daily = _tab_days <= 62
            if _tab_daily:
                kdf["期間"] = kdf["date"].astype(str)
                _x_label = "日付"
                _bar_title = "日別 生産実績推移"
            else:
                kdf["期間"] = pd.to_datetime(kdf["date"], errors="coerce").dt.strftime("%Y年%m月")
                _x_label = "月"
                _bar_title = "月別 生産実績推移"

            kdf["表示名"] = kdf.apply(
                lambda r: r["indicator_jp"] if r["indicator_jp"] else r["indicator_ru"][:30], axis=1
            )
            kdf["fact"] = pd.to_numeric(kdf["fact"], errors="coerce")
            kdf["plan"] = pd.to_numeric(kdf["plan"], errors="coerce")

            col_a, col_b, col_c = st.columns(3)

            # 日別 or 月別 実績推移
            with col_a:
                agg = kdf.groupby(["期間", "表示名"]).agg(fact=("fact", "sum")).reset_index()
                agg = agg[agg["fact"].notna() & (agg["fact"] != 0)]
                if not agg.empty:
                    fig = px.bar(
                        agg, x="期間", y="fact", color="表示名",
                        title=_bar_title,
                        labels={"fact": "実績", "期間": _x_label},
                        color_discrete_sequence=get_palette(),
                    )
                    apply_chart_theme(fig, height=280)
                    fig.update_layout(legend=dict(font=dict(size=10)))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("実績データがありません。")

            # 計画／実績
            with col_b:
                agg2 = kdf.groupby("表示名").agg(plan=("plan", "sum"), fact=("fact", "sum")).reset_index()
                agg2 = agg2[agg2["fact"].notna() & (agg2["fact"] != 0)].head(8)
                if not agg2.empty:
                    st.plotly_chart(
                        plan_fact_bar(agg2, title="計画／実績（期間合計）", height=280),
                        use_container_width=True,
                    )
                else:
                    st.info("計画／実績データがありません。")

            # 達成率
            with col_c:
                ach = kdf.groupby("表示名").agg(plan=("plan", "sum"), fact=("fact", "sum")).reset_index()
                ach = ach[(ach["plan"] > 0) & (ach["fact"] > 0)].head(8)
                if not ach.empty:
                    ach["達成率"] = (ach["fact"] / ach["plan"] * 100).round(1)
                    st.plotly_chart(
                        achievement_bar(
                            ach["表示名"].tolist(),
                            ach["達成率"].tolist(),
                            title="達成率（%）",
                            height=280,
                        ),
                        use_container_width=True,
                    )
                else:
                    st.info("達成率データがありません。")

            # 日別トレンド（折れ線）
            daily = kdf.groupby(["date", "表示名"]).agg(fact=("fact", "sum")).reset_index()
            daily = daily[daily["fact"] > 0]
            if not daily.empty:
                fig_d = px.line(
                    daily, x="date", y="fact", color="表示名", markers=True,
                    color_discrete_sequence=get_palette(),
                    labels={"date": "日付", "fact": "実績"},
                    title="日別 生産実績トレンド",
                )
                apply_chart_theme(fig_d, height=260)
                st.plotly_chart(fig_d, use_container_width=True)

            # 詳細テーブル
            with st.expander("📋 詳細データ"):
                show = df_f[["date", "indicator_jp", "indicator_ru", "unit", "plan", "fact"]].copy()
                show.columns = ["日付", "指標(日)", "指標(露)", "単位", "計画", "実績"]
                themed_table(show, height=300)

    st.divider()

    # ─ 全データ一覧 ───────────────────────────────────────────
    with st.expander("📋 全データ一覧（検索・フィルター可）"):
        kw = st.text_input("キーワード検索", placeholder="指標名・工場名で絞り込み", key="prod_kw")
        show_all = df_op.copy()
        if kw:
            show_all = show_all[
                show_all["factory"].str.contains(kw, case=False, na=False) |
                show_all["indicator_jp"].str.contains(kw, case=False, na=False) |
                show_all["indicator_ru"].str.contains(kw, case=False, na=False)
            ]
        show_all["fact_n"] = pd.to_numeric(show_all["fact"], errors="coerce")
        show_all["plan_n"] = pd.to_numeric(show_all["plan"], errors="coerce")
        show_all["達成率(%)"] = (show_all["fact_n"] / show_all["plan_n"] * 100).round(1)
        show_all = show_all[["date", "factory", "indicator_jp", "unit", "plan", "fact", "達成率(%)"]].copy()
        show_all.columns = ["日付", "工場", "指標", "単位", "計画", "実績", "達成率(%)"]
        themed_table(show_all, height=400)
        csv = show_all.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("📥 CSV出力", csv, file_name="production_operative.csv", mime="text/csv")

