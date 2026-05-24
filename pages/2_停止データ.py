import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from datetime import date as _date
from utils.data_store import (
    get_stoppages, delete_stoppage,
    delete_stoppages_bulk, preview_delete_stoppages,
)
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import (
    themed_table,
    page_setup,
    apply_chart_theme,
    jp_date_input, unit_radio, extract_stop_type, smart_period,
    COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_GOOD, PALETTE_MAIN,
    calendar_heatmap, get_palette,
)

st.set_page_config(page_title="停止データ", page_icon="⏸️", layout="wide")
page_setup()
st.title("⏸️ 停止データ")

# ── フィルター ───────────────────────────────────────────────
with st.expander("🔍 フィルター", expanded=True):
    c1, c2, c3, c4, c5 = st.columns([2, 3, 3, 2, 1])
    sel_factory = c1.selectbox("工場", ["全工場"] + TARGET_FACTORIES, key="sf")
    with c2:
        date_from = jp_date_input("開始日", date.today().replace(day=1), "sdf")
    with c3:
        date_to = jp_date_input("終了日", date.today(), "sdt")
    keyword = c4.text_input("エリア/設備（キーワード）", key="sk")
    with c5:
        unit, divisor = unit_radio(horizontal=False)

unit_label = f"停止時間({unit})"
factory_filter = "" if sel_factory == "全工場" else sel_factory
df = get_stoppages(factory_filter, str(date_from), str(date_to))

if keyword:
    df = df[df["area"].fillna("").str.contains(keyword, case=False, na=False)]

# ── CSV ダウンロード ──────────────────────────────────────────
col_dl, col_info = st.columns([1, 4])
col_info.caption(f"検索結果: {len(df)} 件")
if not df.empty:
    col_labels_dl = {
        "date": "日付", "factory": "工場", "area": "エリア/設備",
        "stop_time": "停止時刻", "recovery_time": "復旧時刻",
        "duration_minutes": "停止時間(分)", "reason": "停止理由",
        "response": "処置内容", "notes": "備考",
    }
    col_dl.download_button(
        "📥 CSV出力",
        df.rename(columns=col_labels_dl).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="stoppage_data.csv", mime="text/csv",
    )

st.divider()

