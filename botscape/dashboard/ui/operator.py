# botscape/dashboard/ui/operator.py
import streamlit as st
import plotly.graph_objects as go
from streamlit_agraph import agraph, Node, Edge, Config

# EN: botscape/dashboard/ui/operator.py
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

def render_network_graph(actor_id, role, df_bots, df_infra, df_partners, df_hubs):
    """
    Renderiza el grafo interactivo pero FORZANDO una jerarquía visual
    de Izquierda a Derecha (Hierarchical Layout).
    """
    nodes = []
    edges = []
    existing_ids = set()

    def add_node(nid, label, **kwargs):
        if nid not in existing_ids:
            # Quitamos 'level' de kwargs para pasarlo explícitamente si hiciera falta, 
            # pero agraph lo lee de las config del nodo
            nodes.append(Node(id=nid, label=label, **kwargs))
            existing_ids.add(nid)

    # 1. NIVEL 1: PARTNERS (Izquierda del todo)
    # Los hacemos más pequeños para que no ocupen tanto si hay muchos
    for _, p in df_partners.iterrows():
        pid = p['partner_id']
        short_label = f"👤 {pid[:6]}.."
        
        # level=1 fuerza que estén a la izquierda
        add_node(pid, label=short_label, size=15, shape="star", color="#FBC02D", level=1) 
        
        # Conexión Partner -> Bot
        if p['shared_token']:
            edges.append(Edge(source=pid, target=p['shared_token'], color="#FBC02D", dashes=True))

    # 2. NIVEL 2: EL ACTOR (Centro de Mando)
    center_color = "#D32F2F" if role=='COMMANDER' else "#1976D2"
    add_node(actor_id, label=f"👹 ACTOR\n{actor_id[:6]}", size=40, shape="diamond", color=center_color, font={'color': 'white'}, level=2)

    # 3. NIVEL 3: BOTS (La Flota)
    for _, b in df_bots.iterrows():
        bid = b['token']
        label = b['display_name'] if b['display_name'] else bid[:8]
        
        # level=3 fuerza que estén a la derecha del actor
        add_node(bid, label=f"🤖 {label}", size=25, shape="dot", color="#455A64", level=3)
        
        # Actor -> Bot
        edges.append(Edge(source=actor_id, target=bid, color="#777777", width=2))

        # C2 (Nivel 4)
        if b.get('c2_webhook_url'):
            wid = b['c2_webhook_url']
            add_node(wid, label="🕸️ C2", size=15, shape="square", color="#E64A19", level=4)
            edges.append(Edge(source=bid, target=wid, label="HOOK", color="#E64A19", dashes=True))

    # 4. NIVEL 4: INFRAESTRUCTURA Y CANALES (Derecha del todo)
    
    # Infra (IPs)
    for _, i in df_infra.iterrows():
        iid = i['ip_address']
        label = f"🌍 {i.get('country_code','IP')}\n{iid}"
        add_node(iid, label=label, size=20, shape="triangle", color="#E64A19", level=4)
        
        if i.get('linked_bot') in existing_ids:
            edges.append(Edge(source=i['linked_bot'], target=iid, color="#E64A19"))

    # Hubs (Canales)
    for _, h in df_hubs.iterrows():
        hid = h['hub_id']
        label = f"📢 {str(hid)[:10]}"
        add_node(hid, label=label, size=18, shape="hexagon", color="#2E7D32", level=4)
        
        if h['connected_bot'] in existing_ids:
            edges.append(Edge(source=h['connected_bot'], target=hid, color="#2E7D32"))

    # --- CONFIGURACIÓN JERÁRQUICA (LA CLAVE) ---
    config = Config(
        width="100%",
        height=700,
        directed=True, 
        physics=False, # Desactivamos física de rebote para que se queden quietos en su nivel
        hierarchical={
            "enabled": True,
            "levelSeparation": 250,  # Distancia horizontal entre capas (Actor <-> Bot)
            "nodeSpacing": 60,       # Distancia vertical entre nodos (evita torres gigantes)
            "treeSpacing": 200,      # Distancia entre árboles distintos
            "direction": "LR",       # Left to Right (Izquierda a Derecha)
            "sortMethod": "directed", # Ordenar basado en las flechas
            "shakeTowards": "roots"   # Compactar hacia el origen
        },
        nodeHighlightBehavior=True, 
        highlightColor="#F7A7A6"
    )

    return agraph(nodes=nodes, edges=edges, config=config)
