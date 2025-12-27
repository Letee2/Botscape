# botscape/dashboard/Home.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, timezone
import os

# Imports Arquitectura
from botscape.config import settings
import botscape.shared.db.queries as queries
import botscape.dashboard.ui.home as ui

# Configuración
st.set_page_config(
    page_title="BotScape | C2 Intel", 
    page_icon="🛰️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

ui.inject_css()

# --- QUERY LIVE FEED ---
from botscape.shared.db.caching import read_sql
def get_live_feed_data(limit=10):
    return read_sql("""
        SELECT token, has_media, text as snippet, to_char(date_utc, 'HH24:MI') as time_str
        FROM messages ORDER BY date_utc DESC LIMIT %(limit)s
    """, params={"limit": limit})

# -----------------------------
# Sidebar & Filtros
# -----------------------------
st.sidebar.title("⚙️ Control")
days = st.sidebar.slider("Ventana (Días)", 1, 60, 7)
end_date = st.sidebar.date_input("Hasta (UTC)", value=date.today())

start_date = end_date - timedelta(days=days - 1)
start_iso = f"{start_date.isoformat()}T00:00:00Z"
end_iso   = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"

prev_start = start_date - timedelta(days=days)
prev_iso_start = f"{prev_start.isoformat()}T00:00:00Z"
prev_iso_end = start_iso

# -----------------------------
# 1. Carga de Datos Globales
# -----------------------------
# KPIs
df_kpi_cur = queries.get_global_kpis(start_iso, end_iso)
df_kpi_prev = queries.get_global_kpis(prev_iso_start, prev_iso_end)
df_ent_cur = queries.get_global_entity_count(start_iso, end_iso)

# Actividad Diaria (Para el Sparkline del Hero)
df_daily = queries.get_daily_activity(start_iso, end_iso)

def safe_val(df, col): return int(df.iloc[0][col] or 0) if not df.empty else 0

bots_cur = safe_val(df_kpi_cur, "bots")
bots_delta = bots_cur - safe_val(df_kpi_prev, "bots")
msgs_cur = safe_val(df_kpi_cur, "msgs")
msgs_delta = msgs_cur - safe_val(df_kpi_prev, "msgs")
media_cur = safe_val(df_kpi_cur, "media")
ents_cur = safe_val(df_ent_cur, "ents")

kpi_pack = {
    'bots': (bots_cur, bots_delta),
    'msgs': (msgs_cur, msgs_delta),
    'media': media_cur,
    'ents': ents_cur
}

# -----------------------------
# 2. Render Hero Unificado (Con Sparkline)
# -----------------------------
logo_path = os.path.join(os.getcwd(), "logo.png")
if not os.path.exists(logo_path): logo_path = os.path.join(settings.BASE_DIR, "logo.png")

ui.render_hero_unified(logo_path, start_date, end_date, kpi_pack, df_daily)

# -----------------------------
# 3. Action Grid
# -----------------------------
ui.render_action_grid()

st.write("")

# -----------------------------
# 4. Live Wire & Analytics
# -----------------------------
col_live, col_viz = st.columns([1.6, 1.2])

with col_live:
    # Tabla interactiva con botones directos
    df_feed = get_live_feed_data(limit=8)
    ui.render_live_wire_interactive(df_feed)

with col_viz:
    # Sunburst de Entidades
    df_top_vals = queries.get_top_entities_values(start_iso, end_iso, limit=60)
    ui.render_entity_sunburst(df_top_vals)
    
    # Top Bots (Bar Chart) - Reemplaza al gráfico de actividad que movimos arriba
    st.write("")
    df_top = queries.get_top_bots_by_volume(start_iso, end_iso, limit=8)
    ui.render_top_bots_chart(df_top)

# -----------------------------
# 5. Footer
# -----------------------------
df_latest = queries.get_latest_message_timestamp()
if not df_latest.empty and df_latest.iloc[0]["maxdt"]:
    ts = df_latest.iloc[0]["maxdt"]
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    ago = datetime.now(timezone.utc) - ts
    status_color = "#238636" if ago < timedelta(minutes=10) else "#d29922"
    status_msg = "Sincronizado" if ago < timedelta(minutes=10) else f"Latencia: {int(ago.total_seconds()/60)}m"
    
    st.markdown(f"""
    <div style="text-align:center; margin-top:30px; padding-top:10px; border-top:1px solid #21262d; font-size:0.8rem; color:#8b949e;">
        System Status: <span style="color:{status_color}; font-weight:bold;">● {status_msg}</span> 
        | Última ingesta: {ts.strftime('%H:%M:%S UTC')}
    </div>
    """, unsafe_allow_html=True)