"""
Lead Intelligence Dashboard — stakeholder edition
Run: streamlit run app.py
"""
import os
from datetime import timedelta
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from data_utils import (
    load_and_enrich, build_prospect_master, period_compare, BUDGET_TIER_ORDER,
    INDIA_STATE_COORDS, build_whatsapp_message, phone_for_whatsapp,
)

st.set_page_config(
    page_title="Lead Intelligence Dashboard Green Raise Agro",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

# ======== Theme ========
PRIMARY = '#1a5f3f'
ACCENT  = '#2d8659'
LIGHT   = '#7fc89a'
WARN    = '#d97706'
BAD     = '#b91c1c'
GREEN_SCALE = ['#e8f5ec', '#b7e0c4', '#7fc89a', '#4da674', '#2d8659', '#1a5f3f', '#0e3a26']
QUAL_PALETTE = ['#1a5f3f', '#2d8659', '#4da674', '#7fc89a', '#b7e0c4', '#d97706', '#059669', '#0891b2', '#7c3aed', '#db2777']

st.markdown(f"""
<style>
    .main > div {{ padding-top: 0.5rem; padding-bottom: 2rem; }}
    [data-testid="stMetricValue"] {{ font-size: 28px; font-weight: 700; color: {PRIMARY}; }}
    [data-testid="stMetricLabel"] {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #555; }}
    [data-testid="stMetricDelta"] {{ font-size: 13px; }}
    h1 {{ color: {PRIMARY}; margin-bottom: 0; font-size: 34px; }}
    h2 {{ color: {ACCENT}; border-bottom: 2px solid {LIGHT}; padding-bottom: 6px; margin-top: 24px; }}
    h3 {{ color: {PRIMARY}; margin-top: 18px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 2px solid #e5e7eb; }}
    .stTabs [data-baseweb="tab"] {{ padding: 10px 18px; font-weight: 500; border-radius: 6px 6px 0 0; }}
    .stTabs [aria-selected="true"] {{ background-color: {LIGHT}33; color: {PRIMARY}; }}
    .insight-card {{
        background: linear-gradient(135deg, #f0fdf4 0%, #e8f5ec 100%);
        border-left: 4px solid {PRIMARY};
        padding: 14px 18px;
        border-radius: 6px;
        margin: 12px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .insight-card strong {{ color: {PRIMARY}; }}
    .action-card {{
        background: #fffbeb;
        border-left: 4px solid {WARN};
        padding: 14px 18px;
        border-radius: 6px;
        margin: 12px 0;
    }}
    .kpi-strip {{
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .stDataFrame {{ border: 1px solid #e5e7eb; border-radius: 6px; }}
    footer, header {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Parsing & enriching leads…")
def _load_cached(path_or_bytes, fname):
    return load_and_enrich(path_or_bytes)


def insight(text):
    st.markdown(f'<div class="insight-card">💡 {text}</div>', unsafe_allow_html=True)


def action(text):
    st.markdown(f'<div class="action-card">🎯 {text}</div>', unsafe_allow_html=True)


def fmt_num(n):
    if n is None or pd.isna(n): return '—'
    n = float(n)
    if n >= 1e7: return f"₹{n/1e7:.1f} Cr"
    if n >= 1e5: return f"₹{n/1e5:.1f} L"
    if n >= 1e3: return f"₹{n/1e3:.1f} K"
    return f"₹{n:.0f}"


def fmt_qty(kg):
    if kg is None or pd.isna(kg): return '—'
    kg = float(kg)
    if kg >= 1000: return f"{kg/1000:.1f} T"
    if kg >= 1: return f"{kg:.0f} kg"
    return f"{kg*1000:.0f} g"


def pct_delta(cur, prev):
    if prev == 0 or prev is None: return None
    return (cur - prev) / prev * 100


# ======== Sidebar: data source ========
with st.sidebar:
    st.markdown(f"### 📊 Lead Intelligence")
    st.markdown("---")
    st.markdown("#### 📁 Data source")
    uploaded = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx', 'xls'],
                                label_visibility='collapsed')
    st.caption("Expected columns: QUERY_TIME, SENDER_*, QUERY_MCAT_NAME, QUERY_MESSAGE, QUERY_TYPE…")
    st.markdown("---")

default_path = "IndiaMartDataFromApril2024 - Sheet1.csv"
if uploaded is not None:
    source, source_label = uploaded, uploaded.name
elif os.path.exists(default_path):
    source, source_label = default_path, default_path
else:
    st.title("📊 Lead Intelligence Dashboard")
    st.warning("📥 Upload a lead-export CSV/Excel in the sidebar to begin.")
    st.stop()

df = _load_cached(source, source_label)
if len(df) == 0:
    st.error("No valid rows found (couldn't parse QUERY_TIME). Check the file.")
    st.stop()

# ======== Sidebar: filters ========
with st.sidebar:
    st.markdown("#### 🔍 Filters")
    mind, maxd = df['QUERY_TIME'].min().date(), df['QUERY_TIME'].max().date()
    date_range = st.date_input("Date range", value=(mind, maxd),
                               min_value=mind, max_value=maxd)

    states = sorted(df['SENDER_STATE'].dropna().unique().tolist()) if 'SENDER_STATE' in df.columns else []
    sel_states = st.multiselect("State", states, placeholder="All states")

    products = sorted(df['QUERY_MCAT_NAME'].dropna().unique().tolist()) if 'QUERY_MCAT_NAME' in df.columns else []
    sel_products = st.multiselect("Product category", products, placeholder="All products")

    channels = sorted(df['CHANNEL'].dropna().unique().tolist()) if 'CHANNEL' in df.columns else []
    sel_channels = st.multiselect("Channel", channels, placeholder="All channels")

    sel_tiers = st.multiselect("Lead tier", ['Hot', 'Warm', 'Cold'], placeholder="All tiers")
    sel_req = st.multiselect("Requirement type", ['Business', 'Personal'], placeholder="All")

    exclude_spam = st.checkbox("🧹 Exclude suspected spam/fake", value=True,
                               help="Hides rows flagged with fake phones, duplicate spammers, test names, etc.")

    st.markdown("---")
    st.caption(f"📄 `{source_label}`")
    st.caption(f"Source rows: **{len(df):,}**")

# Apply filters
f = df.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    f = f[(f['QUERY_TIME'].dt.date >= date_range[0]) & (f['QUERY_TIME'].dt.date <= date_range[1])]
if sel_states:   f = f[f['SENDER_STATE'].isin(sel_states)]
if sel_products: f = f[f['QUERY_MCAT_NAME'].isin(sel_products)]
if sel_channels: f = f[f['CHANNEL'].isin(sel_channels)]
if sel_tiers:    f = f[f['LEAD_TIER'].isin(sel_tiers)]
if sel_req:      f = f[f['REQ_TYPE'].isin(sel_req)]
if exclude_spam and 'IS_SPAM' in f.columns:
    f = f[~f['IS_SPAM']]

if len(f) == 0:
    st.warning("No leads match the selected filters.")
    st.stop()

# ======== Header ========
period_start = f['QUERY_TIME'].min().strftime('%d %b %Y')
period_end   = f['QUERY_TIME'].max().strftime('%d %b %Y')
st.title("📊 Lead Intelligence Dashboard")
st.markdown(
    f"<p style='color:#666; margin-top:-8px;'>Reporting period: <strong>{period_start}</strong> → "
    f"<strong>{period_end}</strong> &nbsp;•&nbsp; {len(f):,} leads &nbsp;•&nbsp; "
    f"{f['SENDER_MOBILE'].nunique():,} unique prospects</p>",
    unsafe_allow_html=True,
)

# ======== Tabs ========
tabs = st.tabs([
    "🏆 Executive Summary",
    "📈 Trends",
    "🗺️ Geography",
    "🛒 Products",
    "📞 Channels",
    "🌾 Crops",
    "👥 Prospect Segmentation",
    "🔥 Hot Leads",
    "📱 Campaigns",
    "🧹 Data Quality",
    "📥 Export",
])

# ============================================================
# TAB 0 — Executive Summary
# ============================================================
with tabs[0]:
    # --- Period comparison (last 30 vs prior 30) ---
    cur, prev = period_compare(f, days=30)

    st.subheader("Headline metrics")
    k1, k2, k3, k4, k5 = st.columns(5)

    cur_leads = len(cur); prev_leads = len(prev)
    k1.metric("Leads (last 30d)", f"{cur_leads:,}",
              delta=f"{pct_delta(cur_leads, prev_leads):+.1f}% vs prior 30d" if prev_leads else None)

    cur_prospects = cur['SENDER_MOBILE'].nunique()
    prev_prospects = prev['SENDER_MOBILE'].nunique()
    k2.metric("Unique prospects (30d)", f"{cur_prospects:,}",
              delta=f"{pct_delta(cur_prospects, prev_prospects):+.1f}%" if prev_prospects else None)

    cur_hot = (cur['LEAD_TIER'] == 'Hot').sum()
    prev_hot = (prev['LEAD_TIER'] == 'Hot').sum()
    k3.metric("Hot leads (30d)", f"{cur_hot:,}",
              delta=f"{pct_delta(cur_hot, prev_hot):+.1f}%" if prev_hot else None)

    total_leads = len(f)
    k4.metric("Total leads (period)", f"{total_leads:,}")

    total_prospects = f['SENDER_MOBILE'].nunique()
    k5.metric("Total prospects", f"{total_prospects:,}")

    st.markdown("&nbsp;")

    # --- Headline chart ---
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Monthly lead volume with tier composition")
        monthly_tier = f.groupby(['QUERY_MONTH', 'LEAD_TIER']).size().reset_index(name='leads')
        fig = px.bar(monthly_tier, x='QUERY_MONTH', y='leads', color='LEAD_TIER',
                     color_discrete_map={'Hot': PRIMARY, 'Warm': LIGHT, 'Cold': '#cbd5e1'},
                     category_orders={'LEAD_TIER': ['Hot', 'Warm', 'Cold']})
        fig.update_layout(height=380, margin=dict(t=20, b=20), legend=dict(orientation='h', y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Lead tier split")
        tier_counts = f['LEAD_TIER'].value_counts().reindex(['Hot', 'Warm', 'Cold'], fill_value=0).reset_index()
        tier_counts.columns = ['tier', 'count']
        fig = px.pie(tier_counts, names='tier', values='count', hole=0.6,
                     color='tier',
                     color_discrete_map={'Hot': PRIMARY, 'Warm': LIGHT, 'Cold': '#cbd5e1'})
        fig.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # --- Auto insights ---
    st.subheader("🔎 Auto-generated insights")

    top_state = f['SENDER_STATE'].value_counts()
    top_state_name = top_state.index[0]
    top_state_pct = top_state.iloc[0] / len(f) * 100

    top_city = f['SENDER_CITY'].value_counts()
    top_city_name = top_city.index[0]
    top_city_pct = top_city.iloc[0] / len(f) * 100

    top_prod = f['QUERY_MCAT_NAME'].value_counts()
    top_prod_name = top_prod.index[0]
    top_prod_pct = top_prod.iloc[0] / len(f) * 100

    hot_pct_total = (f['LEAD_TIER'] == 'Hot').mean() * 100
    repeat_rate = (f['SENDER_MOBILE'].value_counts() > 1).mean() * 100

    peak_month = f['QUERY_MONTH'].value_counts().idxmax()
    peak_month_cnt = f['QUERY_MONTH'].value_counts().max()
    avg_month = f.groupby('QUERY_MONTH').size().mean()
    peak_lift = peak_month_cnt / avg_month

    c1, c2 = st.columns(2)
    with c1:
        insight(f"<strong>{top_state_name}</strong> drives <strong>{top_state_pct:.1f}%</strong> of all leads — "
                f"a concentrated territory for field sales & dealer activation.")
        insight(f"<strong>{top_prod_name}</strong> is the #1 product ({top_prod_pct:.1f}% of queries). "
                f"Prioritize content, ads, and inventory around it.")
        insight(f"<strong>{hot_pct_total:.1f}%</strong> of leads are Hot-tier — "
                f"that's {(f['LEAD_TIER']=='Hot').sum():,} high-intent buyers with stated budget/quantity/business-use.")
    with c2:
        insight(f"<strong>{top_city_name}</strong> single-handedly contributes <strong>{top_city_pct:.1f}%</strong> "
                f"of leads — ideal for a direct dealer tie-up or van-route.")
        insight(f"<strong>{repeat_rate:.1f}%</strong> of prospects query more than once — "
                f"these are re-contactable without ad spend.")
        insight(f"Seasonality peak: <strong>{peak_month}</strong> ran <strong>{peak_lift:.1f}×</strong> "
                f"above the monthly average. Prepare inventory & ads 3 weeks prior next year.")

    # --- Recommended actions ---
    st.subheader("🎯 Top 3 recommended actions")
    action(f"<strong>Play 1 — Hot-lead blitz:</strong> Assign the {(f['LEAD_TIER']=='Hot').sum():,} Hot leads "
           f"to closers for 24-hour callback. Export from the Hot Leads tab.")
    action(f"<strong>Play 2 — {top_state_name} concentration:</strong> Cluster the top 3 cities "
           f"({', '.join(top_city.head(3).index.tolist())}) into a dealer/field-sales circuit.")
    dormant = build_prospect_master(f)
    if len(dormant) and 'days_since_last' in dormant.columns:
        sleeping = ((dormant['days_since_last'].between(60, 180))).sum()
        action(f"<strong>Play 3 — Dormant reactivation:</strong> {sleeping:,} prospects went silent 60-180 days ago. "
               f"Re-engage via WhatsApp with a product refresh or seasonal offer.")

# ============================================================
# TAB 1 — Trends
# ============================================================
with tabs[1]:
    st.subheader("Daily lead volume with 7-day moving average")
    daily = f.groupby(f['QUERY_TIME'].dt.date).size().reset_index(name='leads')
    daily.columns = ['date', 'leads']
    daily['rolling_7d'] = daily['leads'].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=daily['date'], y=daily['leads'], name='Daily', marker_color=LIGHT, opacity=0.55))
    fig.add_trace(go.Scatter(x=daily['date'], y=daily['rolling_7d'], name='7-day avg',
                             line=dict(color=PRIMARY, width=3)))
    fig.update_layout(height=380, legend=dict(orientation='h', y=1.1), margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Monthly lead volume")
        monthly = f.groupby('QUERY_MONTH').size().reset_index(name='leads')
        fig = px.bar(monthly, x='QUERY_MONTH', y='leads')
        fig.update_traces(marker_color=PRIMARY)
        fig.update_layout(height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Day-of-week distribution")
        dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        dow = f.groupby('QUERY_DOW').size().reindex(dow_order, fill_value=0).reset_index()
        dow.columns = ['day', 'leads']
        fig = px.bar(dow, x='day', y='leads')
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Activity heatmap — Day × Hour")
    heat = f.groupby(['QUERY_DOW', 'QUERY_HOUR']).size().reset_index(name='leads')
    heat_pivot = heat.pivot(index='QUERY_DOW', columns='QUERY_HOUR', values='leads').reindex(
        ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    ).fillna(0)
    fig = px.imshow(heat_pivot, aspect='auto', color_continuous_scale=GREEN_SCALE,
                    labels=dict(x='Hour of day', y='Day', color='Leads'))
    fig.update_layout(height=360)
    st.plotly_chart(fig, use_container_width=True)

    peak_hour = f['QUERY_HOUR'].value_counts().idxmax()
    peak_day = f['QUERY_DOW'].value_counts().idxmax()
    weekend_share = f['QUERY_DOW'].isin(['Saturday', 'Sunday']).mean() * 100
    insight(f"Peak window: <strong>{peak_day}s around {peak_hour}:00</strong>. "
            f"Weekend traffic: <strong>{weekend_share:.1f}%</strong> — schedule shifts and WhatsApp blasts accordingly.")

# ============================================================
# TAB 2 — Geography
# ============================================================
with tabs[2]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top states by lead volume")
        s = f['SENDER_STATE'].value_counts().head(15).reset_index()
        s.columns = ['state', 'leads']
        s['share'] = (s['leads'] / len(f) * 100).round(1)
        fig = px.bar(s, x='leads', y='state', orientation='h', text='share',
                     hover_data={'share': ':.1f'})
        fig.update_traces(marker_color=PRIMARY, texttemplate='%{text}%', textposition='outside')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=520, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Top cities by lead volume")
        c = f['SENDER_CITY'].value_counts().head(15).reset_index()
        c.columns = ['city', 'leads']
        c['share'] = (c['leads'] / len(f) * 100).round(1)
        fig = px.bar(c, x='leads', y='city', orientation='h', text='share')
        fig.update_traces(marker_color=ACCENT, texttemplate='%{text}%', textposition='outside')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=520, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    top5_state_share = f['SENDER_STATE'].value_counts(normalize=True).head(5).sum() * 100
    top10_city_share = f['SENDER_CITY'].value_counts(normalize=True).head(10).sum() * 100
    insight(f"Top 5 states capture <strong>{top5_state_share:.1f}%</strong> of leads. "
            f"Top 10 cities capture <strong>{top10_city_share:.1f}%</strong>. "
            f"This concentration makes field-force deployment economical.")

    # India bubble map
    st.subheader("🗺️ India map — lead density by state")
    state_agg = f.groupby('SENDER_STATE').agg(
        leads=('QUERY_TYPE', 'size'),
        prospects=('SENDER_MOBILE', 'nunique'),
        hot=('LEAD_TIER', lambda x: (x == 'Hot').sum()),
    ).reset_index()
    state_agg['lat'] = state_agg['SENDER_STATE'].map(lambda s: INDIA_STATE_COORDS.get(s, (None, None))[0])
    state_agg['lon'] = state_agg['SENDER_STATE'].map(lambda s: INDIA_STATE_COORDS.get(s, (None, None))[1])
    state_map = state_agg.dropna(subset=['lat', 'lon'])
    if len(state_map):
        fig = px.scatter_mapbox(
            state_map, lat='lat', lon='lon',
            size='leads', color='hot',
            hover_name='SENDER_STATE',
            hover_data={'leads': True, 'prospects': True, 'hot': True, 'lat': False, 'lon': False},
            color_continuous_scale=GREEN_SCALE,
            size_max=55, zoom=3.8,
            mapbox_style='open-street-map',
            height=560,
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                          mapbox=dict(center=dict(lat=22.5, lon=80)))
        st.plotly_chart(fig, use_container_width=True)
        insight("Bubble size = lead volume. Colour = hot-lead count. "
                "Dark + big = high-volume **and** high-intent states — prioritize these.")

    st.subheader("State × Product affinity (top 10 × 10)")
    top_states = f['SENDER_STATE'].value_counts().head(10).index
    top_prods = f['QUERY_MCAT_NAME'].value_counts().head(10).index
    sub = f[f['SENDER_STATE'].isin(top_states) & f['QUERY_MCAT_NAME'].isin(top_prods)]
    if len(sub):
        heat = sub.groupby(['SENDER_STATE', 'QUERY_MCAT_NAME']).size().reset_index(name='leads')
        pivot = heat.pivot(index='SENDER_STATE', columns='QUERY_MCAT_NAME', values='leads').fillna(0)
        fig = px.imshow(pivot, aspect='auto', color_continuous_scale=GREEN_SCALE,
                        labels=dict(color='Leads'))
        fig.update_layout(height=520)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("State quality ranking (volume × hot %)")
    quality = f.groupby('SENDER_STATE').agg(
        leads=('QUERY_TYPE', 'size'),
        hot_pct=('LEAD_TIER', lambda x: (x == 'Hot').mean() * 100),
        prospects=('SENDER_MOBILE', 'nunique'),
    ).reset_index()
    quality = quality[quality['leads'] >= 50].sort_values('leads', ascending=False).head(15)
    quality['hot_pct'] = quality['hot_pct'].round(1)
    fig = px.scatter(quality, x='leads', y='hot_pct', size='prospects',
                     hover_name='SENDER_STATE', text='SENDER_STATE',
                     labels={'leads': 'Lead volume', 'hot_pct': 'Hot %', 'prospects': 'Unique prospects'})
    fig.update_traces(marker=dict(color=PRIMARY, opacity=0.7), textposition='top center')
    fig.update_layout(height=440, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)
    insight("States in the top-right quadrant are both high-volume and high-intent — "
            "these are your marketing priority territories.")

# ============================================================
# TAB 3 — Products
# ============================================================
with tabs[3]:
    st.subheader("Top 20 product categories")
    p = f['QUERY_MCAT_NAME'].value_counts().head(20).reset_index()
    p.columns = ['product', 'leads']
    p['share'] = (p['leads'] / len(f) * 100).round(1)
    fig = px.bar(p, x='leads', y='product', orientation='h', text='share',
                 color='leads', color_continuous_scale=GREEN_SCALE)
    fig.update_traces(texttemplate='%{text}%', textposition='outside')
    fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=620,
                      coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly mix — top 6 products")
    top6 = f['QUERY_MCAT_NAME'].value_counts().head(6).index
    sub = f[f['QUERY_MCAT_NAME'].isin(top6)]
    mx = sub.groupby(['QUERY_MONTH', 'QUERY_MCAT_NAME']).size().reset_index(name='leads')
    fig = px.area(mx, x='QUERY_MONTH', y='leads', color='QUERY_MCAT_NAME',
                  color_discrete_sequence=QUAL_PALETTE)
    fig.update_layout(height=400, margin=dict(t=20), legend=dict(orientation='h', y=-0.2))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🚀 Fastest-growing products (last 90d vs prior 90d)")
        max_date = f['QUERY_TIME'].max()
        recent = f[f['QUERY_TIME'] >= max_date - pd.Timedelta(days=90)]
        prior  = f[(f['QUERY_TIME'] >= max_date - pd.Timedelta(days=180)) &
                   (f['QUERY_TIME'] <  max_date - pd.Timedelta(days=90))]
        rc = recent['QUERY_MCAT_NAME'].value_counts()
        pc = prior['QUERY_MCAT_NAME'].value_counts()
        growth = pd.DataFrame({'recent': rc, 'prior': pc}).fillna(0)
        growth = growth[growth['recent'] >= 10]
        growth['change_%'] = ((growth['recent'] - growth['prior']) / growth['prior'].replace(0, 1) * 100).round(1)
        rising = growth.sort_values('change_%', ascending=False).head(10)
        fig = px.bar(rising.reset_index(), y='QUERY_MCAT_NAME', x='change_%', orientation='h',
                     text='change_%')
        fig.update_traces(marker_color=PRIMARY, texttemplate='+%{text}%', textposition='outside')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("📉 Declining products")
        falling = growth.sort_values('change_%', ascending=True).head(10)
        fig = px.bar(falling.reset_index(), y='QUERY_MCAT_NAME', x='change_%', orientation='h',
                     text='change_%')
        fig.update_traces(marker_color=BAD, texttemplate='%{text}%', textposition='outside')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    if 'FORM' in f.columns and f['FORM'].notna().any():
        st.subheader("Requested product forms")
        form = f['FORM'].value_counts().reset_index()
        form.columns = ['form', 'count']
        fig = px.pie(form, names='form', values='count', hole=0.5,
                     color_discrete_sequence=GREEN_SCALE)
        fig.update_layout(height=300, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# TAB 4 — Channels
# ============================================================
with tabs[4]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Channel mix")
        ch = f['CHANNEL'].value_counts().reset_index()
        ch.columns = ['channel', 'leads']
        fig = px.pie(ch, names='channel', values='leads', hole=0.5,
                     color_discrete_sequence=QUAL_PALETTE)
        fig.update_layout(height=360, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Channel × Lead tier")
        ct = f.groupby(['CHANNEL', 'LEAD_TIER']).size().reset_index(name='leads')
        fig = px.bar(ct, x='CHANNEL', y='leads', color='LEAD_TIER',
                     color_discrete_map={'Hot': PRIMARY, 'Warm': LIGHT, 'Cold': '#cbd5e1'},
                     category_orders={'LEAD_TIER': ['Hot', 'Warm', 'Cold']})
        fig.update_layout(height=360, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Channel quality — Hot-lead % by channel")
    ch_quality = f.groupby('CHANNEL').agg(
        leads=('QUERY_TYPE', 'size'),
        hot_pct=('LEAD_TIER', lambda x: (x == 'Hot').mean() * 100),
    ).reset_index()
    ch_quality = ch_quality[ch_quality['leads'] >= 20].sort_values('hot_pct', ascending=True)
    ch_quality['hot_pct'] = ch_quality['hot_pct'].round(1)
    fig = px.bar(ch_quality, y='CHANNEL', x='hot_pct', orientation='h',
                 text='hot_pct', hover_data=['leads'])
    fig.update_traces(marker_color=PRIMARY, texttemplate='%{text}%', textposition='outside')
    fig.update_layout(height=300, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

    best_channel = ch_quality.iloc[-1]
    insight(f"<strong>{best_channel['CHANNEL']}</strong> is the highest-quality channel "
            f"with <strong>{best_channel['hot_pct']:.1f}%</strong> Hot-lead rate. Shift ad budget there.")

    if 'CALL_DURATION' in f.columns:
        calls = f.copy()
        calls['CD'] = pd.to_numeric(calls['CALL_DURATION'], errors='coerce')
        calls = calls[calls['CD'] > 0]
        if len(calls):
            st.subheader(f"📞 Call analytics — {len(calls):,} calls logged")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Total calls", f"{len(calls):,}")
            mc2.metric("Avg duration", f"{calls['CD'].mean():.0f}s")
            mc3.metric("Median duration", f"{calls['CD'].median():.0f}s")
            mc4.metric("Long calls (>2 min)", f"{(calls['CD'] > 120).sum():,}")
            fig = px.histogram(calls[calls['CD'] < 600], x='CD', nbins=40,
                               title=None, labels={'CD': 'Call duration (seconds)'})
            fig.update_traces(marker_color=PRIMARY)
            fig.update_layout(height=320, margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# TAB 5 — Crops
# ============================================================
with tabs[5]:
    if 'CROPS' in f.columns:
        exploded = f.explode('CROPS')
        exploded = exploded[exploded['CROPS'].notna() & (exploded['CROPS'] != '')]
        if len(exploded):
            st.subheader(f"🌾 {len(exploded):,} crop mentions across {exploded['CROPS'].nunique()} crops")
            c1, c2 = st.columns(2)
            with c1:
                cr = exploded['CROPS'].value_counts().head(20).reset_index()
                cr.columns = ['crop', 'mentions']
                fig = px.bar(cr, x='mentions', y='crop', orientation='h', text='mentions')
                fig.update_traces(marker_color=PRIMARY, textposition='outside')
                fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=580, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                top_crops = exploded['CROPS'].value_counts().head(10).index
                top_prods_cr = exploded['QUERY_MCAT_NAME'].value_counts().head(10).index
                cp = exploded[exploded['CROPS'].isin(top_crops) &
                              exploded['QUERY_MCAT_NAME'].isin(top_prods_cr)]
                if len(cp):
                    heat = cp.groupby(['CROPS', 'QUERY_MCAT_NAME']).size().reset_index(name='leads')
                    pivot = heat.pivot(index='CROPS', columns='QUERY_MCAT_NAME', values='leads').fillna(0)
                    fig = px.imshow(pivot, aspect='auto', color_continuous_scale=GREEN_SCALE,
                                    labels=dict(color='Leads'))
                    fig.update_layout(height=580, margin=dict(t=20))
                    st.plotly_chart(fig, use_container_width=True)

            st.subheader("Crop × State focus")
            top_states_cr = exploded['SENDER_STATE'].value_counts().head(10).index
            cs = exploded[exploded['CROPS'].isin(top_crops) & exploded['SENDER_STATE'].isin(top_states_cr)]
            if len(cs):
                heat = cs.groupby(['CROPS', 'SENDER_STATE']).size().reset_index(name='leads')
                pivot = heat.pivot(index='CROPS', columns='SENDER_STATE', values='leads').fillna(0)
                fig = px.imshow(pivot, aspect='auto', color_continuous_scale=GREEN_SCALE)
                fig.update_layout(height=440, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)

            top_crop_1 = exploded['CROPS'].value_counts().index[0]
            insight(f"<strong>{top_crop_1.title()}</strong> is the #1 mentioned crop — "
                    f"build a dedicated product + content bundle around it.")
        else:
            st.info("No crop mentions detected in QUERY_MESSAGE.")
    else:
        st.info("QUERY_MESSAGE column not present — no crop extraction possible.")

# ============================================================
# TAB 6 — Prospect Segmentation (RFM)
# ============================================================
with tabs[6]:
    master = build_prospect_master(f)
    st.subheader(f"👥 Prospect segmentation — {len(master):,} unique prospects")

    if len(master) and 'segment' in master.columns:
        seg = master['segment'].value_counts().reindex(
            ['Champions', 'New', 'Active', 'Slipping', 'Dormant'], fill_value=0
        ).reset_index()
        seg.columns = ['segment', 'count']

        c1, c2, c3, c4, c5 = st.columns(5)
        cmap = {'Champions': PRIMARY, 'New': ACCENT, 'Active': LIGHT, 'Slipping': WARN, 'Dormant': BAD}
        for col, (_, r) in zip([c1, c2, c3, c4, c5], seg.iterrows()):
            col.metric(r['segment'], f"{r['count']:,}",
                       f"{r['count']/len(master)*100:.1f}%" if len(master) else "")

        c1, c2 = st.columns([1, 1])
        with c1:
            fig = px.pie(seg, names='segment', values='count', hole=0.5,
                         color='segment', color_discrete_map=cmap,
                         category_orders={'segment': ['Champions', 'New', 'Active', 'Slipping', 'Dormant']})
            fig.update_layout(height=360, margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("**Segment playbook**")
            st.markdown("""
- **Champions** (recent + repeat) — protect with loyalty pricing, upsell larger SKUs
- **New** (recent + single query) — 24-hour callback, send catalog + sample
- **Active** (queried within 90d) — nurture with product emails, seasonal offers
- **Slipping** (90-180d silent) — WhatsApp reactivation, limited-time promo
- **Dormant** (180d+ silent) — bulk WhatsApp blast, lowest-priority
            """)

        st.subheader("🥇 Top 50 prospects by lead score")
        show_cols = ['phone', 'name', 'company', 'city', 'state', 'total_queries',
                     'top_product', 'avg_budget', 'max_qty_kg', 'days_since_last',
                     'segment', 'tier', 'best_score']
        show_cols = [c for c in show_cols if c in master.columns]
        st.dataframe(master[show_cols].head(50), use_container_width=True, hide_index=True, height=440)

        st.subheader("Drill-down: filter the master file")
        c1, c2 = st.columns(2)
        with c1:
            max_q = int(master['total_queries'].max())
            min_q = st.slider("Minimum total queries", 1, max(1, max_q), 1)
        with c2:
            seg_sel = st.multiselect("Segment", list(cmap.keys()), default=['Champions', 'New', 'Active'])
        mf = master[master['total_queries'] >= min_q]
        if seg_sel:
            mf = mf[mf['segment'].isin(seg_sel)]
        st.caption(f"{len(mf):,} prospects match filters")
        st.dataframe(mf[show_cols] if show_cols else mf, use_container_width=True, hide_index=True, height=400)

# ============================================================
# TAB 7 — Hot Leads
# ============================================================
with tabs[7]:
    hot = f[f['LEAD_TIER'] == 'Hot'].sort_values('LEAD_SCORE', ascending=False)
    st.subheader(f"🔥 {len(hot):,} Hot leads")
    st.caption("Scored on channel, stated budget, quantity, business intent, frequency, contact completeness.")

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Hot leads", f"{len(hot):,}")
    h2.metric("Avg score", f"{hot['LEAD_SCORE'].mean():.0f}")
    h3.metric("With budget stated", f"{hot['BUDGET_AVG'].notna().sum():,}")
    h4.metric("Business-use", f"{(hot['REQ_TYPE']=='Business').sum():,}")

    show_cols = ['QUERY_TIME', 'SENDER_NAME', 'SENDER_MOBILE', 'SENDER_EMAIL',
                 'SENDER_COMPANY', 'SENDER_CITY', 'SENDER_STATE',
                 'QUERY_MCAT_NAME', 'BUDGET_TIER', 'QTY_KG', 'REQ_TYPE',
                 'FREQUENCY', 'CHANNEL', 'LEAD_SCORE']
    show_cols = [c for c in show_cols if c in hot.columns]
    st.dataframe(hot[show_cols].head(1000), use_container_width=True, hide_index=True, height=520)
    st.caption(f"Showing top 1,000 of {len(hot):,}. Full export in the **Export** tab.")

# ============================================================
# TAB 8 — Campaigns (WhatsApp ready)
# ============================================================
with tabs[8]:
    st.subheader("📱 WhatsApp campaign builder")
    st.caption("Export segmented, deduplicated, WhatsApp-ready contact lists with pre-written messages.")

    master_all = build_prospect_master(f)

    if len(master_all) == 0:
        st.info("No prospects available.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            campaign_target = st.selectbox(
                "Target segment",
                ['Champions', 'New', 'Active', 'Slipping', 'Dormant', 'Hot (by lead tier)'],
            )
        with c2:
            min_score = st.slider("Minimum lead score", 0, 100, 0)
        with c3:
            max_rows = st.number_input("Max contacts in export", 1, 20000, 500, step=100)

        # Build campaign list
        if campaign_target == 'Hot (by lead tier)':
            camp = master_all[master_all['tier'] == 'Hot'].copy()
            seg_label = 'Hot'
        else:
            camp = master_all[master_all['segment'] == campaign_target].copy() if 'segment' in master_all.columns else master_all.iloc[0:0]
            seg_label = campaign_target
        camp = camp[camp['best_score'] >= min_score]
        camp = camp.head(int(max_rows))

        # Normalize phone to WhatsApp format + build message (handle empty-df edge case)
        if len(camp) > 0:
            camp['whatsapp_phone'] = camp['phone'].apply(phone_for_whatsapp)
            camp['wa_link'] = camp['whatsapp_phone'].apply(
                lambda p: f"https://wa.me/{p}" if p else None
            )
            camp['message'] = [
                build_whatsapp_message(seg_label, r.get('name'), r.get('top_product'))
                for _, r in camp.iterrows()
            ]
            camp = camp[camp['whatsapp_phone'].notna()]
        else:
            camp = camp.assign(whatsapp_phone=pd.Series(dtype='object'),
                               wa_link=pd.Series(dtype='object'),
                               message=pd.Series(dtype='object'))

        mm1, mm2, mm3, mm4 = st.columns(4)
        mm1.metric("Contacts ready", f"{len(camp):,}")
        mm2.metric("Segment", seg_label)
        mm3.metric("Avg score", f"{camp['best_score'].mean():.0f}" if len(camp) else "—")
        mm4.metric("Unique states", f"{camp['state'].nunique():,}" if 'state' in camp.columns else "—")

        st.markdown("**Sample message (same template, name + product personalized per row):**")
        if len(camp):
            sample = camp.iloc[0]
            st.code(sample['message'], language=None)

        show_cols = ['name', 'whatsapp_phone', 'wa_link', 'company', 'city', 'state',
                     'top_product', 'total_queries', 'best_score', 'message']
        show_cols = [c for c in show_cols if c in camp.columns]
        st.dataframe(camp[show_cols], use_container_width=True, hide_index=True, height=420)

        @st.cache_data
        def _to_csv(d):
            return d.to_csv(index=False).encode('utf-8')

        cexp1, cexp2 = st.columns(2)
        with cexp1:
            st.download_button(
                f"📲 Download WhatsApp list — {seg_label} ({len(camp):,})",
                _to_csv(camp[show_cols]),
                file_name=f"whatsapp_campaign_{seg_label.lower()}.csv",
                use_container_width=True,
            )
        with cexp2:
            bulk_text = "\n".join(
                f"{r['whatsapp_phone']} | {r['message']}" for _, r in camp.iterrows()
            )
            st.download_button(
                "📝 Download phone+message list (.txt)",
                bulk_text.encode('utf-8'),
                file_name=f"bulk_whatsapp_{seg_label.lower()}.txt",
                use_container_width=True,
            )

    st.markdown("---")
    st.subheader("✏️ Template library")
    from data_utils import WA_TEMPLATES
    for seg, tpl in WA_TEMPLATES.items():
        with st.expander(f"📝 {seg}"):
            st.code(tpl, language=None)

    st.caption("💡 Templates can be customised in `data_utils.py → WA_TEMPLATES`.")


# ============================================================
# TAB 9 — Data Quality
# ============================================================
with tabs[9]:
    st.subheader("🧹 Data quality audit")
    st.caption("Spam, duplicate, and fake-lead detection on the **entire source file** (not filtered).")

    full = df.copy()
    spam_rows = full[full['IS_SPAM']]
    good_rows = full[~full['IS_SPAM']]

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Total rows", f"{len(full):,}")
    q2.metric("Clean rows", f"{len(good_rows):,}", f"{len(good_rows)/len(full)*100:.1f}%")
    q3.metric("Suspected spam", f"{len(spam_rows):,}", f"-{len(spam_rows)/len(full)*100:.1f}%")
    unique_phones = full['SENDER_MOBILE'].nunique()
    q4.metric("Unique phones", f"{unique_phones:,}")

    # Reason breakdown
    st.subheader("Spam reasons breakdown")
    reason_list = []
    for r in spam_rows['SPAM_REASON']:
        reason_list.extend([x.strip() for x in r.split(',') if x.strip()])
    reason_counts = pd.Series(reason_list).value_counts().reset_index()
    if len(reason_counts):
        reason_counts.columns = ['reason', 'count']
        fig = px.bar(reason_counts, x='count', y='reason', orientation='h', text='count')
        fig.update_traces(marker_color=BAD, textposition='outside')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    # Top over-queried phones
    st.subheader("🚨 Top 20 most-frequent phones (possible scrapers/bots)")
    freq = full['SENDER_MOBILE'].value_counts().head(20).reset_index()
    freq.columns = ['phone', 'queries']
    freq = freq.merge(
        full[['SENDER_MOBILE', 'SENDER_NAME', 'SENDER_CITY', 'SENDER_STATE']]
            .drop_duplicates('SENDER_MOBILE'),
        left_on='phone', right_on='SENDER_MOBILE', how='left',
    ).drop(columns='SENDER_MOBILE')
    st.dataframe(freq, use_container_width=True, hide_index=True, height=450)
    insight("Phones appearing 20+ times are often scrapers, competitors, or bot traffic. "
            "Review and consider blacklisting before running paid campaigns.")

    # Spam sample
    st.subheader("🔍 Sample flagged rows")
    spam_cols = ['QUERY_TIME', 'SENDER_NAME', 'SENDER_MOBILE', 'SENDER_EMAIL',
                 'SENDER_CITY', 'QUERY_MCAT_NAME', 'SPAM_REASON']
    spam_cols = [c for c in spam_cols if c in spam_rows.columns]
    if len(spam_rows):
        st.dataframe(spam_rows[spam_cols].head(200), use_container_width=True,
                     hide_index=True, height=400)

    @st.cache_data
    def _dq_csv(d):
        return d.to_csv(index=False).encode('utf-8')

    dqc1, dqc2 = st.columns(2)
    with dqc1:
        st.download_button(
            "⬇️ Download flagged/spam rows",
            _dq_csv(spam_rows),
            file_name="flagged_spam.csv",
            use_container_width=True,
        )
    with dqc2:
        st.download_button(
            "✅ Download clean rows only",
            _dq_csv(good_rows),
            file_name="clean_leads.csv",
            use_container_width=True,
        )


# ============================================================
# TAB 10 — Export
# ============================================================
with tabs[10]:
    st.subheader("📥 Downloadable reports")
    st.caption("All exports respect the sidebar filters.")

    @st.cache_data
    def to_csv(d):
        return d.to_csv(index=False).encode('utf-8')

    master = build_prospect_master(f)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("⬇️ All filtered leads (enriched)",
                           to_csv(f), file_name="leads_enriched.csv", use_container_width=True)
    with c2:
        st.download_button("🔥 Hot leads only",
                           to_csv(f[f['LEAD_TIER'] == 'Hot']),
                           file_name="hot_leads.csv", use_container_width=True)
    with c3:
        st.download_button("👥 Prospect master",
                           to_csv(master), file_name="prospect_master.csv", use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Executive summary (copy & paste into email)")

    top_state_name = f['SENDER_STATE'].value_counts().index[0]
    top_city_name = f['SENDER_CITY'].value_counts().index[0]
    top_product_name = f['QUERY_MCAT_NAME'].value_counts().index[0]
    hot_pct_total = (f['LEAD_TIER'] == 'Hot').mean() * 100
    repeat_rate = (f['SENDER_MOBILE'].value_counts() > 1).mean() * 100

    summary_text = f"""
**Reporting period:** {period_start} → {period_end}

**Volume**
- Total leads: {len(f):,}
- Unique prospects: {f['SENDER_MOBILE'].nunique():,}
- Repeat-prospect rate: {repeat_rate:.1f}%

**Geography**
- States covered: {f['SENDER_STATE'].nunique()}  |  Cities: {f['SENDER_CITY'].nunique():,}
- #1 state: {top_state_name} ({f['SENDER_STATE'].value_counts().iloc[0]:,} leads, {f['SENDER_STATE'].value_counts(normalize=True).iloc[0]*100:.1f}%)
- #1 city: {top_city_name}

**Products & intent**
- #1 product: {top_product_name}
- Hot-lead share: {hot_pct_total:.1f}%
- Stated budget: {f['BUDGET_AVG'].notna().sum():,} leads
- Business-use declared: {(f['REQ_TYPE']=='Business').sum():,} leads
"""
    st.markdown(summary_text)
    st.download_button("📄 Download executive summary (.md)",
                       summary_text.encode('utf-8'),
                       file_name="executive_summary.md",
                       use_container_width=True)