def render_sankey_diagram(actor_id, df_flow, bot_resolver, known_bot_ids):
    all_labels, source_indices, target_indices, values, colors = [], [], [], [], []
    def get_idx(label):
        if label not in all_labels: all_labels.append(label)
        return all_labels.index(label)
    
    actor_label = f"👹 ACTOR: {actor_id[:6]}.."
    
    for _, row in df_flow.iterrows():
        vol, via_bot_name = row['volume'], row['via_bot_name']
        via_bot_label = f"🤖 {via_bot_name}"
        remote_id = str(row['remote_entity'])
        via_bot_id = bot_resolver.get(via_bot_name)
        is_self_talk = (via_bot_id == remote_id)
        
        if remote_id in known_bot_ids:
            remote_label = f"⚙️ INTERNAL: {remote_id}"
            link_color = "rgba(241, 196, 15, 0.4)" 
        elif row['remote_type'] == 'USER':
            remote_label = f"👤 {remote_id}" 
            link_color = "rgba(39, 174, 96, 0.4)" 
        else:
            remote_label = f"📢 {remote_id}"
            link_color = "rgba(231, 76, 60, 0.4)" 

        if row['direction'] == 'INBOUND':
            if is_self_talk:
                source_indices.append(get_idx(via_bot_label))
                target_indices.append(get_idx(actor_label))
                values.append(vol)
                colors.append("rgba(241, 196, 15, 0.6)")
            else:
                source_indices.append(get_idx(remote_label))
                target_indices.append(get_idx(via_bot_label))
                values.append(vol)
                colors.append(link_color)
                source_indices.append(get_idx(via_bot_label))
                target_indices.append(get_idx(actor_label))
                values.append(vol)
                colors.append(link_color.replace("0.4", "0.6"))

        elif row['direction'] == 'OUTBOUND':
            source_indices.append(get_idx(actor_label))
            target_indices.append(get_idx(via_bot_label))
            values.append(vol)
            colors.append("rgba(52, 152, 219, 0.4)")
            source_indices.append(get_idx(via_bot_label))
            target_indices.append(get_idx(remote_label))
            values.append(vol)
            colors.append(link_color)

    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=all_labels, color="#58a6ff"),
        link=dict(source=source_indices, target=target_indices, value=values, color=colors)
    )])
    fig.update_layout(height=600, paper_bgcolor='rgba(0,0,0,0)', font_color="white", title_text="Diagrama de Flujo (Clean View)")
    st.plotly_chart(fig, use_container_width=True)
    # LEYENDA TÉCNICA
    st.markdown("""
    <div style="display: flex; justify-content: center; gap: 20px; font-size: 14px; margin-top: 10px;">
        <span style="color: #00CC96;">■ <b>Fuente Externa (Verde):</b> Usuarios/IDs desconocidos inyectando datos.</span>
        <span style="color: #F1C40F;">■ <b>Infraestructura (Amarillo):</b> Tráfico lateral entre bots o auto-gestión.</span>
        <span style="color: #3498DB;">■ <b>Actor (Azul):</b> Interacción directa del operador.</span>
        <span style="color: #E74C3C;">■ <b>Destino Final (Rojo):</b> Canales/Grupos donde se vuelcan los datos.</span>
    </div>
    """, unsafe_allow_html=True)

def render_topology_table(df_topo):
    # Limpieza de datos visuales
    max_in = max(1, int(df_topo['volume_in'].max()))
    max_out = max(1, int(df_topo['volume_out_channels'].max()))

    st.dataframe(
        df_topo[['bot_name', 'volume_in', 'volume_out_channels', 'main_destination', 'total_channels']],
        column_config={
            "bot_name": "Infraestructura (Bot)",
            "volume_in": st.column_config.ProgressColumn("📥 Input Externo", format="%d", min_value=0, max_value=max_in),
            "volume_out_channels": st.column_config.ProgressColumn("📢 Output (Canales)", format="%d", min_value=0, max_value=max_out),
            "main_destination": st.column_config.TextColumn("🎯 Destino Principal (ID Canal)"),
            "total_channels": st.column_config.NumberColumn("Num. Destinos")
        },
        use_container_width=True, height=400, hide_index=True
    )