# ── サマリー指標 ─────────────────────────────────────────────
if not df.empty:
    m1, m2, m3, m4 = st.columns(4)
    total_min = df["duration_minutes"].sum()
    avg_min   = df["duration_minutes"].mean()
    max_min   = df["duration_minutes"].max()
    m1.metric("停止件数",   f"{len(df)} 件")
    m2.metric("総停止時間", f"{total_min/divisor:.1f} {unit}")
    m3.metric("平均停止時間", f"{avg_min/divisor:.1f} {unit}")
    m4.metric("最長停止",   f"{max_min/divisor:.1f} {unit}" if pd.notna(max_min) else "－")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📊 停止種類別時間", "🥧 停止理由", "📈 推移"])

    with tab1:
        df_plot, _, x_title = smart_period(df, date_from, date_to)
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
        apply_chart_theme(fig, height=320, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

        # カレンダーヒートマップ（今月）
        _today = _date.today()
        st.markdown('<div class="section-tag">停止カレンダー（今月）</div>', unsafe_allow_html=True)
        st.plotly_chart(
            calendar_heatmap(df, _today.year, _today.month),
            use_container_width=True,
        )

    with tab2:
        reason_df = (
            df[df["reason"].str.strip().ne("")]
            .groupby("reason")["duration_minutes"].sum()
            .sort_values(ascending=False).head(10).reset_index()
        ) if df["reason"].notna().any() else pd.DataFrame()
        if not reason_df.empty:
            reason_df["val"] = reason_df["duration_minutes"] / divisor
            fig2 = px.pie(
                reason_df, names="reason", values="val",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig2.update_traces(hovertemplate="%{label}<br>%{value:.1f} " + unit + "<extra></extra>")
            apply_chart_theme(fig2, height=320, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("停止理由データがありません。")

    with tab3:
        import numpy as np
        df_plot2, _, x_title2 = smart_period(df, date_from, date_to)
        df_plot2["val"] = df_plot2["duration_minutes"] / divisor
        daily = df_plot2.groupby(["period", "period_dt"])["val"].sum().reset_index().sort_values("period_dt")
        fig3 = px.line(
            daily, x="period", y="val",
            labels={"period": x_title2, "val": unit_label},
            markers=True,
            category_orders={"period": daily["period"].unique().tolist()},
        )
        # トレンドライン
        if len(daily) >= 3:
            x_idx = list(range(len(daily)))
            z = np.polyfit(x_idx, daily["val"].values, 1)
            trend_y = np.poly1d(z)(x_idx)
            fig3.add_scatter(
                x=daily["period"], y=trend_y,
                mode="lines", name="トレンド",
                line=dict(color="#E15759", width=2, dash="dot"),
            )
        apply_chart_theme(fig3, height=300, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig3, use_container_width=True)

    st.divider()

# ── ドリルダウン（工場→エリア→設備） ─────────────────────────
if not df.empty:
    st.markdown('<div class="section-tag">🔍 ドリルダウン分析</div>', unsafe_allow_html=True)
    dd1, dd2 = st.columns(2)

    with dd1:
        # 工場別集計
        fac_drill = (
            df.groupby("factory")
            .agg(件数=("id", "count"), 停止時間=("duration_minutes", "sum"))
            .reset_index().sort_values("停止時間", ascending=False)
        )
        fac_drill["停止時間"] = (fac_drill["停止時間"] / divisor).round(1)
        fig_d1 = px.bar(
            fac_drill, x="factory", y="停止時間",
            color="停止時間", color_continuous_scale=[[0,"#4E79A7"],[1,"#E15759"]],
            text="停止時間",
            labels={"factory": "工場", "停止時間": unit_label},
            title="工場別 停止時間",
        )
        fig_d1.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
        fig_d1.update_layout(coloraxis_showscale=False)
        apply_chart_theme(fig_d1, height=260, margin=dict(t=40, b=10, l=10, r=10))
        st.plotly_chart(fig_d1, use_container_width=True)

        # 工場クリックでエリア絞り込み
        sel_fac_dd = st.selectbox(
            "▼ 工場を選んでエリアを表示",
            ["（全工場）"] + fac_drill["factory"].tolist(), key="dd_fac",
        )

    with dd2:
        # エリア別集計（選択工場でフィルター）
        df_area = df.copy()
        if sel_fac_dd != "（全工場）":
            df_area = df_area[df_area["factory"] == sel_fac_dd]

        area_drill = (
            df_area[df_area["area"].fillna("").str.strip() != ""]
            .groupby("area")
            .agg(件数=("id", "count"), 停止時間=("duration_minutes", "sum"))
            .reset_index().sort_values("停止時間", ascending=False).head(12)
        )
        area_drill["停止時間"] = (area_drill["停止時間"] / divisor).round(1)
        fac_title = sel_fac_dd if sel_fac_dd != "（全工場）" else "全工場"
        if not area_drill.empty:
            fig_d2 = px.bar(
                area_drill, y="area", x="停止時間", orientation="h",
                color="停止時間", color_continuous_scale=[[0,"#76B7B2"],[1,"#E15759"]],
                text="停止時間",
                labels={"area": "エリア/設備", "停止時間": unit_label},
                title=f"{fac_title} ― エリア別 TOP12",
            )
            fig_d2.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
            fig_d2.update_layout(coloraxis_showscale=False)
            apply_chart_theme(fig_d2, height=260, margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(fig_d2, use_container_width=True)
        else:
            st.info("エリアデータがありません。")

    # エリア→設備レベル（選択工場のエリア詳細テーブル）
    if not area_drill.empty:
        sel_area = st.selectbox(
            "▼ エリアを選んで詳細を表示",
            ["（全エリア）"] + area_drill["area"].tolist(), key="dd_area",
        )
        df_detail = df_area.copy()
        if sel_area != "（全エリア）":
            df_detail = df_detail[df_detail["area"] == sel_area]
        df_detail = df_detail.copy()
        df_detail["停止時間"] = (df_detail["duration_minutes"] / divisor).round(1)
        themed_table(df_detail[["date", "factory", "area", "停止時間", "reason", "response"]] .rename(columns={"date":"日付","factory":"工場","area":"エリア/設備", "reason":"停止理由","response":"処置内容"}) .sort_values("停止時間", ascending=False), height=220)

st.divider()

# ── データテーブル ───────────────────────────────────────────
st.markdown('<div class="section-tag">停止データ一覧</div>', unsafe_allow_html=True)
if df.empty:
    st.info("該当データがありません。「データ取込」からExcelをインポートしてください。")
else:
    display_cols = ["date", "factory", "area", "stop_time", "recovery_time",
                    "duration_minutes", "reason", "response", "notes"]
    col_labels = {
        "date": "日付", "factory": "工場", "area": "エリア/設備",
        "stop_time": "停止時刻", "recovery_time": "復旧時刻",
        "duration_minutes": unit_label, "reason": "停止理由",
        "response": "処置内容", "notes": "備考",
    }
    show = df[display_cols].copy()
    show["duration_minutes"] = (show["duration_minutes"] / divisor).round(1)
    themed_table(show.rename(columns=col_labels), height=450)

    # ── 削除 ────────────────────────────────────────────────────
    with st.expander("🗑️ データを削除"):
        tab_bulk, tab_single = st.tabs(["一括削除（工場・期間指定）", "個別削除（ID指定）"])

        with tab_bulk:
            bc1, bc2, bc3 = st.columns(3)
            del_factory = bc1.selectbox("工場", [""] + TARGET_FACTORIES,
                                        format_func=lambda v: "すべての工場" if v == "" else v,
                                        key="del_fac")
            with bc2:
                del_date_from = jp_date_input("開始日", date.today().replace(day=1), "del_from")
            with bc3:
                del_date_to = jp_date_input("終了日", date.today(), "del_to")

            df_from_str = str(del_date_from)
            df_to_str   = str(del_date_to)

            if st.button("🔍 削除対象を確認", key="del_preview"):
                preview = preview_delete_stoppages(del_factory, df_from_str, df_to_str)
                if preview.empty:
                    st.info("該当するデータがありません。")
                else:
                    st.warning(f"**{len(preview)} 件**が削除対象です。")
                    show_cols = ["date", "factory", "area", "duration_minutes", "reason"]
                    lbl = {"date": "日付", "factory": "工場", "area": "エリア/設備",
                           "duration_minutes": "停止時間(分)", "reason": "停止理由"}
                    themed_table(preview[show_cols].rename(columns=lbl), height=280)
                    st.session_state["_del_ready"] = True
                    st.session_state["_del_count"] = len(preview)

            if st.session_state.get("_del_ready"):
                cnt = st.session_state.get("_del_count", 0)
                if st.button(f"⚠️  {cnt} 件を削除する（取り消し不可）", type="primary", key="del_exec"):
                    deleted = delete_stoppages_bulk(del_factory, df_from_str, df_to_str)
                    st.success(f"✅  {deleted} 件を削除しました。")
                    st.session_state.pop("_del_ready", None)
                    st.session_state.pop("_del_count", None)
                    st.rerun()

        with tab_single:
            st.caption("IDで1件だけ削除する場合はこちら（IDは下の詳細テーブルで確認）")
            del_id = st.text_input("レコードID", key="del_id_input")
            if st.button("削除実行", type="secondary", key="del_single"):
                if del_id.strip():
                    delete_stoppage(del_id.strip())
                    st.success(f"ID: {del_id} を削除しました。")
                    st.rerun()
                else:
                    st.warning("IDを入力してください。")

    with st.expander("📋 詳細（ID含む全列表示）"):
        themed_table(df)
