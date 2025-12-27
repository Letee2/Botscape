import streamlit as st
import pandas as pd
import io
import os
from PIL import Image
from streamlit_agraph import agraph, Config
from datetime import date, timedelta
import plotly.express as px

# Imports de lógica de negocio
from botscape.dashboard.modules.graph_analytics import build_networkx_graph
import botscape.shared.db.queries as queries

# --- ESTILOS CSS CENTRALIZADOS ---
CSS_STYLES = """
<style>
    /* GLOBAL DARK TONE */
    .stApp { background-color: #0e1117; }
    
    /* HEADER WIDGET STYLES */
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: #0d1117; border-color: #30363d;
    }
    .stNumberInput input, .stDateInput input {
        background-color: #0d1117; border-color: #30363d; color: #c9d1d9;
    }

    /* BADGES & TAGS */
    .risk-badge { padding: 5px 14px; border-radius: 20px; font-weight: 800; font-size: 0.8rem; letter-spacing: 0.8px; text-transform: uppercase; display: inline-block; }
    .risk-CRITICAL { background: rgba(185, 28, 28, 0.2); color: #fecaca; border: 1px solid #b91c1c; }
    .risk-HIGH { background: rgba(194, 65, 12, 0.2); color: #fed7aa; border: 1px solid #c2410c; }
    .risk-MEDIUM { background: rgba(161, 98, 7, 0.2); color: #fef08a; border: 1px solid #a16207; }
    .risk-LOW { background: rgba(21, 128, 61, 0.2); color: #bbf7d0; border: 1px solid #15803d; }
    .risk-UNKNOWN { background: rgba(51, 65, 85, 0.3); color: #94a3b8; border: 1px solid #475569; }
    .tag-pill { background: #21262d; color: #c9d1d9; padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; border: 1px solid #30363d; margin-right: 4px;}

    /* CARDS */
    .intel-card { 
        background: #161b22; 
        border: 1px solid #30363d; 
        border-radius: 10px; 
        padding: 20px; 
        margin-bottom: 20px;
        height: 100%;
    }
    .section-header { color: #58a6ff; font-weight: 600; font-size: 1rem; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; text-transform: uppercase; letter-spacing: 1px;}
    
    /* CLUSTER TABLE */
    .cluster-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #0d1117; border-radius: 6px; overflow: hidden; border: 1px solid #21262d; }
    .cluster-table td { padding: 10px 12px; border-bottom: 1px solid #21262d; color: #8b949e; }
    .cluster-table td:first-child { color: #c9d1d9; font-weight: 600; width: 45%; }

    /* GRAFO */
    iframe {
        border: 1px solid #30363d !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        background-color: #0E1117;
    }
</style>
"""

# --- HELPERS VISUALES ---
def inject_css():
    st.markdown(CSS_STYLES, unsafe_allow_html=True)

def get_risk_badge(level):
    lvl = level.upper() if level else "UNKNOWN"
    return f'<span class="risk-badge risk-{lvl}">{lvl} RISK</span>'

def open_image_safe(path: str):
    try:
        with open(path, "rb") as f: return Image.open(io.BytesIO(f.read())).convert("RGB")
    except: return None

# --- COMPONENTES UI ---

def render_profiler_card(profile_data, df_tags):
    """Renderiza la tarjeta de Inteligencia Artificial (Resumen y Tags)."""
    st.markdown('<div class="intel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">🧠 Profiler AI</div>', unsafe_allow_html=True)
    
    if profile_data is not None:
        clean_summary = profile_data['summary'].replace("<h4>", "").replace("</h4>", "").replace("<p>", "").replace("</p>", "")
        st.info(clean_summary, icon="📝")
        
        # Tags
        if not df_tags.empty:
            tags_html = " ".join([f'<span class="tag-pill">{row["tag"]}</span>' for _, row in df_tags.iterrows()])
            st.markdown(f"<div style='margin-bottom:10px;'>{tags_html}</div>", unsafe_allow_html=True)
        
        st.markdown(f"<div style='font-size:0.8em; color:#555;'>Modelo: {profile_data['model_version']}</div>", unsafe_allow_html=True)
    else:
        st.warning("Perfil no generado.")
        st.markdown("<small>Ejecuta el análisis manual para obtener inteligencia.</small>", unsafe_allow_html=True)
        
    st.markdown('</div>', unsafe_allow_html=True)

