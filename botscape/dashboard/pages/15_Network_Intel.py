import streamlit as st
import pandas as pd

# --- Imports de Arquitectura ---
import botscape.shared.db.queries as queries

# Configuración
st.set_page_config(page_title="Network Intel", page_icon="📡", layout="wide")

st.markdown("""
<style>
    .intel-box {
        background-color: #12141c; 
        border: 1px solid #2d3342; 
        padding: 15px; 
        border-radius: 8px; 
        margin-bottom: 20px;
    }
    .webhook-url { color: #fca5a5; font-family: monospace; }
    .origin-url { color: #86efac; font-family: monospace; }
</style>
<div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%); padding: 20px; border-radius: 10px; border-bottom: 2px solid #3b82f6;">
    <h2 style="margin:0; color: #e2e8f0;">📡 Network Intelligence</h2>
    <div style="color: #94a3b8;">Infraestructura confirmada: C2 Backends y Vectores de Infección.</div>
</div>
<br>
""", unsafe_allow_html=True)

# 1. Cargar Datos
df_webhooks = queries.get_c2_webhooks()
df_origins = queries.get_confirmed_origins()

# 2. KPIs
k1, k2 = st.columns(2)
k1.metric("Webhooks C2 (Backends)", len(df_webhooks), help="Direcciones directas de los servidores que controlan los bots.")
k2.metric("Orígenes Confirmados (Frontends)", len(df_origins), help="URLs desde donde se distribuye el malware o phishing (In-The-Wild).")

st.divider()

# --- SECCIÓN 1: C2 WEBHOOKS ---
st.subheader("🚨 Infraestructura C2 (Webhooks)")
st.caption("Estas URLs reciben directamente los datos robados por los bots. Son el 'cerebro' de la operación.")

if not df_webhooks.empty:
    # Formateo visual para la tabla
    st.dataframe(
        df_webhooks,
        use_container_width=True,
        hide_index=True,
        column_config={
            "token": st.column_config.TextColumn("Bot Token", width="medium"),
            "c2_webhook_url": st.column_config.LinkColumn(
                "Webhook URL (Destino)", 
                width="large",
                display_text=r"https?://(.*?)/.*" # Regex para mostrar solo el dominio limpio
            ),
            "detected_at": "Detectado",
            "is_active": "Bot Activo"
        }
    )
    
    # Botón de exportación rápida
    csv_wh = df_webhooks.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Lista C2 (CSV)", csv_wh, "c2_webhooks.csv", "text/csv")

else:
    st.info("No se han detectado Webhooks activos todavía. La mayoría de bots podrían estar usando Long Polling.")

st.divider()

# --- SECCIÓN 2: ORÍGENES DE INFECCIÓN ---
st.subheader("🎣 Vectores de Origen (In-The-Wild)")
st.caption("Sitios web comprometidos o dominios maliciosos desde donde se descarga el malware.")

if not df_origins.empty:
    st.dataframe(
        df_origins,
        use_container_width=True,
        hide_index=True,
        column_config={
            "origin_url": st.column_config.LinkColumn("URL de Origen", width="large"),
            "file_type": "Tipo de Archivo",
            "sha256": st.column_config.TextColumn("Hash Muestra", width="medium"),
            "associated_token": "Bot Asociado",
            "origin_source": "Fuente (Intel)"
        }
    )
    
    csv_or = df_origins.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Orígenes (CSV)", csv_or, "infection_origins.csv", "text/csv")

else:
    st.info("No hay orígenes confirmados aún. Ejecuta el hunter en modo 'Phishing' para buscar más.")