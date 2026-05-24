"""
全ページ共通UIヘルパー — ライトモード専用（木材ビジネステーマ）
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import math
from datetime import date
import plotly.graph_objects as go
import plotly.express as px


# ════════════════════════════════════════════════════════════
#  カラー定数（ライトモード固定）
# ════════════════════════════════════════════════════════════
PRIMARY     = "#4A8C72"   # ソフトグリーン（薄め）
SECONDARY   = "#62A98A"   # ライトグリーン
ACCENT      = "#8B5E3C"   # 木材ブラウン
COLOR_WARN  = "#C97D0A"   # 琥珀
COLOR_ERR   = "#B83C2B"   # 赤
COLOR_OK    = SECONDARY
COLOR_GOOD  = PRIMARY
BG          = "#F5F0E8"   # クリーム
CARD        = "#FFFFFF"
BORDER      = "#DDD5C0"
TEXT        = "#333333"
TEXT_SUB    = "#7A6A56"
SIDEBAR_BG  = "#EDE8DC"

# 後方互換
COLOR_PRIMARY = PRIMARY
COLOR_NEUTRAL = "#AAAAAA"
COLOR_PLAN    = "rgba(180,180,180,0.30)"

PALETTE_MAIN = [
    "#2D6A4F","#8B5E3C","#D4860B","#40916C","#C0392B",
    "#5B8DB8","#A0522D","#6B8E23","#D2691E","#4A7C59",
]
PALETTE_LIGHT = PALETTE_MAIN


def get_palette() -> list[str]:
    return PALETTE_MAIN


# ════════════════════════════════════════════════════════════
#  ブラウザ翻訳抑止
# ════════════════════════════════════════════════════════════
def prevent_browser_translation():
    components.html("""<script>
(function(){
  var p=window.parent.document;
  p.documentElement.setAttribute('translate','no');
  p.documentElement.setAttribute('lang','ja');
  if(!p.querySelector('meta[name="google"]')){
    var m=p.createElement('meta');m.name='google';m.content='notranslate';p.head.appendChild(m);
  }
})();
</script>""", height=0, scrolling=False)


# ════════════════════════════════════════════════════════════
#  共通CSS
# ════════════════════════════════════════════════════════════
def common_css() -> str:
    return f"""<style>
/* ── フォント ── */
html, body, .main, [data-testid="stAppViewContainer"] {{
  font-family: 'Noto Sans JP','Hiragino Sans','Yu Gothic UI',sans-serif !important;
}}

/* ── ページ背景 ── */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main {{
  background-color: {BG} !important;
}}

/* ── トップヘッダー・ツールバー ── */
[data-testid="stHeader"] {{
  background-color: {BG} !important;
  border-bottom: none !important;
  height: 2.2rem !important;
  min-height: 2.2rem !important;
  max-height: 2.2rem !important;
}}
[data-testid="stDecoration"] {{
  display: none !important;
}}
/* ヘッダー縮小後もコンテンツ領域が余白を保持するのを解消 */
section[data-testid="stAppViewContainer"] {{
  padding-top: 0 !important;
  margin-top: 0 !important;
}}
[data-testid="stAppViewContainer"] > .main {{
  padding-top: 0 !important;
}}

/* ── サイドバー ── */
[data-testid="stSidebar"] {{
  background-color: {SIDEBAR_BG} !important;
  border-right: 1px solid {BORDER} !important;
}}
[data-testid="stSidebarNav"] a span {{
  color: {TEXT_SUB} !important;
  font-weight: 500 !important;
}}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{
  color: {PRIMARY} !important;
  font-weight: 700 !important;
}}

/* ── コンテンツ幅 ── */
.main .block-container {{
  padding-top: 0.5rem !important;
  padding-bottom: 1rem !important;
  max-width: 1280px !important;
}}

/* ── 見出し ── */
h1 {{ color: {PRIMARY} !important; font-weight: 700 !important; font-size: 1.6rem !important; }}
h2 {{ color: {ACCENT}  !important; font-weight: 700 !important; font-size: 1.25rem !important; }}
h3,h4,h5,h6 {{ color: {TEXT} !important; font-weight: 600 !important; }}
p,span,li,td,th,label,div {{ color: {TEXT}; }}

/* ── KPIメトリクス ── */
[data-testid="stMetricContainer"] {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
  border-left: 4px solid {PRIMARY} !important;
  border-radius: 8px !important;
  padding: 16px 20px !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}}
