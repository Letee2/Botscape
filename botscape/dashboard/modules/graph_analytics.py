import networkx as nx
import pandas as pd
from streamlit_agraph import Node, Edge
import logging
import streamlit as st

from community import community_louvain

from botscape.shared.db.caching import read_sql

# --- CONFIGURACIÓN DE ESTILO ---
CAMPAIGN_PALETTE = [
    "#E74C3C", "#8E44AD", "#3498DB", "#16A085", "#F39C12", 
    "#D35400", "#C0392B", "#9B59B6", "#2980B9", "#1ABC9C"
]

NODE_STYLES = {
    'bot_active':   {'color': '#2E86C1', 'shape': 'dot',    'size': 20}, # Azul
    'bot_inactive': {'color': '#85929E', 'shape': 'dot',    'size': 20}, # Gris
    'hash':         {'color': '#C0392B', 'shape': 'square', 'size': 15}, # Rojo Oscuro
    'actor':        {'color': '#E74C3C', 'shape': 'diamond',  'size': 22}, # Rojo Brillante (Threat Actor)
    'infra':        {'color': '#27AE60', 'shape': 'triangle', 'size': 18}, # Verde (Canal/Grupo)
    'agglomerate':  {'color': '#F39C12', 'shape': 'hexagon',  'size': 25}, # Naranja
    'operator':     {'color': '#E74C3C', 'shape': 'image',    'size': 30}, # Icono Hacker
    'c2':           {'color': '#8E44AD', 'shape': 'square',   'size': 25}  # Morado C2
}

# --- 1. DATA FETCHING ---

@st.cache_data(show_spinner="Cargando topología de la red...", ttl=3600)
def get_full_graph_data():
    """Obtiene datos base para el grafo, incluyendo chat_type."""
    bots_df = read_sql("SELECT token, is_active FROM bots;")
    hash_edges_df = read_sql("SELECT token, sample_sha256 FROM hash_origin;")
    chat_edges_df = read_sql("SELECT DISTINCT token, chat_id, chat_type FROM messages WHERE chat_id IS NOT NULL AND token IS NOT NULL;")
    bot_tags_df = read_sql("SELECT t.tag, m.bot_token AS token FROM bot_tags t JOIN bot_tag_map m ON t.id = m.tag_id;")
    return bots_df, hash_edges_df, chat_edges_df, bot_tags_df

# --- 2. CONSTRUCCIÓN DEL GRAFO ---

def _safe_str(val):
    return str(val).strip()

def _get_campaign_color(idx):
    return CAMPAIGN_PALETTE[idx % len(CAMPAIGN_PALETTE)]

def _add_bots(G, bots_df, bot_tags_df, filter_tags=None):
    if bots_df.empty: return set()
    
    bot_tag_map = {}
    if not bot_tags_df.empty:
        bot_tag_map = bot_tags_df.groupby('token')['tag'].apply(list).to_dict()

    added = set()
    for _, row in bots_df.iterrows():
        token = _safe_str(row['token'])
        tags = bot_tag_map.get(token, [])
        
        # Filtro de Tags (para el grafo completo filtrado)
        if filter_tags and not any(t in filter_tags for t in tags):
            continue

        label = f"[{tags[0][:4].upper()}]" if tags else "BOT"
        label += f"\n{token[:6]}..."
        
        style = NODE_STYLES['bot_active'] if row['is_active'] else NODE_STYLES['bot_inactive']
        
        G.add_node(token, type='bot', label=label, 
                   base_color=style['color'], shape=style['shape'], size=style['size'])
        added.add(token)
    return added

def _add_hashes(G, df, valid_bots):
    if df.empty: return
    style = NODE_STYLES['hash']
    for _, row in df.iterrows():
        token = _safe_str(row['token'])
        if token not in valid_bots: continue
        h = _safe_str(row['sample_sha256'])
        if h not in G:
            G.add_node(h, type='hash', label=f"MALWARE\n{h[:6]}...", 
                       base_color=style['color'], shape=style['shape'], size=style['size'])
        G.add_edge(token, h, type='hash_link', color="#922B21")

