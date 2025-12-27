# botscape/dashboard/pages/9_Graph_Analysis.py

import streamlit as st
import pandas as pd
from streamlit_agraph import agraph, Config

# --- IMPORTS ---
from botscape.config import settings
from botscape.shared.db.caching import list_tokens
import botscape.shared.db.queries as queries
from botscape.dashboard.modules.graph_analytics import (
    build_networkx_graph,
    find_connected_components
)

st.set_page_config(page_title="Graph Analysis", page_icon="🕸️", layout="wide")

st.markdown("""
<style>
    .hero-graph {
        background: linear-gradient(135deg, #000000 0%, #1a1a1a 100%);
        border: 1px solid #333; border-radius: 12px; padding: 12px 16px;
        color: #e6f0ff; margin-bottom: 15px;
    }
</style>
<div class="hero-graph">
    <h3 style="margin:0">🕸️ Grafo de Inteligencia Unificado</h3>
    <small style="color:#888">Correlación total: Infraestructura, Malware, Atribución y C2.</small>
</div>
""", unsafe_allow_html=True)

# -----------------------------
# 1. Función Maestra de Carga
# -----------------------------
@st.cache_data(show_spinner="Fusionando capas de inteligencia...", ttl=600)
def get_graph_elements(t_tokens, t_hashes, t_chats, active_layers, agg_thresh, filter_tags):
    
    # A. Expansión de Vecindario
    final_tokens = list(t_tokens)
    if t_tokens or t_hashes:
        if t_hashes:
            df_h = queries.get_graph_edges_hashes(hashes=t_hashes)
            final_tokens.extend(df_h['token'].tolist())
        if t_chats:
            df_c = queries.get_graph_edges_chats(chat_ids=t_chats)
            final_tokens.extend(df_c['token'].tolist())
            
    final_tokens = list(set(final_tokens)) 

    if not final_tokens and (t_tokens or t_hashes): 
        return [], [], None

    # B. Data Fetching (Base)
    bots_df = queries.get_graph_nodes_bots(tokens=final_tokens if final_tokens else None)
    tags_df = queries.get_graph_nodes_tags(tokens=final_tokens if final_tokens else None)
    
    # C. Data Fetching Condicional
    hash_edges_df = pd.DataFrame()
    chat_edges_df = pd.DataFrame()
    social_edges_df = pd.DataFrame()
    operator_nodes_df = pd.DataFrame()
    c2_edges_df = pd.DataFrame()
    sim_edges_df = pd.DataFrame() # <--- Restaurado

    # Cargar capas activas
    if "Malware" in active_layers:
        hash_edges_df = queries.get_graph_edges_hashes(tokens=final_tokens if final_tokens else None)
        # Carga de similitud
        sim_edges_df = queries.get_similarity_edges(hashes=None) # Carga global o filtrada si optimizamos queries
    
    if "Chats" in active_layers:
        chat_edges_df = queries.get_graph_edges_chats(tokens=final_tokens if final_tokens else None)
    
    if "Operadores" in active_layers:
        operator_nodes_df = queries.get_graph_nodes_operators(tokens=final_tokens if final_tokens else None)
        social_edges_df = queries.get_graph_edges_social(tokens=final_tokens if final_tokens else None)
    
    if "C2 Webhooks" in active_layers:
        c2_edges_df = queries.get_graph_edges_c2(tokens=final_tokens if final_tokens else None)

    # D. Construcción (LLAMADA COMPLETA RESTAURADA)
    G, nodes, edges = build_networkx_graph(
        bots_df, hash_edges_df, chat_edges_df, tags_df, 
        
        sim_edges_df=None,          # <--- None por eficiencia, se puede activar para ver similitud entre muestras de malware
        social_edges_df=social_edges_df,    # <--- Argumento recuperado
        operator_nodes_df=operator_nodes_df,# <--- Argumento recuperado
        c2_edges_df=c2_edges_df,            # <--- Argumento recuperado
        
        chat_agglomerate_threshold=agg_thresh,
        filter_tags=filter_tags
    )
    return nodes, edges, G

# -----------------------------
# 2. Configuración Sidebar
# -----------------------------
st.sidebar.header("🔍 Configuración de Vista")

st.sidebar.subheader("Capas Visibles")
layer_options = ["Chats", "Malware", "Operadores", "C2 Webhooks"]
active_layers = st.sidebar.multiselect(
    "Selecciona capas:",
    options=layer_options,
    default=["Operadores", "C2 Webhooks", "Malware"]
)