[data-testid="stMetricLabel"] p {{
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.03em !important;
  color: {TEXT_SUB} !important;
}}
[data-testid="stMetricValue"] {{
  font-size: 2rem !important;
  font-weight: 700 !important;
  color: {PRIMARY} !important;
}}
[data-testid="stMetricDelta"] svg {{ display: none !important; }}
[data-testid="stMetricDelta"] {{ font-size: 0.75rem !important; color: {TEXT_SUB} !important; }}

/* ── グラフ ── */
[data-testid="stPlotlyChart"] {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
  padding: 4px !important;
}}

/* ── セクションタグ ── */
.section-tag {{
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: {PRIMARY};
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  margin: 12px 0 16px;
  border-bottom: 2px solid rgba(45,106,79,0.20);
}}

/* ── 工場カード ── */
.fac-grid {{ display: grid; gap: 10px; margin-bottom: 10px; }}
.fac-card {{
  background-color: {CARD};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 14px 18px;
  position: relative;
  overflow: hidden;
}}
.fac-card::before {{
  content:'';position:absolute;top:0;left:0;
  width:4px;height:100%;border-radius:8px 0 0 8px;
}}
.fac-ok::before   {{ background-color: {SECONDARY}; }}
.fac-warn::before {{ background-color: {COLOR_WARN}; }}
.fac-err::before  {{ background-color: {COLOR_ERR}; }}
.fac-none::before {{ background-color: #AAAAAA; }}
.fac-name  {{ font-size:0.62rem;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;color:{TEXT_SUB};margin-bottom:8px; }}
.fac-value {{ font-size:1.4rem;font-weight:700;color:{TEXT};display:flex;align-items:center;gap:8px; }}
.fac-note  {{ font-size:0.70rem;color:{TEXT_SUB};margin-top:5px; }}

/* ── ステータスドット ── */
.pdot {{ display:inline-block;width:8px;height:8px;border-radius:50%;flex-shrink:0; }}
.pdot-ok   {{ background-color: {SECONDARY}; }}
.pdot-warn {{ background-color: {COLOR_WARN}; }}
.pdot-err  {{ background-color: {COLOR_ERR}; }}
.pdot-none {{ background-color: #AAAAAA; }}

/* ── アラートカード ── */
.alert-ok   {{ background:rgba(64,145,108,0.07);border:1px solid {SECONDARY};border-left:3px solid {SECONDARY};border-radius:6px;padding:12px 16px;color:{TEXT}; }}
.alert-warn {{ background:rgba(212,134,11,0.07);border:1px solid {COLOR_WARN};border-left:3px solid {COLOR_WARN};border-radius:6px;padding:12px 16px;color:{TEXT}; }}
.alert-err  {{ background:rgba(192,57,43,0.07);border:1px solid {COLOR_ERR};border-left:3px solid {COLOR_ERR};border-radius:6px;padding:12px 16px;color:{TEXT}; }}

/* ── プログレスバー ── */
.pb-wrap {{ background:#E8E0D0;border-radius:3px;height:5px;overflow:hidden;margin-top:8px; }}
.pb-fill {{ height:100%;border-radius:3px; }}

/* ── バッジ ── */
.badge {{ display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px;font-size:0.70rem;font-weight:600; }}
.badge-ok   {{ background:rgba(64,145,108,0.10);color:{SECONDARY}; }}
.badge-warn {{ background:rgba(212,134,11,0.10);color:{COLOR_WARN}; }}
.badge-err  {{ background:rgba(192,57,43,0.10);color:{COLOR_ERR}; }}
.badge-info {{ background:rgba(45,106,79,0.10);color:{PRIMARY}; }}

/* ── ボタン ── */
.stButton > button {{
  background-color: {CARD} !important;
  border: 1px solid {PRIMARY} !important;
  color: {PRIMARY} !important;
  border-radius: 6px !important;
  font-weight: 600 !important;
}}
.stButton > button:hover {{
  background-color: {PRIMARY} !important;
  color: #FFFFFF !important;
}}
.stButton > button[kind="primary"] {{
  background-color: {PRIMARY} !important;
  border-color: {PRIMARY} !important;
  color: #FFFFFF !important;
}}

/* ── タブ ── */
[data-testid="stTabs"] [role="tablist"] {{
  border-bottom: 2px solid {BORDER} !important;
}}
[data-testid="stTab"][aria-selected="true"] {{
  color: {PRIMARY} !important;
  border-bottom: 2px solid {PRIMARY} !important;
  font-weight: 700 !important;
}}

/* ── エクスパンダー ── */
[data-testid="stExpander"],
details[data-testid="stExpander"] {{
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
  background-color: {CARD} !important;
}}
details[data-testid="stExpander"] > summary {{
  background-color: {SIDEBAR_BG} !important;
  border-radius: 8px !important;
  color: {TEXT} !important;
  padding: 10px 16px !important;
}}
details[data-testid="stExpander"][open] > summary {{
  border-radius: 8px 8px 0 0 !important;
  border-bottom: 1px solid {BORDER} !important;
}}
details[data-testid="stExpander"] > summary span,
details[data-testid="stExpander"] > summary p {{
  color: {TEXT} !important;
  font-weight: 600 !important;
}}
details[data-testid="stExpander"] > summary svg {{
  fill: {TEXT_SUB} !important;
}}
details[data-testid="stExpander"] > div {{
  background-color: {CARD} !important;
  border-radius: 0 0 8px 8px !important;
}}

/* ── ファイルアップローダー ── */
[data-testid="stFileUploader"] {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
}}
[data-testid="stFileUploaderDropzone"] {{
  background-color: {CARD} !important;
  border: 2px dashed {BORDER} !important;
  border-radius: 8px !important;
}}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] p {{
  color: {TEXT_SUB} !important;
}}
[data-testid="stFileUploaderDropzone"] button {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
  color: {TEXT} !important;
  border-radius: 6px !important;
}}

/* ── セレクトボックス ── */
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div {{
  background-color: {CARD} !important;
  color: {TEXT} !important;
  border-color: {BORDER} !important;
}}
[data-baseweb="select"] span {{ color: {TEXT} !important; }}
[data-baseweb="select"] svg {{ fill: {TEXT_SUB} !important; }}
[data-baseweb="popover"] [data-baseweb="menu"] {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
}}
[data-baseweb="popover"] [role="option"] {{
  background-color: {CARD} !important;
  color: {TEXT} !important;
}}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] {{
  background-color: {SIDEBAR_BG} !important;
}}

/* ── テキスト・日付入力 ── */
input, textarea, [data-baseweb="input"] > div {{
  background-color: {CARD} !important;
  color: {TEXT} !important;
  border-color: {BORDER} !important;
}}

/* ── 入力ラベル ── */
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stDateInput"] label,
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label {{
  color: {TEXT_SUB} !important;
  font-weight: 600 !important;
  font-size: 0.82rem !important;
}}

/* ── DataFrame外枠 ── */
[data-testid="stDataFrame"] {{
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
}}

/* ── divider ── */
hr, [data-testid="stDivider"] {{
  border-color: {BORDER} !important;
}}

/* ── コンテナ ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {{
  background-color: {CARD} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
}}
</style>"""


# ════════════════════════════════════════════════════════════
#  page_setup（全ページ共通初期化）
# ════════════════════════════════════════════════════════════
def page_setup():
    prevent_browser_translation()
    st.markdown(common_css(), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  ユーティリティ
# ════════════════════════════════════════════════════════════
def jp_date_input(label: str, default: date, key: str) -> date:
    if key not in st.session_state:
        st.session_state[key] = default
    return st.date_input(label, key=key, format="YYYY/MM/DD")


def unit_radio(horizontal: bool = True) -> tuple[str, int]:
    return "時間", 60


def extract_stop_type(reason) -> str:
    if pd.isna(reason) or str(reason).strip() == "":
        return "不明"
    return str(reason).split(" / ")[0].strip()


def smart_period(df: pd.DataFrame, date_from: date, date_to: date):
    days = (date_to - date_from).days
    df = df.copy()
    dt = pd.to_datetime(df["date"])
    if days <= 62:
        df["period_dt"] = dt.dt.normalize()
        df["period"]    = dt.dt.strftime("%m月%d日")
        x_title = "日付"
    else:
        df["period_dt"] = dt.dt.to_period("M").dt.to_timestamp()
        df["period"]    = dt.dt.strftime("%Y年%m月")
        x_title = "月"
    return df, None, x_title


# ════════════════════════════════════════════════════════════
#  グラフテーマ
# ════════════════════════════════════════════════════════════
def _achievement_color(pct) -> str:
    if pct is None:     return PRIMARY
    if pct >= 100:      return SECONDARY
    if pct >= 80:       return PRIMARY
    if pct >= 60:       return COLOR_WARN
    return COLOR_ERR


def apply_chart_theme(fig, height: int = 320, margin: dict = None):
    m    = margin or dict(t=40, b=10, l=10, r=10)
    grid = "rgba(0,0,0,0.07)"

    fig.update_layout(
        paper_bgcolor=CARD,
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=m,
        font=dict(color=TEXT, family="'Noto Sans JP',sans-serif", size=12),
        legend=dict(font=dict(color=TEXT, size=11), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(
        gridcolor=grid, linecolor="rgba(0,0,0,0.10)", zerolinecolor=grid,
        tickfont=dict(color=TEXT, size=11), title_font=dict(color=TEXT, size=12),
    )
    fig.update_yaxes(
        gridcolor=grid, linecolor="rgba(0,0,0,0.10)", zerolinecolor=grid,
        tickfont=dict(color=TEXT, size=11), title_font=dict(color=TEXT, size=12),
    )
    return fig


# ════════════════════════════════════════════════════════════
#  HTMLコンポーネント
# ════════════════════════════════════════════════════════════
def page_header_html(title: str, subtitle: str = "", icon: str = "🏭",
                     right_text: str = "") -> str:
    return f"""
<div style="
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 24px 14px;margin-bottom:20px;
  background-color:{CARD};border:1px solid {BORDER};
  border-top:3px solid {PRIMARY};border-radius:8px;
  box-shadow:0 1px 3px rgba(0,0,0,0.06);
">
  <div style="display:flex;align-items:center;gap:12px">
    <span style="font-size:2rem">{icon}</span>
    <div>
      <div style="font-size:1.4rem;font-weight:700;color:{PRIMARY};line-height:1.2">{title}</div>
      <div style="font-size:0.70rem;color:{TEXT_SUB};font-weight:600;letter-spacing:0.10em;
                  text-transform:uppercase;margin-top:2px">{subtitle}</div>
    </div>
  </div>
  <div style="font-size:0.82rem;color:{TEXT_SUB};font-weight:500">{right_text}</div>
</div>"""


def animated_kpi_html(value: str, label: str, delta: str = "",
                      icon: str = "", color: str = "",
                      progress: float | None = None) -> str:
    if not color:
        color = PRIMARY
    prog_html = ""
    if progress is not None:
        pct = min(max(progress, 0), 100)
        prog_html = (f'<div class="pb-wrap">'
                     f'<div class="pb-fill" style="width:{pct}%;background-color:{color}"></div>'
                     f'</div>')
    delta_html = ""
    if delta:
        delta_html = f'<div style="font-size:0.73rem;color:{color};margin-top:5px;font-weight:600">{delta}</div>'
    return f"""
<div class="fac-card" style="border-left:4px solid {color} !important">
  <div class="fac-name" style="color:{TEXT_SUB}">{icon}&nbsp;{label}</div>
  <div class="fac-value" style="color:{color};font-size:1.55rem">{value}</div>
  {delta_html}{prog_html}
</div>"""


def themed_table(df: pd.DataFrame, height: int | None = None,
                 hide_index: bool = True) -> None:
    """テーマ対応HTMLテーブル（st.dataframe の代替）"""
    disp = df.copy()
    if not hide_index:
        disp = disp.reset_index()

    def _fmt(v):
        if v is None:
            return "—"
        try:
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return "—"
        except Exception:
            pass
        s = str(v)
        return "—" if s in ("nan", "None", "NaT", "<NA>") else s

    th_s = (f"padding:8px 12px;text-align:left;font-size:0.72rem;font-weight:700;"
            f"letter-spacing:0.06em;text-transform:uppercase;color:{TEXT_SUB};"
            f"background:{SIDEBAR_BG};border-bottom:2px solid {PRIMARY};"
            f"white-space:nowrap;position:sticky;top:0;z-index:1")
    td_s = (f"padding:7px 12px;font-size:0.80rem;color:{TEXT};"
            f"border-bottom:1px solid {BORDER};"
            f"max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")

    header = "".join(f'<th style="{th_s}">{col}</th>' for col in disp.columns)
    rows = ""
    for i, (_, row) in enumerate(disp.iterrows()):
        bg_r = "rgba(0,0,0,0.02)" if i % 2 == 0 else CARD
        cells = "".join(f'<td style="{td_s}">{_fmt(v)}</td>' for v in row)
        rows += f'<tr style="background:{bg_r}">{cells}</tr>'

    scroll = f"max-height:{height}px;" if height else ""
    st.markdown(
        f'<div style="overflow-x:auto;{scroll}overflow-y:auto;'
        f'border:1px solid {BORDER};border-radius:8px;margin-bottom:8px">'
        f'<table style="width:100%;border-collapse:collapse;background:{CARD}">'
        f'<thead><tr>{header}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )


def factory_status_cards_html(factory_data: list[dict], cols: int = 0) -> str:
    n = len(factory_data)
    if n == 0:
        return ""
    grid_cols = cols if cols > 0 else n
    status_map = {
        "ok":   ("fac-ok",   "pdot pdot-ok"),
        "warn": ("fac-warn", "pdot pdot-warn"),
        "err":  ("fac-err",  "pdot pdot-err"),
        "none": ("fac-none", "pdot pdot-none"),
    }
    cards = []
    for d in factory_data:
        css, dot_cls = status_map.get(d.get("status", "none"), ("fac-none", "pdot pdot-none"))
        unit = d.get("unit", "")
        unit_html = f'<span style="font-size:0.78rem;opacity:0.6;font-weight:400"> {unit}</span>' if unit else ""
        cards.append(f"""
<div class="fac-card {css}">
  <div class="fac-name">{d.get('icon','')} {d.get('name','')}</div>
  <div class="fac-value"><span class="{dot_cls}"></span>{d.get('value','')}{unit_html}</div>
  <div class="fac-note">{d.get('note','')}</div>
</div>""")
    return (
        f'<div class="fac-grid" style="grid-template-columns:repeat({grid_cols},1fr)">'
        + "".join(cards) + "</div>"
    )


# ════════════════════════════════════════════════════════════
#  グラフ関数
# ════════════════════════════════════════════════════════════
def plan_fact_bar(df_agg: pd.DataFrame, title: str = "", height: int = 320) -> go.Figure:
    colors = []
    for _, row in df_agg.iterrows():
        pct = row["fact"] / row["plan"] * 100 if row.get("plan", 0) > 0 else None
        colors.append(_achievement_color(pct))
    fig = go.Figure()
    fig.add_bar(
        y=df_agg["表示名"], x=df_agg["plan"], name="計画", orientation="h",
        marker=dict(color=COLOR_PLAN, line=dict(color="rgba(120,120,120,0.3)", width=1)),
        hovertemplate="%{y}  計画: %{x:,.0f}<extra></extra>",
    )
    fig.add_bar(
        y=df_agg["表示名"], x=df_agg["fact"], name="実績", orientation="h",
        marker=dict(color=colors, opacity=0.9),
        hovertemplate="%{y}  実績: %{x:,.0f}<extra></extra>",
    )
    fig.update_layout(
        barmode="overlay", title_text=title, title_font_size=14, title_font_color=TEXT,
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=11, color=TEXT)),
    )
    apply_chart_theme(fig, height=height)
    return fig


def achievement_bar(labels, values, title: str = "達成率(%)", height: int = 280) -> go.Figure:
    if not values:
        return go.Figure()
    colors = [_achievement_color(v) for v in values]
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h",
        marker=dict(color=colors, opacity=0.9),
        text=[f"{v:.1f}%" for v in values], textposition="outside",
        textfont=dict(color=TEXT, size=12), cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig.add_vline(x=100, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1.5)
    max_val = max(values) * 1.28 if values else 130
    fig.update_layout(
        title_text=title, title_font_size=14, title_font_color=TEXT,
        xaxis_range=[0, max(max_val, 115)],
    )
    apply_chart_theme(fig, height=height)
    return fig


def gauge_chart(value: float, title: str = "", max_val: float = 100,
                height: int = 220) -> go.Figure:
    color = _achievement_color(value if max_val == 100 else value / max_val * 100)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title=dict(text=title, font=dict(size=12, color=TEXT)),
        number=dict(
            suffix="%" if max_val == 100 else "",
            font=dict(size=28, color=color),
            valueformat=".1f",
        ),
        gauge=dict(
            axis=dict(range=[0, max_val], tickfont=dict(size=9, color=TEXT)),
            bar=dict(color=color, thickness=0.70),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[
                dict(range=[0, max_val*0.6],         color="rgba(192,57,43,0.07)"),
                dict(range=[max_val*0.6, max_val*0.8], color="rgba(212,134,11,0.07)"),
                dict(range=[max_val*0.8, max_val],     color="rgba(64,145,108,0.06)"),
            ],
        ),
    ))
    apply_chart_theme(fig, height=height, margin=dict(t=30, b=10, l=25, r=25))
    return fig


def multi_gauge(items: list[dict], height: int = 220) -> go.Figure:
    n = len(items)
    if n == 0:
        return go.Figure()
    step = 1.0 / n
    domains = [[i*step+0.01, (i+1)*step-0.01] for i in range(n)]
    fig = go.Figure()
    for i, item in enumerate(items):
        val = item.get("value", 0)
        mx  = item.get("max", 100)
        pct = val / mx * 100 if mx > 0 else 0
        color = _achievement_color(pct)
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=val,
            title=dict(text=item.get("label", ""), font=dict(size=10, color=TEXT)),
            number=dict(suffix="%" if mx==100 else "", font=dict(size=16, color=color), valueformat=".1f"),
            gauge=dict(
                axis=dict(range=[0, mx], tickfont=dict(size=7, color=TEXT)),
                bar=dict(color=color, thickness=0.7),
                bgcolor="rgba(0,0,0,0)", borderwidth=0,
                steps=[
                    dict(range=[0, mx*0.6],        color="rgba(192,57,43,0.07)"),
                    dict(range=[mx*0.6, mx*0.8],   color="rgba(212,134,11,0.07)"),
                    dict(range=[mx*0.8, mx],        color="rgba(64,145,108,0.05)"),
                ],
            ),
            domain=dict(x=domains[i], y=[0, 1]),
        ))
    apply_chart_theme(fig, height=height, margin=dict(t=40, b=10, l=10, r=10))
    return fig


def calendar_heatmap(df_stop: pd.DataFrame, year: int, month: int,
                     title: str = "停止時間カレンダー") -> go.Figure:
    import calendar as _cal
    WEEKDAYS_JP = ["月","火","水","木","金","土","日"]
    _, days_in_month = _cal.monthrange(year, month)
    first_weekday   = _cal.monthrange(year, month)[0]

    stop_map: dict[int, float] = {}
    if not df_stop.empty:
        df_m = df_stop.copy()
        df_m["_d"] = pd.to_datetime(df_m["date"], errors="coerce")
        df_m = df_m[(df_m["_d"].dt.year==year) & (df_m["_d"].dt.month==month)]
        if not df_m.empty:
            for day, grp in df_m.groupby(df_m["_d"].dt.day):
                stop_map[day] = grp["duration_minutes"].sum() / 60

    grid = [[None]*7 for _ in range(6)]
    text = [[""] *7 for _ in range(6)]
    col, row = first_weekday, 0
    for d in range(1, days_in_month+1):
        hrs = stop_map.get(d, 0.0)
        grid[row][col] = hrs
        text[row][col] = f"{d}日\n{hrs:.1f}h" if hrs > 0 else f"{d}日"
        col += 1
        if col == 7: col=0; row+=1

    z_vals = [[v if v is not None else -1 for v in r] for r in grid]
    colorscale = [
        [0,   "rgba(45,106,79,0.05)"],
        [0.01,"rgba(64,145,108,0.25)"],
        [0.3, "rgba(212,134,11,0.55)"],
        [0.7, "rgba(192,57,43,0.75)"],
        [1,   "rgba(139,0,0,0.90)"],
    ]
    fig = go.Figure(go.Heatmap(
        z=z_vals, text=text, texttemplate="%{text}",
        textfont=dict(size=10, color=TEXT),
        x=WEEKDAYS_JP, y=[f"第{i+1}週" for i in range(6)],
        colorscale=colorscale,
        zmin=0, zmax=max(8, max(stop_map.values(), default=1)),
        showscale=True,
        colorbar=dict(title=dict(text="停止(h)", font=dict(color=TEXT, size=10)),
                      thickness=12, len=0.8, tickfont=dict(size=9, color=TEXT)),
        hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(
        title_text=f"{year}年{month}月  {title}",
        title_font_size=13, title_font_color=TEXT,
        yaxis=dict(autorange="reversed"),
    )
    apply_chart_theme(fig, height=280, margin=dict(t=45, b=10, l=55, r=60))
    return fig


def inject_animations():
    components.html("""<script>
(function(){
  try{
    var doc=window.parent.document;
    var obs=new IntersectionObserver(function(entries){
      entries.forEach(function(e){if(e.isIntersecting)e.target.classList.add('in-view');});
    },{threshold:0.06});
    function init(){doc.querySelectorAll('.fade-up').forEach(function(el){obs.observe(el);});}
    init();
    new MutationObserver(function(){init();}).observe(doc.body,{childList:true,subtree:true});
  }catch(e){}
})();
</script>""", height=0, scrolling=False)
