import pandas as pd
from streamlit_agraph import Node, Edge, Config

def calculate_tactical_role(row):
    """Heurística para determinar el rol del bot en la red."""
    v_in, v_out = row['volume_in'], row['volume_out']
    total = v_in + v_out
    if total == 0: return "💀 Dead"
    
    out_ratio = v_out / total
    if v_in > 0 and v_out == 0: return "📥 RECOLECTOR PURO (Sink)"
    elif v_out > 0 and v_in == 0: return "📢 EMISOR PURO (Spam/C2)"
    elif out_ratio < 0.1: return "💾 ALMACÉN (Hoarder)"
    elif out_ratio > 0.9: return "🗣️ COMANDANTE"
    else: return "🔄 PUENTE (Relay/Chat)"

def build_topology_graph_config(actor_id, role, df_bots, df_infra, df_partners, df_hubs):
    """Construye los Nodos y Aristas para Agraph."""
    nodes = []
    edges = []
    existing_ids = set()

    def add_node(nid, **kwargs):
        if nid not in existing_ids:
            nodes.append(Node(id=nid, **kwargs))
            existing_ids.add(nid)

    # 1. Actor Central
    center_color = "#e74c3c" if role == 'COMMANDER' else "#3498db"
    add_node(actor_id, label=f"ACTOR\n{actor_id}", size=45, shape="diamond", color=center_color, font={'color': 'white'})

    # 2. Bots
    for _, b in df_bots.iterrows():
        bid = b['token']
        bname = b['display_name'] if b['display_name'] else bid[:8]
        add_node(bid, label=f"🤖 {bname}", size=25, shape="dot", color="#7f8c8d")
        edges.append(Edge(source=actor_id, target=bid, color="#95a5a6", width=2))
        
        if b['c2_webhook_url']:
            wid = b['c2_webhook_url']
            add_node(wid, label="WEBHOOK", size=20, shape="square", color="#8e44ad")
            edges.append(Edge(source=bid, target=wid, label="C2", color="#8e44ad", dashes=True))

    # 3. Infraestructura (IPs)
    def get_flag_emoji(cc):
        return "".join(chr(ord(c.upper()) + 127397) for c in cc) if isinstance(cc, str) and len(cc)==2 else "🌍"

    for _, i in df_infra.iterrows():
        iid = i['ip_address']
        lbl = f"{get_flag_emoji(i['country_code'])}\n{iid}\n{i['asn']}"
        add_node(iid, label=lbl, size=22, shape="triangle", color="#27ae60")
        
        linked_bot = i['linked_bot']
        if linked_bot and linked_bot in existing_ids:
            edges.append(Edge(source=linked_bot, target=iid, label="HOSTING", color="#27ae60"))
        else:
            edges.append(Edge(source=actor_id, target=iid, label="DIRECT", color="#27ae60", dashes=True))

    # 4. Hubs y Partners (simplificado para brevedad)
    for _, h in df_hubs.iterrows():
        hid = h['hub_id']
        add_node(hid, label=f"📢 GRUPO\n{hid}", size=20, shape="hexagon", color="#e67e22")
        if h['connected_bot'] in existing_ids:
            edges.append(Edge(source=h['connected_bot'], target=hid, color="#e67e22", dashes=True))

    # Configuración física
    config = Config(
        width="100%", height=650, directed=True,
        physics={"enabled": True, "barnesHut": {"gravitationalConstant": -6000, "centralGravity": 0.3, "springLength": 250}},
        nodeHighlightBehavior=True, highlightColor="#F7A7A6"
    )
    return nodes, edges, config