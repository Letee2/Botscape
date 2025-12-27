import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Channel Analysis", page_icon="👥", layout="wide")

st.markdown(
    """
    <style>
    .hero-channels {
        background: linear-gradient(135deg, #062a2f 0%, #0a3e48 55%, #0f5966 100%);
        border:1px solid #0e3a42; border-radius:14px; padding:16px 18px;
        color:#e9fbff;
        box-shadow:0 2px 12px rgba(6,42,47,.35) inset;
    }
    .hero-channels .muted{ color:#bfe7ee; font-size:.92rem; }
    </style>
    <div class="hero-channels">
      <h2 style="margin:0 0 6px 0;">👥 Channel Analysis</h2>
      <div class="muted">
        Analiza los canales (chats) donde operan los bots para encontrar
        infraestructura compartida y actores clave.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Helpers
# -----------------------------
def dt_range(start_date: date, end_date: date):
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso   = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"
    return start_iso, end_iso

# -----------------------------
# Filtros
# -----------------------------
st.write("")
c_f1, c_f2 = st.columns([1, 1])
with c_f1:
    days = st.slider("Ventana (días)", 1, 60, 14, key="chan_days")
with c_f2:
    end_date = st.date_input("Hasta (UTC)", value=date.today(), key="chan_end")

start_date = end_date - timedelta(days=days - 1)
start_iso, end_iso = dt_range(start_date, end_date)
st.caption(f"Mostrando datos entre {start_iso.split('T')[0]} y {end_iso.split('T')[0]} (UTC)")
st.write("")

# -----------------------------
# 1. Leaderboard
# -----------------------------
st.subheader("🏆 Leaderboard de Canales (Top 100)")
st.markdown("""
Esta tabla muestra los canales (chats) más activos.
- `unique_bots`: N.º de *nuestros bots monitorizados* en este chat.
- `unique_senders`: N.º de IDs de usuario únicos.
""")

df_leaderboard = queries.get_channel_leaderboard(start_iso, end_iso)

if df_leaderboard.empty:
    st.info("No se encontró actividad de canal en esta ventana de tiempo.")
    st.stop()

st.dataframe(df_leaderboard, width='stretch', height=350)
st.write("")
st.markdown("---")

# -----------------------------
# 2. Drill-Down
# -----------------------------
st.subheader("🔬 Análisis Detallado del Canal")

selected_chat_id = st.selectbox(
    "Selecciona un Chat ID del leaderboard para analizarlo:",
    options=df_leaderboard["chat_id"].unique()
)

if not selected_chat_id:
    st.stop()

# Carga de datos específicos del canal
df_bots = queries.get_channel_bot_activity(selected_chat_id, start_iso, end_iso)
df_senders = queries.get_channel_sender_activity(selected_chat_id, start_iso, end_iso)
df_timeline = queries.get_channel_timeline(selected_chat_id, start_iso, end_iso)
df_messages = queries.get_channel_recent_messages(selected_chat_id, start_iso, end_iso)

# Gráficos
col_g1, col_g2 = st.columns(2)

with col_g1:
    st.markdown(f"**Bots Monitorizados en `{selected_chat_id}`**")
    if not df_bots.empty:
        fig_bots = px.bar(df_bots, x="message_count", y="token", orientation='h', title=f"Bots ({len(df_bots)})")
        fig_bots.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bots, width='stretch')
    else:
        st.info("Sin actividad de bots propios.")

with col_g2:
    st.markdown(f"**Top Remitentes en `{selected_chat_id}`**")
    if not df_senders.empty:
        fig_senders = px.bar(df_senders, x="message_count", y="sender_id", orientation='h', title=f"Remitentes ({len(df_senders)})")
        fig_senders.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_senders, width='stretch')
    else:
        st.info("Sin actividad de remitentes.")

# Timeline
st.markdown(f"**Línea de Tiempo**")
if not df_timeline.empty:
    fig_time = px.area(df_timeline, x="day", y="count", title=f"Volumen diario")
    fig_time.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_time, width='stretch')
else:
    st.info("Sin datos temporales.")

# Mensajes
st.markdown(f"**Muestra de Mensajes (Últimos 50)**")
if not df_messages.empty:
    st.dataframe(df_messages, width='stretch', height=300)
else:
    st.info("No hay mensajes recientes.")