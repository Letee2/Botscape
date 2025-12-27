import streamlit as st
import pandas as pd
from datetime import date, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Salud del Hunter", page_icon="🎯", layout="wide")

st.markdown(
    """
    <style>
    .hero-health {
        background: linear-gradient(135deg, #1f1d2b 0%, #2f2a45 100%);
        border:1px solid #3a3357; border-radius:14px; padding:16px 18px;
        color:#e0dcfc;
        box-shadow:0 2px 12px rgba(47,42,69,.35) inset;
    }
    .hero-health .muted{ color:#c7c1ea; font-size:.92rem; }
    </style>
    <div class="hero-health">
      <h2 style="margin:0 0 6px 0;">Bots Behaviour</h2>
      <div class="muted">
        Análisis del ciclo de vida de los Bots.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# 1. KPIs Generales
# -----------------------------
st.subheader("Estado General del Sistema")

df_health = queries.get_system_health_kpis()

if df_health.empty:
    st.error("No se pudieron cargar las métricas de salud.")
    st.stop()

health = df_health.iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Bots Activos (Monitorizados)", f"{health['active_bots'] or 0}")
k2.metric("Bots Inactivos", f"{health['inactive_bots'] or 0}")

last_check = health['last_hunter_check'].strftime("%Y-%m-%d %H:%M:%S") if health['last_hunter_check'] else "Nunca"
last_msg = health['last_listener_message'].strftime("%Y-%m-%d %H:%M:%S") if health['last_listener_message'] else "Ninguno"

k3.metric("Última Ejecución Hunter", last_check)
k4.metric("Último Mensaje Recibido", last_msg)

st.markdown("---")

# -----------------------------
# 2. Bots Nuevos
# -----------------------------
st.subheader("Actividad de Bots Nuevos (Hunter)")
st.caption("Bots descubiertos por el Hunter y su estado de actividad.")

days_check = st.slider("Ver bots añadidos en los últimos (días)", 1, 30, 7)
df_new = queries.get_new_bots_stats(days=days_check)

if df_new.empty:
    st.info(f"No se han añadido nuevos bots en los últimos {days_check} días.")
else:
    total_new = len(df_new)
    silent_bots = len(df_new[df_new['last_seen'].isnull()])
    
    kp1, kp2 = st.columns(2)
    kp1.metric(f"Bots Nuevos (Últimos {days_check} días)", total_new)
    kp2.metric("Bots Silenciosos (Nunca han hablado)", silent_bots)

    # Formato visual
    df_new['first_seen_utc'] = pd.to_datetime(df_new['first_seen_utc']).dt.strftime('%Y-%m-%d %H:%M')
    df_new['last_seen'] = pd.to_datetime(df_new['last_seen']).dt.strftime('%Y-%m-%d %H:%M')
    df_new['time_to_first_message'] = df_new['time_to_first_message'].astype(str).str.replace('0 days ', '')
    
    st.dataframe(df_new.fillna("---"), width='stretch')

st.markdown("---")

# -----------------------------
# 3. Bots Caídos
# -----------------------------
st.subheader("Bots Caídos Recientemente")
st.caption("Bots marcados como 'inactivos' por el Listener (Token revocado).")

df_dead = queries.get_dead_bots_stats(limit=50)

if df_dead.empty:
    st.info("¡Buenas noticias! No hay bots marcados como inactivos.")
else:
    df_dead['last_seen'] = pd.to_datetime(df_dead['last_seen']).dt.strftime('%Y-%m-%d %H:%M')
    df_dead['last_checked_utc'] = pd.to_datetime(df_dead['last_checked_utc']).dt.strftime('%Y-%m-%d %H:%M')
    st.dataframe(df_dead.fillna("---"), width='stretch')

st.markdown("---")

# -----------------------------
# 4. Trazabilidad (Hash Traceability)
# -----------------------------
st.subheader("Trazabilidad: Hashes de Malware Fructíferos")
st.caption("Hashes de malware que han proporcionado más bots activos.")

df_hashes = queries.get_top_malware_sources(limit=25)

if df_hashes.empty:
    st.info("No hay información de origen (hash) para los bots activos.")
else:
    df_hashes['last_bot_found_date'] = pd.to_datetime(df_hashes['last_bot_found_date']).dt.date
    st.dataframe(df_hashes, width='stretch')