import streamlit as st
import pandas as pd
import hashlib
from streamlit_agraph import agraph, Config, Node, Edge
import networkx as nx
import plotly.graph_objects as go # <--- NECESARIO PARA SANKEY
import botscape.shared.db.queries.intelligence as intel_queries


# --- IMPORTS DE LÓGICA ---
from botscape.dashboard.modules.graph_analytics import (
    get_full_graph_data,
    build_networkx_graph,
    get_cluster_subgraph,
    analyze_louvain_quality,
    calculate_advanced_centrality,
    simulate_node_removal,
    get_inter_community_edges
)
from botscape.dashboard.modules.community_intel import analyze_community_with_llm

st.set_page_config(page_title="Cluster Explorer", page_icon="🔭", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    .metric-container { background-color: #1E1E1E; padding: 15px; border-radius: 8px; border-left: 5px solid #3498DB; margin-bottom: 10px; }
    .louvain-info { padding: 10px; border-radius: 5px; font-size: 0.9rem; margin-top: 10px; }
    .louvain-good { background-color: rgba(39, 174, 96, 0.2); border: 1px solid #27AE60; color: #2ecc71; }
    .louvain-bad { background-color: rgba(231, 76, 60, 0.2); border: 1px solid #E74C3C; color: #e74c3c; }
    .cluster-header { background: linear-gradient(90deg, #0f2027 0%, #203a43 50%, #2c5364 100%); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white; display: flex; align-items: center; justify-content: space-between; }
</style>
""", unsafe_allow_html=True)

# --- 0. HELPER DE COLOR ---
def get_consistent_color(comm_id: int) -> str:
    """Genera un color hexadecimal único y determinista para un ID."""
    base_palette = [
        "#FF0055", "#00CCFF", "#CCFF00", "#AA00FF", "#FF9900", 
        "#00FF99", "#FF00FF", "#00FFFF", "#FFFF00", "#FF0000",
        "#00FF00", "#0000FF", "#800080", "#008080", "#800000",
        "#808000", "#000080", "#C0C0C0", "#FF69B4", "#4B0082",
        "#FF1493", "#00BFFF", "#32CD32", "#FFD700", "#8A2BE2",
        "#FF4500", "#2E8B57", "#DA70D6", "#1E90FF", "#DC143C"
    ]
    if comm_id < len(base_palette):
        return base_palette[comm_id]
    hash_object = hashlib.md5(str(comm_id).encode())
    return f"#{hash_object.hexdigest()[:6]}"

# --- 1. GESTIÓN DE ESTADO ---

if 'selected_token' not in st.session_state:
    st.session_state.selected_token = None

if 'louvain_cache' not in st.session_state:
    st.session_state.louvain_cache = {
        'root_token': None,
        'partition': {},
        'num_comm': 0,
        'q': 0.0,
        'comm_groups': {}
    }

# Carga de datos
bots_df, hash_edges_df, chat_edges_df, bot_tags_df = get_full_graph_data()
full_G, _, _ = build_networkx_graph(bots_df, hash_edges_df, chat_edges_df, bot_tags_df)

if not st.session_state.selected_token:
    st.info("Selecciona un bot para comenzar.")
    opts = bots_df['token'].tolist()
    sel = st.selectbox("Bot:", opts)
    if st.button("Explorar Cluster"):
        st.session_state.selected_token = sel
        st.rerun()
    st.stop()

root_token = st.session_state.selected_token
sub_G, nodes_viz, edges_viz = get_cluster_subgraph(full_G, root_token)

if not sub_G:
    st.error("Nodo aislado.")
    if st.button("Volver"):
        st.session_state.selected_token = None
        st.rerun()
    st.stop()

# --- 2. HEADER ---
st.markdown(f"""
<div class="cluster-header">
    <div>
        <h2 style="margin:0">🔭 Cluster: {root_token[:10]}...</h2>
        <small>Nodos: {sub_G.number_of_nodes()} | Aristas: {sub_G.number_of_edges()}</small>
    </div>
</div>
""", unsafe_allow_html=True)

# --- 3. PESTAÑAS ---
# AÑADIDA PESTAÑA 4: FLUJO (MACRO)
tab_viz, tab_math, tab_sim, tab_flow = st.tabs(["🕸️ Visualización & IA", "🧮 Matemáticas", "🧪 Simulación", "🌊 Flujo (Macro)"])

# === PESTAÑA 1: VISUALIZACIÓN ===
with tab_viz:
    c1, c2 = st.columns([3, 1])
    
    with c1:
        use_louvain = st.checkbox("🎨 Detección de Comunidades (Louvain)", value=True)
        final_nodes = nodes_viz
        
        # --- PERSISTENCIA LOUVAIN ---
        if use_louvain:
            if st.session_state.louvain_cache['root_token'] != root_token:
                partition, num_comm, q = analyze_louvain_quality(sub_G)
                df_temp = calculate_advanced_centrality(sub_G, partition)
                leaders = set(df_temp[df_temp['Rol'] == '👑 LÍDER']['Nodo'].tolist())
                
                comm_groups = {}
                for n_id, comm_id in partition.items():
                    ntype = sub_G.nodes[n_id].get('type')
                    if ntype == 'bot':
                        if comm_id not in comm_groups: comm_groups[comm_id] = []
                        comm_groups[comm_id].append(n_id)
                
                st.session_state.louvain_cache = {
                    'root_token': root_token,
                    'partition': partition,
                    'num_comm': num_comm,
                    'q': q,
                    'comm_groups': comm_groups,
                    'leaders': leaders
                }
            
            cache = st.session_state.louvain_cache
            partition = cache['partition']
            comm_groups = cache['comm_groups']
            leaders = cache['leaders']
            louvain_q = cache['q']

            # --- A. ENRIQUECIMIENTO VISUAL NODOS ---
            colored_nodes = []
            for n in nodes_viz:
                if n.id == root_token:
                    n.color = "#FFFFFF"; n.size=40; n.label=f"🎯 TARGET\n{n.label}"; n.shape="star"
                    colored_nodes.append(n)
                    continue
                
                cid = partition.get(n.id, 0)
                n.color = get_consistent_color(cid)
                
                if n.id in leaders:
                    n.size = 30 
                    n.borderWidth = 3
                    n.label = f"👑 {n.label}"
                
                colored_nodes.append(n)
            final_nodes = colored_nodes

            # --- B. ENRIQUECIMIENTO VISUAL ARISTAS ---
            special_edges = []
            inter_community_links = get_inter_community_edges(sub_G, partition)
            inter_comm_set = set(inter_community_links)
            inter_comm_set_rev = set([(v, u) for u, v in inter_community_links])

            for e in edges_viz:
                u, v = e.source, e.to
                if (u, v) in inter_comm_set or (u, v) in inter_comm_set_rev:
                    e.color = "#FFFFFF" 
                    e.width = 3 
                    e.dashes = True
                    e.label = "PUENTE"
                else:
                    e.color = "#444444" 
                    e.width = 1
                special_edges.append(e)
            final_edges = special_edges

        # Renderizar Grafo
        config = Config(width="100%", height=750, directed=False, physics=True, hierarchical=False,
                        nodeHighlightBehavior=True, highlightColor="#F7DC6F", backgroundColor="#0E1117",
                        physics_options={"solver": "forceAtlas2Based", "forceAtlas2Based": {"gravitationalConstant": -50, "springLength": 100, "damping": 0.4}})
        
        selection = agraph(nodes=final_nodes, edges=edges_viz, config=config)

    with c2:
        if use_louvain:
            st.markdown("### Calidad del Cluster")
            if louvain_q > 0.3:
                st.success(f"✅ Estructura Fuerte (Q={louvain_q:.2f})")
                st.caption("👑 Nodos grandes = Líderes. | ---- = Puentes.")
                st.markdown("---")
                st.markdown("#### 🧠 Community Intel")
                
                sel_comm_id = st.selectbox(
                    "Analizar Grupo:", 
                    options=sorted(comm_groups.keys()),
                    format_func=lambda x: f"Comunidad {x} ({len(comm_groups[x])} bots)",
                    key=f"sel_comm_{root_token}"
                )
                
                target_tokens = comm_groups[sel_comm_id]
                color_hex = get_consistent_color(sel_comm_id)
                st.markdown(f"""<div style="background:{color_hex}; padding:5px; border-radius:5px; color:black; text-align:center; font-weight:bold;">Color Grupo</div>""", unsafe_allow_html=True)
                
                if st.button("🧠 Interrogar con IA", type="primary", use_container_width=True):
                    with st.spinner("Analizando..."):
                        analysis = analyze_community_with_llm(target_tokens)
                    
                    if "error" in analysis:
                        st.error(analysis["error"])
                    else:
                        st.info(f"🤖 **Hipótesis:** {analysis.get('hypothesis')}")
                        if 'keywords' in analysis:
                            st.write("Keywords: " + ", ".join(analysis['keywords']))
                
                st.markdown("---")
                with st.expander(f"🔎 Miembros ({len(target_tokens)})", expanded=True):
                    cluster_bots_df = bots_df[bots_df['token'].isin(target_tokens)][['token', 'is_active']]
                    selection_df = st.dataframe(
                        cluster_bots_df,
                        column_config={"token": "Token", "is_active": "Activo"},
                        use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True, height=250
                    )
                    if selection_df.selection['rows']:
                        idx = selection_df.selection['rows'][0]
                        st.session_state.selected_token = cluster_bots_df.iloc[idx]['token']
                        st.switch_page("pages/2_Bots.py")
            else:
                st.warning(f"⚠️ Estructura Débil (Q={louvain_q:.2f})")
        
        st.markdown("---")
        if selection:
            node_data = full_G.nodes.get(selection, {})
            ntype = node_data.get('type', 'unknown')
            st.subheader("Inspector")
            st.code(selection)
            if ntype == 'actor': st.error("👤 Threat Actor")
            elif ntype == 'infra': st.success("📢 Infraestructura")
            elif ntype == 'bot': 
                st.info("🤖 Bot")
                if selection != root_token and st.button("Pivotar"):
                    st.session_state.selected_token = selection
                    st.rerun()

# === PESTAÑA 2: MATEMÁTICAS ===
with tab_math:
    st.markdown("### 📊 Métricas de Centralidad")
    current_partition = st.session_state.louvain_cache.get('partition') if use_louvain else None
    df_cen = calculate_advanced_centrality(sub_G, current_partition)
    
    st.dataframe(
        df_cen[['Nodo', 'Tipo', 'Comunidad', 'Rol', 'Betweenness', 'Conexiones']].sort_values(['Comunidad', 'Conexiones'], ascending=[True, False]),
        use_container_width=True, hide_index=True,
        column_config={
            "Comunidad": st.column_config.NumberColumn("Comunidad", format="%d"),
            "Betweenness": st.column_config.NumberColumn("Influencia", format="%.4f"),
            "Conexiones": st.column_config.ProgressColumn("Grado", min_value=0, max_value=int(df_cen['Conexiones'].max()))
        }
    )

# === PESTAÑA 3: SIMULACIÓN ===
with tab_sim:
    st.markdown("### 🧪 Simulación de Takedown")
    infra_candidates = [n for n in sub_G.nodes if sub_G.nodes[n].get('type') in ['infra', 'actor']]
    target = st.selectbox("🎯 Objetivo:", infra_candidates) if infra_candidates else None
    
    if target and st.button("Simular Eliminación"):
        n_before = nx.number_connected_components(sub_G)
        n_after, size_largest = simulate_node_removal(sub_G, target)
        impact = 100 - (size_largest / len(sub_G) * 100)
        c1, c2, c3 = st.columns(3)
        c1.metric("Fragmentación Antes", n_before)
        c2.metric("Fragmentación Después", n_after, delta=n_after-n_before)
        c3.metric("Impacto Red", f"{impact:.1f}%", delta=impact)
        if n_after > n_before: st.success("✅ Impacto Estructural Crítico")
        else: st.warning("⚠️ Impacto Bajo (Redundante)")

# === PESTAÑA 4: FLUJO POR COMUNIDADES (VISUALIZACIÓN ESTRATÉGICA) ===
with tab_flow:
    st.markdown("### 🌊 Community Flow Analysis")
    st.caption("Visualización del tráfico agrupado por Sub-Comunidades (Louvain). Simplifica la complejidad visual manteniendo la lógica del camino.")

    # 1. Recuperar la partición de Louvain de la sesión (calculada en Tab 1)
    # Esto es vital: necesitamos saber a qué grupo pertenece cada bot
    cache = st.session_state.louvain_cache
    partition = cache.get('partition', {})
    
    # Si no hay partición calculada, forzamos un fallback
    if not partition:
        st.warning("⚠️ Primero debes calcular las comunidades en la pestaña 'Visualización & IA'.")
    else:
        # 2. Controles visuales
        c_ctrl1, c_ctrl2 = st.columns(2)
        with c_ctrl1:
            top_n = st.slider("Top Fuentes/Destinos", 5, 30, 10)
        
        # 3. Extraer tokens y Consultar Tráfico
        cluster_tokens = [n for n, attr in sub_G.nodes(data=True) if attr.get('type') == 'bot']
        df_raw = intel_queries.get_cluster_flow_sankey(cluster_tokens, limit=1000)

        if df_raw.empty:
            st.info("No hay tráfico registrado.")
        else:
            # --- LÓGICA DE AGREGACIÓN POR COMUNIDAD ---
            # En lugar de usar el nombre del bot, usaremos "Comunidad X"
            
            agg_rows = []
            
            for _, row in df_raw.iterrows():
                # Determinar a qué comunidad pertenecen los bots involucrados
                
                # A) Origen de la línea
                src_label = row['source_label']
                # Si el origen es un bot (LATERAL o OUTBOUND), lo reemplazamos por su Comunidad
                if "🤖" in src_label: 
                    pass 

          
            bot_name_to_comm = {}
            for n_id, attr in sub_G.nodes(data=True):
                if attr.get('type') == 'bot':
                    # Intentamos matchear display_name o label
                    name = attr.get('label', n_id) 
                    comm_id = partition.get(n_id, 0)
                    bot_name_to_comm[name] = comm_id
                    bot_name_to_comm[n_id] = comm_id

            # Función para transformar etiqueta "🤖 BotName" -> "📦 Community 1"
            def transform_label(label, is_bot_role):
                if not is_bot_role: return label # Es víctima o canal
                
                clean_name = label.replace("🤖 ", "").strip()
                found_comm = -1
                for b_token, b_comm in partition.items():
                    # Si el token está en el grafo, miramos sus atributos
                    node_attr = sub_G.nodes.get(b_token, {})
                    b_display = node_attr.get('label', b_token)
                    
                    if b_display in clean_name or clean_name in b_display:
                        found_comm = b_comm
                        break
                
                if found_comm != -1:
                    return f"📦 COMUNIDAD {found_comm}"
                return "📦 GHOST BOTS" # Bots sin comunidad clara

            # --- CONSTRUCCIÓN DEL DATASET AGREGADO ---
            df_agg = df_raw.copy()
            
            # Aplicar transformación
            # INBOUND: Target es Bot -> Transformar Target
            mask_in = df_agg['direction'] == 'INBOUND'
            df_agg.loc[mask_in, 'target_label'] = df_agg.loc[mask_in, 'target_label'].apply(lambda x: transform_label(x, True))
            
            # OUTBOUND: Source es Bot -> Transformar Source
            mask_out = df_agg['direction'] == 'OUTBOUND'
            df_agg.loc[mask_out, 'source_label'] = df_agg.loc[mask_out, 'source_label'].apply(lambda x: transform_label(x, True))
            
            # LATERAL: Ambos son Bots -> Transformar Ambos
            mask_lat = df_agg['direction'] == 'LATERAL'
            df_agg.loc[mask_lat, 'source_label'] = df_agg.loc[mask_lat, 'source_label'].apply(lambda x: transform_label(x, True))
            df_agg.loc[mask_lat, 'target_label'] = df_agg.loc[mask_lat, 'target_label'].apply(lambda x: transform_label(x, True))

            # Agrupar por las nuevas etiquetas (SUMAR VOLUMEN)
            df_sankey = df_agg.groupby(['direction', 'source_label', 'target_label'])['volume'].sum().reset_index()
            
            # --- FILTRADO TOP N (Para Sources/Targets externos) ---
            # Solo filtramos lo que NO es comunidad
            final_rows = []
            
            # Top Sources
            in_sources = df_sankey[df_sankey['direction']=='INBOUND'].sort_values('volume', ascending=False)
            if not in_sources.empty:
                final_rows.extend(in_sources.head(top_n).to_dict('records'))
                # Others
                rest = in_sources.iloc[top_n:]
                if not rest.empty:
                    # Agrupar por comunidad destino para no romper el flujo
                    others_agg = rest.groupby('target_label')['volume'].sum().reset_index()
                    for _, r in others_agg.iterrows():
                        final_rows.append({
                            'direction': 'INBOUND', 
                            'source_label': '👥 OTHERS (Sources)', 
                            'target_label': r['target_label'], 
                            'volume': r['volume']
                        })

            # Lateral (Todo)
            final_rows.extend(df_sankey[df_sankey['direction']=='LATERAL'].to_dict('records'))

            # Top Targets
            out_targets = df_sankey[df_sankey['direction']=='OUTBOUND'].sort_values('volume', ascending=False)
            if not out_targets.empty:
                final_rows.extend(out_targets.head(top_n).to_dict('records'))
                # Others
                rest = out_targets.iloc[top_n:]
                if not rest.empty:
                    others_agg = rest.groupby('source_label')['volume'].sum().reset_index()
                    for _, r in others_agg.iterrows():
                        final_rows.append({
                            'direction': 'OUTBOUND', 
                            'source_label': r['source_label'], 
                            'target_label': '📢 OTHERS (Channels)', 
                            'volume': r['volume']
                        })
            
            df_viz = pd.DataFrame(final_rows)

            # --- RENDERIZADO ---
            # Asignar colores consistentes a las comunidades
            def get_color_node(lbl):
                if "COMUNIDAD" in lbl:
                    try:
                        cid = int(lbl.split(" ")[-1])
                        return get_consistent_color(cid)
                    except: return "#3498db"
                if "OTHERS" in lbl: return "#95a5a6"
                if "📢" in lbl: return "#e74c3c" # Rojo destino
                return "#2ecc71" # Verde origen

            all_labels = list(set(df_viz['source_label']).union(set(df_viz['target_label'])))
            
            # Lógica de Posición X Forzada (Clave para legibilidad)
            node_x = []
            node_y = []
            node_colors = []
            
            for lbl in all_labels:
                node_colors.append(get_color_node(lbl))
                if "COMUNIDAD" in lbl:
                    node_x.append(0.5) # Centro
                elif "📢" in lbl or "OTHERS (Channels)" in lbl:
                    node_x.append(0.99) # Derecha
                else:
                    node_x.append(0.01) # Izquierda
                node_y.append(None)

            # Mapeo de índices
            lbl_map = {l: i for i, l in enumerate(all_labels)}
            
            source_idxs = [lbl_map[row['source_label']] for _, row in df_viz.iterrows()]
            target_idxs = [lbl_map[row['target_label']] for _, row in df_viz.iterrows()]
            volumes = df_viz['volume'].tolist()
            
            # Colores de enlaces (Links)
            link_colors = []
            for _, row in df_viz.iterrows():
                if row['direction'] == 'INBOUND': link_colors.append("rgba(46, 204, 113, 0.3)")
                elif row['direction'] == 'LATERAL': link_colors.append("rgba(241, 196, 15, 0.5)") # Oro para inter-comunidad
                else: link_colors.append("rgba(231, 76, 60, 0.3)")

            fig = go.Figure(data=[go.Sankey(
                arrangement = "snap",
                node = dict(
                    pad = 20, thickness = 20,
                    line = dict(color = "black", width = 0.5),
                    label = all_labels,
                    color = node_colors,
                    x = node_x, y = node_y
                ),
                link = dict(
                    source = source_idxs, target = target_idxs,
                    value = volumes, color = link_colors
                )
            )])
            
            fig.update_layout(height=650, font_size=12, paper_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig, use_container_width=True)
            
            st.info("💡 **Guía:** Los nodos centrales representan **Comunidades de Bots** (agrupados por color/estructura). Las líneas amarillas indican tráfico entre diferentes comunidades del cluster.")

    