st.sidebar.subheader("Filtrar Nodos")
all_tags_df = queries.get_graph_nodes_tags()
available_tags = sorted(all_tags_df['tag'].unique().tolist()) if not all_tags_df.empty else []
selected_tags = st.sidebar.multiselect("Por Etiqueta (Tag):", options=available_tags)

# --- D. Pivote ---
st.sidebar.markdown("---")
graph_mode = st.sidebar.radio("Modo de Carga", ["Pivote (Focalizado)", "Completo (Panorama Global)"])

target_tokens, target_hashes = [], []
G_logic = None
nodes, edges = [], []

if graph_mode.startswith("Pivote"):
    pivot_type = st.sidebar.radio("Pivote Inicial:", ["Bot Token", "Hash SHA256"])
    if pivot_type == "Bot Token":
        tokens = list_tokens()
        sel = st.sidebar.selectbox("Seleccionar Bot", options=tokens)
        if sel: 
            target_tokens = [sel]
            df_h = queries.get_bot_hashes(sel)
            if not df_h.empty: target_hashes = df_h['sample_sha256'].tolist()
    else: 
        sel = st.sidebar.text_input("Pegar Hash SHA256")
        if sel and len(sel) == 64: target_hashes = [sel]

    if target_tokens or target_hashes:
        nodes, edges, G_logic = get_graph_elements(
            target_tokens, target_hashes, [], active_layers, 10, selected_tags
        )

else: # MODO COMPLETO
    if st.sidebar.button("🚀 Renderizar Grafo Completo"):
        n, e, g = get_graph_elements(
            [], [], [], active_layers, 10, selected_tags
        )
        st.session_state['full_graph_unified'] = {'nodes': n, 'edges': e, 'G': g}
        st.rerun()

    if 'full_graph_unified' in st.session_state:
        data = st.session_state['full_graph_unified']
        nodes, edges, G_logic = data['nodes'], data['edges'], data['G']

# -----------------------------
# 3. Renderizado
# -----------------------------
col_graph, col_inspector = st.columns([3, 1.2])

with col_graph:
    if nodes:
        config = Config(
            width="100%", height=850, directed=False, physics=True, hierarchical=False,
            backgroundColor="#0E1117", nodeHighlightBehavior=True, highlightColor="#F7DC6F",
            physics_options={
                "solver": "forceAtlas2Based",
                "forceAtlas2Based": {
                    "theta": 0.6, "gravitationalConstant": -60, "centralGravity": 0.008,
                    "springLength": 150, "springConstant": 0.05, "damping": 0.4
                }
            }
        )
        selection_id = agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("👈 Configura los filtros o selecciona un pivote para visualizar.")
        selection_id = None

# -----------------------------
# 4. Inspector Lateral
# -----------------------------
with col_inspector:
    st.markdown("### 🕵️ Inspector")
    if selection_id:
        if ":" in selection_id and len(selection_id) > 20: 
            st.success("🤖 Bot")
            st.code(selection_id, language="text")
            if st.button("📂 Ver Perfil", use_container_width=True):
                st.session_state.selected_token = selection_id
                st.switch_page("pages/2_Bots.py")
        elif len(selection_id) == 64 and " " not in selection_id:
            st.error("🦠 Malware")
            st.code(selection_id[:12]+"...", language="text")
            st.markdown(f"[🔎 VirusTotal](https://www.virustotal.com/gui/file/{selection_id})")
        elif str(selection_id).lstrip("-").isdigit() and len(str(selection_id)) > 5:
            st.warning("💀 Operador / Canal")
            st.metric("ID Telegram", selection_id)
        elif str(selection_id).startswith("http"):
             st.info("📡 C2 Webhook")
             st.code(selection_id, language="text")
    else:
        st.caption("Selecciona un nodo para ver detalles.")
        if G_logic:
            st.markdown("---")
            st.markdown("**Resumen del Grafo Actual**")
            st.markdown(f"- Nodos Totales: **{len(G_logic.nodes)}**")
            st.markdown(f"- Conexiones: **{len(G_logic.edges)}**")
            comps = find_connected_components(G_logic)
            if not comps.empty:
                st.markdown(f"- Campañas Aisladas: **{len(comps)}**")