def _add_chats(G, df, valid_bots, threshold=15):
    if df.empty: return
    valid_rows = df[df['token'].isin(valid_bots)].copy()
    
    counts = valid_rows.groupby('token')['chat_id'].nunique()
    massive_bots = set(counts[counts > threshold].index)
    normal_traffic = valid_rows[~valid_rows['token'].isin(massive_bots)]
    
    chat_types = df.set_index('chat_id')['chat_type'].to_dict()

    for _, row in normal_traffic.iterrows():
        token = _safe_str(row['token'])
        c_id = _safe_str(row['chat_id'])
        c_type = chat_types.get(c_id, 'group')
        
        # Distinción Actor vs Infraestructura
        if c_type == 'private':
            style, ntype, label, ecol = NODE_STYLES['actor'], 'actor', f"👤 ACTOR\n{c_id}", "#E74C3C"
        else:
            style, ntype, label, ecol = NODE_STYLES['infra'], 'infra', f"📢 INFRA\n{c_id}", "#27AE60"
            
        if c_id not in G:
            G.add_node(c_id, type=ntype, label=label, chat_type=c_type,
                       base_color=style['color'], shape=style['shape'], size=style['size'])
        G.add_edge(token, c_id, type='chat_link', color=ecol)

    # Nodos Aglomerados
    style_agg = NODE_STYLES['agglomerate']
    for token in massive_bots:
        agg_id = f"agg_{token}"
        if agg_id not in G:
            G.add_node(agg_id, type='agglomerate', label=f"{counts[token]} Chats", 
                       base_color=style_agg['color'], shape=style_agg['shape'], size=style_agg['size'])
        G.add_edge(token, agg_id, type='agg_link', color="#F39C12", dashes=True)

def _add_strategic_layer(G, social_df, operator_df, c2_df, valid_bots):
    """Capa C2 y Social (Operadores confirmados)."""
    if not operator_df.empty and not social_df.empty:
        social_df['bot_token'] = social_df['bot_token'].astype(str)
        social_df['identity_id'] = social_df['identity_id'].astype(str)
        operator_df['telegram_id'] = operator_df['telegram_id'].astype(str)

        rels = social_df[social_df['bot_token'].isin(valid_bots)]
        relevant_ops = set(rels['identity_id'].unique())

        for _, row in operator_df.iterrows():
            op_id = row['telegram_id']
            if op_id in relevant_ops and op_id not in G:
                is_user = (row['type'] == 'USER')
                style = NODE_STYLES['operator'] if is_user else NODE_STYLES['infra']
                label = f"@{row['username']}" if row['username'] else f"ID:{op_id[:4]}.."
                img = "https://img.icons8.com/color/48/hacker.png" if is_user else ""
                
                G.add_node(op_id, type='operator', label=label, image=img, 
                           base_color=style['color'], shape=style['shape'], size=style['size'])
        
        for _, row in rels.iterrows():
            if row['identity_id'] in G:
                G.add_edge(row['bot_token'], row['identity_id'], type='social_link', color="#E74C3C", width=2)

    if not c2_df.empty:
        c2_df['token'] = c2_df['token'].astype(str)
        valid_c2 = c2_df[c2_df['token'].isin(valid_bots) & (c2_df['c2_webhook_url'].str.len() > 8)]
        style = NODE_STYLES['c2']
        
        for _, row in valid_c2.iterrows():
            url = row['c2_webhook_url']
            if url not in G:
                domain = url.split('/')[2] if '//' in url else url[:15]
                G.add_node(url, type='c2', label=f"📡 {domain}", 
                           base_color=style['color'], shape=style['shape'], size=style['size'])
            G.add_edge(row['token'], url, type='c2_link', color="#8E44AD", dashes=True)

def _add_similarity(G, sim_df):
    """Capa de Similitud (SSDeep/Imphash)."""
    if sim_df is None or sim_df.empty: return
    for _, row in sim_df.iterrows():
        h1, h2 = str(row['sha256_a']), str(row['sha256_b'])
        if h1 in G and h2 in G:
            label = f"{row['score']}%"
            G.add_edge(h1, h2, type='similarity', label=label, color="#F4D03F", dashes=True)

def _finalize_agraph(G, color_by_campaign=False):
    nodes, edges = [], []
    
    community_map = {}
    if color_by_campaign and len(G.nodes) > 0:
        comps = list(nx.connected_components(G))
        comps.sort(key=len, reverse=True)
        for i, comp in enumerate(comps):
            c = _get_campaign_color(i)
            for n in comp: community_map[n] = c

    for n_id, attr in G.nodes(data=True):
        final_color = community_map.get(n_id, attr.get('base_color', '#fff')) if color_by_campaign else attr.get('base_color', '#fff')
        
        nodes.append(Node(
            id=n_id,
            label=attr.get('label', str(n_id)),
            shape=attr.get('shape', 'dot'),
            size=attr.get('size', 15),
            color=final_color,
            image=attr.get('image', ''),
            font={'color': 'white', 'size': 10}
        ))
    for u, v, attr in G.edges(data=True):
        edges.append(Edge(
            source=str(u), target=str(v),
            color=attr.get('color', '#555'),
            width=attr.get('width', 1.5),
            dashes=attr.get('dashes', False),
            label=attr.get('label', '')
        ))
    return nodes, edges