def render_architectural_graph(actor_id, role, df_bots, df_infra, df_partners, df_hubs):
    """
    Renderiza un grafo topológico compactado usando Clusters para evitar
    la alineación vertical infinita.
    """
    
    # 1. Configuración Global para "Diagonal/Compacto"
    # newrank=true permite mezclar rangos entre clusters
    # pack=true intenta compactar el resultado final
    # ratio=fill intenta llenar el espacio disponible
    dot = """
    digraph G {
        rankdir=LR; 
        splines=ortho; 
        nodesep=0.2;      /* Separación vertical mínima entre nodos */
        ranksep=0.8;      /* Separación horizontal entre capas */
        bgcolor="transparent";
        compound=true;    /* Permite flechas entre clusters */
        newrank=true;     /* Algoritmo de ranking mejorado */
        pack=true;        /* Empaquetado agresivo */
        packmode="clust"; /* Empaquetar por clusters */

        /* ESTILOS MINIATURA (Para que quepan muchos) */
        node [
            shape=box, 
            style="filled,rounded", 
            fontname="Sans-Serif", 
            fontsize=8,       /* Fuente pequeña */
            fontcolor="white",
            penwidth=0,
            margin=0.1,       /* Márgenes internos reducidos */
            height=0.4        /* Altura fija pequeña */
        ];
        edge [
            color="#555555", 
            penwidth=0.8, 
            arrowsize=0.6
        ];
    """

    # Diccionario de mapeo Token -> ID
    token_map = {} 
    
    # --- ZONA 1: PARTNERS (CLUSTER EXTERNO) ---
    # Al ponerlos en un cluster, Graphviz intenta hacer un cuadrado con ellos
    # en lugar de una línea vertical.
    dot += """
    subgraph cluster_partners {
        label="Fuentes Externas (Partners)";
        style=dashed; color="#444444"; fontcolor="#888888"; fontsize=9;
        node [shape=star, fillcolor="#FBC02D", fontcolor="black", width=0.8, fixedsize=false];
    """
    
    if not df_partners.empty:
        for i, row in df_partners.iterrows():
            pid = f"PARTNER_{i}"
            # Truncamos ID visualmente
            label = str(row['partner_id'])[:6]
            shared_token = row['shared_token']
            
            dot += f'        {pid} [label="{label}.."];\n'
    
    dot += "    }\n" # Fin Cluster Partners


    # --- ZONA 2: ACTOR (CLUSTER MANDO) ---
    dot += """
    subgraph cluster_actor {
        label=""; penwidth=0;
        node [shape=circle, fontsize=10, width=1.0, fixedsize=true];
    """
    actor_color = "#D32F2F" if role == 'COMMANDER' else "#1976D2"
    dot += f'        ACTOR [label="ACTOR\\nID:{actor_id[:5]}", fillcolor="{actor_color}"];\n'
    dot += "    }\n"


    # --- ZONA 3: BOTS (CLUSTER FLOTA) ---
    dot += """
    subgraph cluster_fleet {
        label="Infraestructura (Bots)";
        style=filled; color="#263238"; fontcolor="#cfd8dc"; fontsize=9;
        node [shape=box, fillcolor="#455A64", width=1.5, fixedsize=false];
    """
    
    bot_nodes = []
    for i, row in df_bots.iterrows():
        bid = f"BOT_{i}"
        token = row['token']
        token_map[token] = bid
        
        # Nombre limpio y corto
        name = row['display_name'] if row['display_name'] else "Unknown"
        label = name[:12].replace('"', "'")
        
        dot += f'        {bid} [label="{label}"];\n'
        bot_nodes.append(bid)

    dot += "    }\n" # Fin Cluster Bots


    # --- ZONA 4: SALIDA (INFRA + CANALES) ---
    dot += """
    subgraph cluster_output {
        label="Destinos & Infra";
        style=invis;
        node [shape=folder, fillcolor="#2E7D32", fontsize=8, width=1.2];
    """
    
    # Canales/Hubs
    if not df_hubs.empty:
        for i, row in df_hubs.iterrows():
            hid = f"HUB_{i}"
            label = str(row['hub_id'])[:10]
            dot += f'        {hid} [label="GRP: {label}"];\n'

    # Infra (IPs)
    dot += '        node [shape=note, fillcolor="#E64A19", fontcolor="white"];\n'
    if not df_infra.empty:
        for i, row in df_infra.iterrows():
            iid = f"INFRA_{i}"
            ip = row['ip_address']
            dot += f'        {iid} [label="{ip}"];\n'

    # C2
    for i, row in df_bots.iterrows():
        if row.get('c2_webhook_url'):
            c2_id = f"C2_{i}"
            dot += f'        {c2_id} [label="C2 WEBHOOK"];\n'

    dot += "    }\n" # Fin Cluster Output


    # --- CONEXIONES (ARISTAS) ---
    
    # 1. Partner -> Bot
    if not df_partners.empty:
        for i, row in df_partners.iterrows():
            pid = f"PARTNER_{i}"
            token = row['shared_token']
            if token in token_map:
                bid = token_map[token]
                # ltail permite conectar desde el cluster si se quisiera, 
                # pero conectamos nodo a nodo para precisión
                dot += f'    {pid} -> {bid} [style=dashed, color="#FBC02D"];\n'

    # 2. Actor -> Bot
    for bid in bot_nodes:
        dot += f'    ACTOR -> {bid} [weight=2];\n'

    # 3. Bot -> Hub
    if not df_hubs.empty:
        for i, row in df_hubs.iterrows():
            hid = f"HUB_{i}"
            token = row['connected_bot']
            if token in token_map:
                bid = token_map[token]
                dot += f'    {bid} -> {hid} [color="#2E7D32"];\n'

    # 4. Bot -> Infra/C2
    if not df_infra.empty:
        for i, row in df_infra.iterrows():
            iid = f"INFRA_{i}"
            linked = row.get('linked_bot')
            if linked in token_map:
                bid = token_map[linked]
                dot += f'    {bid} -> {iid} [style=dotted, color="#E64A19"];\n'

    for i, row in df_bots.iterrows():
        if row.get('c2_webhook_url'):
            c2_id = f"C2_{i}"
            token = row['token']
            if token in token_map:
                bid = token_map[token]
                dot += f'    {bid} -> {c2_id} [style=dotted, color="#E64A19"];\n'

    dot += "}"
    
    # Renderizar con ancho expandido para aprovechar la diagonalidad de los clusters
    st.graphviz_chart(dot, use_container_width=True)