def render_cluster_card(cluster_metrics, token):
    """Renderiza la tarjeta de métricas del cluster y el botón de navegación."""
    st.markdown('<div class="intel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📡 Cluster Intelligence</div>', unsafe_allow_html=True)
    
    c_status = "Nodo Aislado" if cluster_metrics['is_isolated'] else "Campaña Activa"
    c_style = 'style="color:#3fb950; font-weight:bold"' if cluster_metrics['is_isolated'] else 'style="color:#d29922; font-weight:bold"'
    
    st.markdown(f"""
    <table class="cluster-table">
        <tr><td>Estado del Nodo</td><td {c_style}>{c_status}</td></tr>
        <tr><td>Alcance (Bots)</td><td>{cluster_metrics['bots']}</td></tr>
        <tr><td>Infraestructura (Chats)</td><td>{cluster_metrics['chats']}</td></tr>
        <tr><td>Vectores (Hashes)</td><td>{cluster_metrics['hashes']}</td></tr>
    </table>
    """, unsafe_allow_html=True)
    
    st.write("")
    
    if not cluster_metrics['is_isolated']:
        if st.button("🔭 Explorar Cluster Completo", key="btn_cluster_explore", use_container_width=True):
            # Navegación a la nueva página
            st.session_state['cluster_root_token'] = token
            st.switch_page("pages/13_Cluster_Explorer.py")
    else:
        st.caption("El grafo adyacente representa la totalidad de la red conocida para este nodo.")
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_ego_graph(selected_token, t_hashes, t_chats):
    """Renderiza el grafo egocéntrico del bot seleccionado."""
    if not t_hashes and not t_chats:
        st.info("Sin topología de red disponible (Nodo Aislado).")
        return

    tokens_list = [selected_token]
    bots_df = queries.get_graph_nodes_bots(tokens_list)
    tags_df = queries.get_graph_nodes_tags(tokens_list)
    
    hash_edges_df = queries.get_graph_edges_hashes(tokens=tokens_list) if t_hashes else pd.DataFrame()
    chat_edges_df = queries.get_graph_edges_chats(tokens=tokens_list) if t_chats else pd.DataFrame()
    
    # Construcción grafo - CORREGIDO: Eliminados argumentos obsoletos
    _, nodes, edges = build_networkx_graph(
        bots_df, hash_edges_df, chat_edges_df, tags_df
    )
    
    config = Config(
        width="100%", height=600, 
        directed=False, physics=True, hierarchical=False, backgroundColor="#0E1117",
        node_options={"font": {"color": "#FFFFFF", "strokeWidth": 0, "multi": "html"}}
    )

    selection = agraph(nodes=nodes, edges=edges, config=config)
    
    # Interacción simple con el grafo ego
    if selection:
        if len(selection) == 64 and " " not in selection:
                vt_link = f"https://www.virustotal.com/gui/file/{selection}"
                st.toast(f"Hash seleccionado: {selection[:10]}...", icon="🦠")
                st.markdown(f"""
                <div style="margin-top:10px; padding:10px; background:#21262d; border-radius:6px; border:1px solid #b91c1c; color:#fecaca;">
                🦠 Malware: {selection[:12]}... <a href="{vt_link}" target="_blank" style="color:#fff;">🔎 VirusTotal ↗</a>
                </div>
                """, unsafe_allow_html=True)

