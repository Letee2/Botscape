import streamlit as st
import pandas as pd
import time
from datetime import date, timedelta, datetime
from fpdf import FPDF  # pip install fpdf

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries.breach as queries
import botscape.shared.db.actions as actions

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Breach Monitor", page_icon="🛡️", layout="wide")

# Estilos CSS
st.markdown("""
<style>
    .metric-card { background-color: #1e2130; border: 1px solid #343a40; padding: 15px; border-radius: 10px; text-align: center; }
    .risk-critical { color: #ff4b4b; font-weight: 800; }
    .risk-high { color: #ffa726; font-weight: 800; }
    .asset-card { border-left: 4px solid #5c2b63; background-color: #181a26; padding: 15px; margin-bottom: 10px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Helpers: Generador de PDF
# -----------------------------
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Botscape - Reporte de Incidente', 0, 1, 'C')
        self.ln(10)

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 6, f"Activo: {title}", 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, body)
        self.ln()

def generate_pdf(asset_val, df_incidents):
    pdf = PDFReport()
    pdf.add_page()
    pdf.chapter_title(asset_val)
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f"Fecha de Generacion: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    pdf.cell(0, 10, f"Total Incidentes Detectados: {len(df_incidents)}", 0, 1)
    pdf.ln(5)
    
    for index, row in df_incidents.iterrows():
        risk = row['risk_level']
        date_str = row['date_utc'].strftime('%Y-%m-%d %H:%M') if isinstance(row['date_utc'], datetime) else str(row['date_utc'])
        
        # Encabezado del incidente
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"[{date_str}] Riesgo: {risk} | Bot: {row['token'][:15]}...", 0, 1)
        
        # Cuerpo (Snippet)
        pdf.set_font('Courier', '', 8)
        clean_snippet = row['snippet'].encode('latin-1', 'replace').decode('latin-1') # Sanitizar caracteres
        pdf.multi_cell(0, 4, f"Evidencia: {clean_snippet}")
        pdf.ln(3)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()) # Línea separadora
        pdf.ln(3)
        
    return pdf.output(dest='S').encode('latin-1')

# -----------------------------
# SECCIÓN 1: GESTIÓN DE LISTA DE VIGILANCIA (PRIORITARIO)
# -----------------------------
st.markdown("### 🛡️ Gestión de Lista de Vigilancia")

with st.expander("➕ Añadir / Eliminar Activos Monitorizados", expanded=True):
    c_add, c_list = st.columns([1, 1.5])
    
    # Formulario de Alta
    with c_add:
        st.markdown("#### Nuevo Activo")
        with st.form("add_asset_form", clear_on_submit=True):
            new_type = st.selectbox("Tipo", ["domain", "email", "ip", "url"])
            new_value = st.text_input("Valor", placeholder="ej: miempresa.com")
            new_desc = st.text_input("Descripción", placeholder="Dominio principal")
            
            if st.form_submit_button("Guardar Activo", type="primary"):
                if new_value:
                    if actions.add_monitored_asset(new_type, new_value, new_desc):
                        st.success(f"Guardado: {new_value}")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Error al guardar.")
                else:
                    st.warning("El valor es obligatorio.")

    # Lista Simple
    with c_list:
        st.markdown("#### Activos Actuales")
        df_assets = queries.get_monitored_assets()
        if df_assets.empty:
            st.info("Lista vacía.")
        else:
            st.dataframe(
                df_assets, 
                height=180, 
                use_container_width=True,
                hide_index=True,
                column_config={"id": None, "asset_value": "Activo", "asset_type": "Tipo"} 
            )
            # Botón de borrado rápido
            col_del1, col_del2 = st.columns([3, 1])
            to_del = col_del1.selectbox("Borrar activo:", options=df_assets['asset_value'], index=None, label_visibility="collapsed", placeholder="Selecciona para borrar...")
            if col_del2.button("🗑️", help="Eliminar activo seleccionado"):
                if to_del:
                    asset_id = df_assets[df_assets['asset_value'] == to_del].iloc[0]['id']
                    actions.delete_monitored_asset(asset_id)
                    st.success("Eliminado")
                    st.cache_data.clear()
                    st.rerun()

st.markdown("---")

# -----------------------------
# SECCIÓN 2: ANÁLISIS DE BRECHAS
# -----------------------------
st.subheader("🚨 Monitor de Incidentes")

# Filtros de Fecha
c_filt1, c_filt2 = st.columns([1, 3])
with c_filt1:
    days = st.slider("Ventana (días)", 1, 90, 30)
    start_date = date.today() - timedelta(days=days - 1)
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso = f"{(date.today() + timedelta(days=1)).isoformat()}T00:00:00Z"

# 1. Resumen Inteligente (Izquierda)
df_summary = queries.get_breach_summary(start_iso, end_iso)

col_selector, col_details = st.columns([1, 2.5])

with col_selector:
    st.markdown("#### 1. Selección de Activo")
    if df_summary.empty:
        st.success("✅ Sin incidentes en el periodo.")
    else:
        st.caption("Activos con actividad reciente:")
        
        # Crear opciones con formato rico "Activo (N alertas)"
        options_map = {
            f"{row['asset_value']} ({row['breach_count']} alertas)": row['asset_value'] 
            for _, row in df_summary.iterrows()
        }
        
        selected_label = st.radio(
            "Selecciona para analizar:",
            options=options_map.keys(),
            label_visibility="collapsed"
        )
        
        # Recuperar el valor real del activo seleccionado
        selected_asset = options_map.get(selected_label)

# 2. Detalles del Activo (Derecha)
with col_details:
    if not df_summary.empty and selected_asset:
        st.markdown(f"#### 2. Análisis: `{selected_asset}`")
        
        # Cargar detalles específicos
        df_incidents = queries.find_breaches_by_asset(selected_asset, start_iso, end_iso)
        
        # Botón de Reporte PDF
        col_tools1, col_tools2 = st.columns([3, 1])
        with col_tools2:
            pdf_bytes = generate_pdf(selected_asset, df_incidents)
            st.download_button(
                label="📄 Exportar PDF",
                data=pdf_bytes,
                file_name=f"report_{selected_asset}_{date.today()}.pdf",
                mime='application/pdf',
                use_container_width=True
            )

        # Tabla de Incidentes
        if not df_incidents.empty:
            # Formatear para display
            df_display = df_incidents.copy()
            df_display['date_utc'] = pd.to_datetime(df_display['date_utc']).dt.strftime('%Y-%m-%d %H:%M')
            
            # Badge de Riesgo Visual
            def risk_badge(val):
                colors = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
                return f"{colors.get(val, '⚪')} {val}"
            
            df_display['Riesgo'] = df_display['risk_level'].apply(risk_badge)

            event = st.dataframe(
                df_display[['Riesgo', 'date_utc', 'token', 'actor_intent', 'snippet']],
                column_config={
                    "token": st.column_config.TextColumn("Bot Source", width="small"),
                    "snippet": st.column_config.TextColumn("Evidencia (Contexto)", width="large"),
                    "actor_intent": "Intención"
                },
                use_container_width=True,
                height=400,
                selection_mode="single-row",
                on_select="rerun",
                hide_index=True
            )
            
            # Panel de Acción Rápida (Al hacer click en una fila)
            if event.selection['rows']:
                idx = event.selection['rows'][0]
                row_data = df_incidents.iloc[idx]
                
                with st.container(border=True):
                    st.markdown("**Investigación Rápida**")
                    b1, b2 = st.columns(2)
                    if b1.button("🔍 Perfil del Bot", use_container_width=True):
                        st.session_state['selected_token'] = row_data['token']
                        st.switch_page("pages/2_Bots.py")
                    if b2.button("💬 Ver Mensaje Original", use_container_width=True):
                        st.session_state['jump_to_id'] = int(row_data['message_pk'])
                        st.session_state['token_selector'] = row_data['token']
                        st.switch_page("pages/3_Messages.py")