import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Admin del Sistema", page_icon="🖥️", layout="wide")

st.markdown(
    """
    <style>
    .hero-admin {
        background: linear-gradient(135deg, #1f2d3d 0%, #3c5a78 100%);
        border:1px solid #3c5a78; border-radius:14px; padding:16px 18px;
        color:#e6f0ff;
        box-shadow:0 2px 12px rgba(60,90,120,.35) inset;
    }
    .hero-admin .muted{ color:#c1d9f7; font-size:.92rem; }
    </style>
    <div class="hero-admin">
      <h2 style="margin:0 0 6px 0;">🖥️ Panel de Administración del Sistema</h2>
      <div class="muted">
        Monitor de estado del disco, base de datos y adjuntos.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Lógica de Carga (Caché)
# -----------------------------
@st.cache_data(ttl=60)
def get_system_metrics():
    """Obtiene todas las métricas de salud centralizadas."""
    metrics = {}
    try:
        # 1. Métricas del Host
        df_health = queries.get_host_health_metrics()
        metrics['health_data'] = df_health.set_index('metric_name').to_dict('index') if not df_health.empty else {}

        # 2. Tamaño DB
        df_total_size = queries.get_database_size(settings.DB_NAME)
        metrics['db_total_size'] = df_total_size.iloc[0]['size'] if not df_total_size.empty else "Error"

        # 3. Desglose Tablas
        metrics['table_breakdown'] = queries.get_tables_size_breakdown(limit=10)

        return metrics
    except Exception as e:
        st.error(f"Error recuperando métricas: {e}")
        return None

# -----------------------------
# Renderizado
# -----------------------------
st.subheader("Métricas de Almacenamiento del Servidor")

metrics = get_system_metrics()
if not metrics:
    st.stop()

# Helpers UI
def get_metric(data, key, field='value_numeric', default=0.0):
    return data.get(key, {}).get(field, default) or 0.0

health_data = metrics.get('health_data', {})
disk_used = get_metric(health_data, 'disk_used_gb')
disk_total = get_metric(health_data, 'disk_total_gb')
disk_free = get_metric(health_data, 'disk_free_gb')
disk_percent = get_metric(health_data, 'disk_percent_used')
media_size = get_metric(health_data, 'media_folder_gb')

# KPIs
k1, k2, k3 = st.columns(3)
k1.metric("Uso del Disco (Servidor /)", f"{disk_used:.2f} GB / {disk_total:.2f} GB", f"{disk_free:.2f} GB Libres")
k2.metric("Espacio Ocupado por /media", f"{media_size:.2f} GB")
k3.metric("Espacio Ocupado por la BBDD", metrics['db_total_size'])

st.progress(disk_percent / 100)

# Alerta de frescura
last_update = health_data.get('disk_used_gb', {}).get('last_updated')
if last_update:
    if last_update.tzinfo is None: last_update = last_update.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - last_update
    if diff > timedelta(minutes=15):
        st.warning(f"¡Atención! Métricas desactualizadas (hace {diff.total_seconds()/60:.0f} min).")
    else:
        st.caption(f"Estado al {disk_percent:.1f}% (actualizado hace {diff.total_seconds():.0f}s).")
else:
    st.warning("Esperando datos del agente 'health_reporter'.")

st.markdown("---")

# Tabla DB
st.subheader("Desglose de la Base de Datos")
if not metrics['table_breakdown'].empty:
    df_t = metrics['table_breakdown'].rename(columns={"table_name": "Tabla", "total_size_pretty": "Tamaño Total"})
    st.dataframe(df_t, width='stretch', hide_index=True)
else:
    st.info("No disponible.")

st.markdown("---")
st.info("Solo lectura. La limpieza se gestiona vía 'Janitor'.")