# --- FUNCIÓN MAESTRA ---

def build_networkx_graph(
    bots_df, hash_edges_df, chat_edges_df, bot_tags_df,
    sim_edges_df=None,          
    social_edges_df=pd.DataFrame(),
    operator_nodes_df=pd.DataFrame(),
    c2_edges_df=pd.DataFrame(),
    chat_agglomerate_threshold=15,
    filter_tags=None,
    color_by_campaign=False   
):
    """
    Construye el grafo completo soportando TODAS las capas.
    """
    G = nx.Graph()
    
    # 1. Base
    valid_bots = _add_bots(G, bots_df, bot_tags_df, filter_tags)
    if not valid_bots: return G, [], []
    
    # 2. Táctica
    _add_hashes(G, hash_edges_df, valid_bots)
    _add_chats(G, chat_edges_df, valid_bots, chat_agglomerate_threshold)
    
    # 3. Estratégica (Todos los argumentos pasados correctamente)
    _add_strategic_layer(G, social_edges_df, operator_nodes_df, c2_edges_df, valid_bots)
    _add_similarity(G, sim_edges_df)
    
    # 4. Limpieza
    G.remove_nodes_from(list(nx.isolates(G)))
    
    # 5. Render
    nodes, edges = _finalize_agraph(G, color_by_campaign)
    
    return G, nodes, edges

# --- HELPERS ANALÍTICOS (Cluster Explorer) ---

def get_cluster_subgraph(full_G: nx.Graph, root_node: str):
    if root_node not in full_G: return None, [], []
    cluster_nodes = nx.node_connected_component(full_G, root_node)
    subG = full_G.subgraph(cluster_nodes).copy()
    nodes, edges = _finalize_agraph(subG)
    
    for n in nodes:
        if n.id == root_node:
            n.size, n.color, n.label = 40, "#F1C40F", f"📍 TARGET\n{n.label}"
            
    return subG, nodes, edges

def analyze_louvain_quality(G: nx.Graph):
    try:
        partition = community_louvain.best_partition(G)
        mod = community_louvain.modularity(partition, G)
        return partition, len(set(partition.values())), mod
    except: return {n:0 for n in G.nodes()}, 1, 0.0

def calculate_advanced_centrality(G: nx.Graph, partition: dict = None):
    deg = nx.degree_centrality(G)
    bet = nx.betweenness_centrality(G, k=min(len(G), 200))
    
    leaders = set()
    if partition:
        comm_max = {}
        for n, cid in partition.items():
            if deg[n] > comm_max.get(cid, (-1, -1))[1]:
                comm_max[cid] = (n, deg[n])
        leaders = {v[0] for v in comm_max.values()}

    data = []
    for n in G.nodes():
        row = {
            "Nodo": n,
            "Tipo": G.nodes[n].get('type', '?'),
            "Comunidad": partition.get(n, -1) if partition else -1,
            "Rol": "👑 LÍDER" if n in leaders else ("Puente" if bet[n] > 0.05 else "Miembro"),
            "Betweenness": bet[n],
            "Conexiones": len(list(G.neighbors(n)))
        }
        data.append(row)
    return pd.DataFrame(data).sort_values("Betweenness", ascending=False)

def simulate_node_removal(G, target):
    simG = G.copy()
    if target in simG: simG.remove_node(target)
    comps = list(nx.connected_components(simG))
    return len(comps), len(max(comps, key=len)) if comps else 0

def get_inter_community_edges(G, partition):
    return [(u,v) for u,v in G.edges() if u in partition and v in partition and partition[u] != partition[v]]

def analyze_structural_integrity(G: nx.Graph):
    if not nx.is_connected(G):
        G_cc = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    else:
        G_cc = G
    articulation_points = list(nx.articulation_points(G_cc))
    ap_data = [{"Nodo": n, "Tipo": G_cc.nodes[n].get('type', '?'), "Grado": G_cc.degree[n]} for n in articulation_points]
    bridges = list(nx.bridges(G_cc))
    bridge_data = [{"Origen": u, "Destino": v} for u, v in bridges]
    return pd.DataFrame(ap_data).sort_values('Grado', ascending=False), pd.DataFrame(bridge_data)

def find_connected_components(G):
    if not G: return pd.DataFrame()
    comps = list(nx.connected_components(G))
    res = [{"Cluster": i, "Nodos": len(c)} for i, c in enumerate(comps)]
    return pd.DataFrame(res).sort_values("Nodos", ascending=False)