import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime

# Imports de Arquitectura
from botscape.config import settings
import botscape.shared.db.queries.profiling as queries
# Importamos el motor de análisis para el botón "Force Run"
from botscape.scripts.profiler import analyze_single_bot

# Configuración
st.set_page_config(page_title="Profiler AI", page_icon="🕵️‍♂️", layout="wide")

# Estilos CSS para Badges de Riesgo
st.markdown("""
<style>
.risk-badge {
    padding: 4px 12px; border-radius: 16px; font-weight: bold; color: white;
}
.risk-CRITICAL { background-color: #dc3545; }
.risk-HIGH { background-color: #fd7e14; }
.risk-MEDIUM { background-color: #ffc107; color: black; }
.risk-LOW { background-color: #28a745; }
.risk-UNKNOWN { background-color: #6c757d; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <div style="background: linear-gradient(135deg, #2c0b0e 0%, #4a1b22 100%); border:1px solid #5c2b33; padding:16px; border-radius:14px; color:#ffdadf;">
      <h2 style="margin:0;">🕵️‍♂️ Profiler AI</h2>
      <div style="color:#e0b8be; font-size:0.9rem;">
        Análisis semántico de bots mediante LLM local ({model}).
      </div>
    </div>
    """.format(model="Llama 3.1"), unsafe_allow_html=True
)

# -----------------------------
# 1. KPIs de Inteligencia
# -----------------------------
df_kpis = queries.get_profiling_kpis()
if not df_kpis.empty:
    row = df_kpis.iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Bots Perfilados", row['total_profiled'])
    k2.metric("Riesgo CRÍTICO", row['critical'])
    k3.metric("Riesgo ALTO", row['high'])
    k4.metric("Stealers Identificados", row['stealers'])

st.markdown("---")

# -----------------------------
# 2. Leaderboard de Riesgo
# -----------------------------
col_main, col_detail = st.columns([1.5, 2])

with col_main:
    st.subheader("Threat Radar")
    df_list = queries.get_profiles_leaderboard(limit=50)
    
    if df_list.empty:
        st.info("No hay perfiles generados aún. Ejecuta el script 'profiler.py'.")
        st.stop()
        
    # Selector interactivo
    selected_idx = st.dataframe(
        df_list, 
        width='stretch', 
        height=600,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "token": "Bot Token",
            "risk_level": "Riesgo",
            "actor_intent": "Intención",
            "analyzed_at": st.column_config.DatetimeColumn("Analizado", format="DD/MM HH:mm"),
            "risk_score": None, # Ocultar columna de ordenación
            "display_name": None
        }
    )

    selected_token = None
    if len(selected_idx.selection['rows']) > 0:
        row_idx = selected_idx.selection['rows'][0]
        selected_token = df_list.iloc[row_idx]['token']

# -----------------------------
# 3. Detalle del Informe (Report Card)
# -----------------------------
with col_detail:
    if selected_token:
        profile_df = queries.get_bot_profile(selected_token)
        if profile_df.empty:
            st.warning("Error cargando perfil.")
            st.stop()
            
        p = profile_df.iloc[0]
        
        # Header del Reporte
        r_color = f"risk-{p['risk_level']}"
        
        # Usamos st.container para agrupar
        with st.container():
            # Título y Badge
            c_head1, c_head2 = st.columns([3, 1])
            c_head1.subheader("Informe de Inteligencia")
            c_head2.markdown(f"""
                <div style="text-align: right;">
                    <span class="risk-badge {r_color}">{p['risk_level']}</span>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown(f"**Target:** `{selected_token}` | **Intent:** `{p['actor_intent']}`")
            st.divider()
            
            # Resumen Ejecutivo (Sin HTML complejo que rompa)
            st.markdown("#### 📝 Resumen Ejecutivo")
            # Limpiamos posibles tags HTML que el LLM haya alucinado en el texto
            clean_summary = p['summary'].replace("<h4>", "").replace("</h4>", "").replace("<p>", "").replace("</p>", "")
            st.info(clean_summary)
            
            # TTPs
            st.markdown("#### 🛠️ Tácticas Detectadas (TTPs)")
            if p['detected_ttps']:
                try:
                    ttps = p['detected_ttps'] if isinstance(p['detected_ttps'], list) else json.loads(p['detected_ttps'])
                    # Usamos st.pills (nuevo en Streamlit) o tags visuales
                    st.markdown(" ".join([f"`{t}`" for t in ttps]))
                except:
                    st.caption("No TTPs parsed.")
            else:
                st.caption("No se detectaron TTPs específicos.")

            st.markdown("---")
            
            # Metadatos del Modelo
            m1, m2 = st.columns(2)
            m1.caption(f"🧠 Modelo: {p['model_version']}")
            m2.caption(f"📅 Análisis: {p['analyzed_at']}")
        # --- ACTION: Re-Analyze Button ---
        st.write("")
        if st.button("🔄 Forzar Re-Análisis (LLM Local)", type="secondary"):
            with st.spinner(f"Consultando a Ollama... esto puede tardar unos segundos..."):
                result = analyze_single_bot(selected_token)
                
            if result:
                st.success("¡Perfil actualizado!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Fallo en el análisis. Revisa que Ollama esté corriendo y el bot tenga datos.")

    else:
        st.info("👈 Selecciona un bot de la lista para ver su informe de inteligencia.")
        st.markdown("""
        ### ¿Cómo funciona?
        1. **Ingesta:** El Listener captura logs crudos.
        2. **Parsing:** Se extraen entidades y patrones estructurales.
        3. **Inferencia:** Un LLM local (Llama 3) lee los patrones agregados.
        4. **Perfilado:** Se genera este informe de riesgo y capacidades.
        """)