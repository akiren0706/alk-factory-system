import streamlit as st
import pandas as pd
from datetime import date, timedelta
from utils.data_store import get_operative
from utils.master_data import TARGET_FACTORIES
from utils.ui_helpers import page_setup, factory_status_cards_html, themed_table, COLOR_ERR, COLOR_WARN, COLOR_OK

st.set_page_config(page_title="アラート", page_icon="🚨", layout="wide")
page_setup()
st.title("🚨 データ取込アラート")
st.caption("直近の日付で取込が完了していない工場を一覧表示します")

# ── 設定 ─────────────────────────────────────────────────────
ALL_FACTORIES = TARGET_FACTORIES + ["土場", "製品在庫"]
sel_factories = st.sidebar.multiselect(
    "対象工場", ALL_FACTORIES, default=ALL_FACTORIES
)

# ── データ取得 ────────────────────────────────────────────────
today     = date.today()
date_from = date(2025, 1, 1)   # 2025年1月1日から全件チェック
df_all = get_operative("", str(date_from), str(today))

# ── 期待される日付リスト ──────────────────────────────────────
total_days = (today - date_from).days + 1
expected_dates = [date_from + timedelta(days=i) for i in range(total_days)]
expected_strs  = [str(d) for d in expected_dates]

# ── 工場×日付の取込状況マトリクスを作成 ──────────────────────
if df_all.empty:
    imported_set = set()
else:
    imported_set = set(
        f"{r.factory}|{r.date}" for r in df_all.itertuples()
    )

rows = []
for fac in sel_factories:
    for d in expected_strs:
        key = f"{fac}|{d}"
        rows.append({
            "工場": fac,
            "日付": d,
            "取込": key in imported_set,
        })

matrix = pd.DataFrame(rows)

# ── サマリー KPI ─────────────────────────────────────────────
missing = matrix[~matrix["取込"]]
ok      = matrix[ matrix["取込"]]

today_str     = str(today)
yesterday_str = str(today - timedelta(days=1))

miss_today = missing[missing["日付"] == today_str]
miss_yest  = missing[missing["日付"] == yesterday_str]

k1, k2, k3, k4 = st.columns(4)
k1.metric("未取込（直近全体）",   f"{len(missing)} 件",
          delta=f"-{len(missing)}" if len(missing) else None,
          delta_color="inverse" if len(missing) else "off")
k2.metric("取込済み",             f"{len(ok)} 件")
k3.metric("本日 未取込工場数",    f"{len(miss_today)} 工場",
          delta=f"-{len(miss_today)}" if len(miss_today) else None,
          delta_color="inverse" if len(miss_today) else "off")
k4.metric("昨日 未取込工場数",    f"{len(miss_yest)} 工場",
          delta=f"-{len(miss_yest)}" if len(miss_yest) else None,
          delta_color="inverse" if len(miss_yest) else "off")

st.divider()

# ── 今日・昨日のアラート ──────────────────────────────────────
if not miss_today.empty:
    facs = "、".join(miss_today["工場"].tolist())
    st.error(f"**本日（{today_str}）** のデータが未取込です：{facs}")
else:
    st.success(f"本日（{today_str}）の全工場データ取込済み")

if not miss_yest.empty:
    facs = "、".join(miss_yest["工場"].tolist())
    st.warning(f"**昨日（{yesterday_str}）** のデータが未取込の工場があります：{facs}")
else:
    st.success(f"昨日（{yesterday_str}）の全工場データ取込済み")

st.divider()

# ── 工場別 最終取込日 ─────────────────────────────────────────
st.subheader("工場別 最終取込日")
last_rows = []
for fac in sel_factories:
    df_f = df_all[df_all["factory"] == fac] if not df_all.empty else pd.DataFrame()
    if df_f.empty:
        last_date = "未取込"
        days_ago  = "－"
        status    = "❌"
    else:
        last_d  = df_f["date"].max()
        last_date = last_d
        delta   = (today - date.fromisoformat(last_d)).days
        days_ago = f"{delta} 日前" if delta > 0 else "今日"
        if delta == 0:
            status = "✅"
        elif delta == 1:
            status = "🟡"
        else:
            status = "🔴"
    last_rows.append({
        "状態": status,
        "工場": fac,
        "最終取込日": last_date,
        "経過": days_ago,
    })

# 工場別ステータスカードを最終取込日テーブルの前に表示
fac_cards = []
for row in last_rows:
    card_status = {"✅": "ok", "🟡": "warn", "🔴": "err"}.get(row["状態"], "none")
    fac_cards.append({
        "name": row["工場"], "icon": "", "status": card_status,
        "value": row["最終取込日"], "unit": "",
        "note": row["経過"],
    })
st.markdown(factory_status_cards_html(fac_cards, cols=min(4, len(fac_cards))), unsafe_allow_html=True)

themed_table(pd.DataFrame(last_rows))

st.divider()

# ── 未取込日付 一覧 ───────────────────────────────────────────
st.subheader("未取込の日付一覧")

if missing.empty:
    st.success("2025年1月1日以降の取込は全て完了しています。")
else:
    # 日付ごとに未取込工場を集約
    agg = (
        missing.groupby("日付")["工場"]
        .apply(lambda x: "、".join(sorted(x)))
        .reset_index()
        .rename(columns={"工場": "未取込工場"})
        .sort_values("日付", ascending=False)
    )
    agg["重要度"] = agg["日付"].apply(
        lambda d: "🔴 本日" if d == today_str
        else ("🟡 昨日" if d == yesterday_str else "⚪ 過去")
    )
    agg = agg[["重要度", "日付", "未取込工場"]]
    themed_table(agg, height=400)

st.divider()

# ── ヒートマップ（工場×日付） ─────────────────────────────────
st.subheader("取込状況カレンダー（直近30日）")
recent_dates = [str(today - timedelta(days=i)) for i in range(30, -1, -1)]
heat = matrix[matrix["日付"].isin(recent_dates)].copy()
pivot = heat.pivot(index="工場", columns="日付", values="取込")

# 表示用: ✅ / ❌
display = pivot.map(lambda v: "✅" if v else "❌")
# 列名を "YYYY-MM-DD" → "MM/DD" に短縮（視認性向上）
display.columns = [c[5:].replace("-", "/") for c in display.columns]
display.index.name = "工場"
themed_table(display, hide_index=False)