def render_metrics_tabs(selected_token, start_iso, end_iso):
    """Renderiza las pestañas inferiores de detalles."""
    tab_ents, tab_media, tab_tpl, tab_raw = st.tabs(["🧩 Entidades", "🖼️ Media & Archivos", "📐 Plantillas", "📥 Export"])

    with tab_ents:
        ce1, ce2 = st.columns([1, 2])
        with ce1:
            df_etype = queries.get_bot_entity_types(selected_token, start_iso, end_iso)
            if not df_etype.empty:
                fig = px.pie(df_etype, names="etype", values="cnt", hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                fig.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True)
        with ce2:
            df_vals = queries.get_bot_top_entity_values(selected_token, start_iso, end_iso, limit=50)
            if not df_vals.empty:
                st.dataframe(df_vals, use_container_width=True, height=250)
            else:
                st.info("Sin datos.")

    # --- MODULO DE MEDIA Y ARCHIVOS MEJORADO ---
    with tab_media:
        df_media = queries.get_bot_media_gallery(selected_token, start_iso, end_iso, limit=200) # Límite aumentado
        
        if not df_media.empty:
            # 1. Definir extensiones visuales (añadido .webp y .gif)
            image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
            
            # 2. Clasificar
            df_media['is_image'] = df_media['path'].apply(
                lambda x: x is not None and str(x).lower().endswith(image_extensions)
            )
            
            images_df = df_media[df_media['is_image']]
            files_df = df_media[~df_media['is_image']]
            
            # --- SECCIÓN VISUAL ---
            if not images_df.empty:
                st.markdown("#### 📸 Galería de Imágenes")
                cols = st.columns(6)
                valid_imgs = 0
                
                for _, row in images_df.iterrows():
                    p = row["path"]
                    # Comprobación de existencia física
                    if p and os.path.exists(p):
                        im = open_image_safe(p)
                        if im:
                            with cols[valid_imgs % 6]: 
                                st.image(im, caption=os.path.basename(p), use_container_width=True)
                            valid_imgs += 1
                
                if valid_imgs == 0:
                    st.warning(f"⚠️ Hay {len(images_df)} imágenes registradas en la BBDD, pero los archivos no se encuentran en disco. Revisa los volúmenes de Docker.")
                
                st.divider()

            # --- SECCIÓN DE ARCHIVOS (Logs, Zips, Txt) ---
            if not files_df.empty:
                st.markdown("#### 📁 Archivos Exfiltrados / Logs")
                
                # Preparar tabla limpia
                display_files = files_df.copy()
                display_files['Archivo'] = display_files['path'].apply(lambda x: os.path.basename(str(x)) if x else "Desconocido")
                
                # Formatear tamaño
                def fmt_size(s):
                    return f"{s/1024:.1f} KB" if s else "0 KB"
                display_files['Tamaño'] = display_files['size'].apply(fmt_size)
                
                st.dataframe(
                    display_files[['date_utc', 'Archivo', 'mime', 'Tamaño']],
                    column_config={
                        "date_utc": "Fecha Detección",
                        "mime": "Tipo MIME"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            
            if images_df.empty and files_df.empty:
                st.info("No se pudo clasificar el contenido multimedia.")

        else:
            st.caption("Este bot no ha enviado adjuntos en el periodo seleccionado.")

    with tab_tpl:
        df_tpl = queries.get_bot_text_templates(selected_token, start_iso, end_iso)
        if not df_tpl.empty:
            st.dataframe(df_tpl, use_container_width=True)
        else:
            st.caption("Sin patrones.")

    with tab_raw:
        c_x1, c_x2 = st.columns(2)
        with c_x1:
            df_m = queries.export_bot_messages(selected_token, start_iso, end_iso)
            st.download_button("CSV Mensajes", df_m.to_csv(index=False).encode('utf-8'), "messages.csv", "text/csv")
        with c_x2:
            df_e = queries.export_bot_entities(selected_token, start_iso, end_iso)
            st.download_button("CSV Entidades", df_e.to_csv(index=False).encode('utf-8'), "entities.csv", "text/csv")