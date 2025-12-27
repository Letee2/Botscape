# botscape/dashboard/ui/home.py
import streamlit as st
import plotly.express as px
import base64
import os
import numpy as np

# --- ESTILOS CSS (Command Center Theme) ---
CSS = """
<style>
    /* ACTION CARDS */
    .action-card {
        background: linear-gradient(145deg, #161b22, #0d1117);
        border: 1px solid #30363d; border-radius: 12px; padding: 15px;
        text-align: center; transition: transform 0.2s; height: 100%;
        display: flex; flex-direction: column; justify-content: center; align-items: center;
    }
    .action-card:hover {
        transform: translateY(-2px); border-color: #58a6ff; cursor: pointer;
        box-shadow: 0 4px 12px rgba(88, 166, 255, 0.15);
    }
    .action-icon { font-size: 1.8rem; margin-bottom: 8px; }
    .action-title { font-weight: 700; color: #e6edf3; font-size: 1rem; margin: 0; }
    .action-desc { color: #8b949e; font-size: 0.75rem; margin-top: 4px; }

    /* HERO UNIFICADO */
    .hero-container {
        display: flex; justify-content: space-between; align-items: center;
        padding: 15px 25px;
        background: linear-gradient(90deg, #0d1117 0%, #161b22 100%);
        border-bottom: 1px solid #30363d; border-radius: 0 0 15px 15px;
        margin-bottom: 20px;
        gap: 20px;
    }
    .hero-left { display: flex; align-items: center; min-width: 250px; }
    .hero-titles h1 { 
        margin: 0; font-size: 1.8rem; line-height: 1.1;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #4B7BFF); 
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; 
    }
    .hero-titles p { margin: 2px 0 0 0; color: #8b949e; font-size: 0.85rem; }
    
    /* KPI GRID */
    .hero-kpis { display: flex; gap: 20px; text-align: right; align-items: center; }
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-val { font-size: 1.4rem; font-weight: 700; color: #e6edf3; line-height: 1; }
    .kpi-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px;}
    .kpi-delta { font-size: 0.7rem; font-weight: 600; }
    .delta-pos { color: #3fb950; } .delta-neg { color: #f85149; } .delta-neu { color: #8b949e; }

    /* SPARKLINE CONTAINER */
    .spark-container {
        display: flex; flex-direction: column; align-items: flex-end;
        padding-left: 20px; border-left: 1px solid #30363d;
    }
    .spark-title { font-size: 0.7rem; color: #8b949e; margin-bottom: 5px; text-transform: uppercase; }

    /* LIVE WIRE INTERACTIVO */
    .live-row {
        display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 0.85rem; transition: background 0.1s;
    }
    .live-row:hover { background-color: #13181e; }
    .live-time { font-family: monospace; color: #58a6ff; width: 60px; font-weight: bold; flex-shrink: 0; }
    .live-icon { width: 30px; text-align: center; flex-shrink: 0; font-size: 1rem; }
    .live-snippet { 
        color: #c9d1d9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; 
        padding-left: 10px; font-family: monospace; font-style: italic; flex-grow: 1;
    }
</style>
"""

def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)

def get_img_as_base64(file_path):
    if not os.path.exists(file_path): return ""
    try:
        with open(file_path, "rb") as f: data = f.read()
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"
    except: return ""

def generate_sparkline_svg(df_daily, width=180, height=50):
    """Genera un SVG minimalista (Sparkline) a partir del DataFrame diario."""
    if df_daily.empty:
        return ""
    
    # Datos
    data = df_daily['msgs'].tolist()
    if not data: return ""
    
    # Normalización
    min_val, max_val = 0, max(data) if max(data) > 0 else 1
    points = []
    step_x = width / (len(data) - 1) if len(data) > 1 else width
    
    # Construir puntos poligonal
    # Coordenadas SVG: (0,0) es arriba-izquierda. Invertimos Y.
    for i, val in enumerate(data):
        x = i * step_x
        # Normalizar altura (dejando un margen de 2px)
        y = height - ((val - min_val) / (max_val - min_val) * (height - 4)) - 2
        points.append(f"{x:.1f},{y:.1f}")
    
    polyline = " ".join(points)
    
    # Relleno (cerrar el path)
    fill_path = f"0,{height} " + " ".join([p.replace(',', ' ') for p in points]) + f" {width},{height}"
    path_d = f"M {points[0]} L " + " L ".join(points[1:])
    
    # SVG String
    svg = f"""
    <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#58a6ff;stop-opacity:0.4" />
                <stop offset="100%" style="stop-color:#58a6ff;stop-opacity:0" />
            </linearGradient>
        </defs>
        <path d="M 0 {height} L {polyline.replace(',', ' ')} L {width} {height} Z" fill="url(#grad)" stroke="none" />
        <polyline points="{polyline}" style="fill:none;stroke:#58a6ff;stroke-width:2" />
    </svg>
    """
    return svg

def render_hero_unified(logo_path, start_date, end_date, kpis, df_daily):
    """
    Renderiza Header + KPIs + Sparkline Chart en una sola tarjeta.
    """
    # 1. Logo
    img_tag = ""
    b64_logo = get_img_as_base64(logo_path)
    if b64_logo:
        img_tag = f'<img src="{b64_logo}" style="width:60px; height:auto; margin-right:15px; border-radius:8px;">'

    # 2. Deltas
    def fmt_delta(val):
        if val > 0: return f'<span class="kpi-delta delta-pos">+{val}</span>'
        if val < 0: return f'<span class="kpi-delta delta-neg">{val}</span>'
        return '<span class="kpi-delta delta-neu">-</span>'

    # 3. KPIs
    bots_html = f'<div class="kpi-box"><span class="kpi-val">{kpis["bots"][0]}</span><span class="kpi-label">Bots {fmt_delta(kpis["bots"][1])}</span></div>'
    msgs_html = f'<div class="kpi-box"><span class="kpi-val">{kpis["msgs"][0]:,}</span><span class="kpi-label">Msgs {fmt_delta(kpis["msgs"][1])}</span></div>'
    ents_html = f'<div class="kpi-box"><span class="kpi-val">{kpis["ents"]:,}</span><span class="kpi-label">Intel</span></div>'

    # 4. Chart
    sparkline_svg = generate_sparkline_svg(df_daily)
    chart_html = ""
    
    if sparkline_svg:
       
        clean_svg = sparkline_svg.replace("\n", "").strip()
       
        chart_html = f'<div class="spark-container"><div class="spark-title">Ritmo de Ingesta</div>{clean_svg}</div>'

    # 5. Renderizado Final (HTML Minificado)
    # Usamos una cadena f-string compacta para evitar indentaciones accidentales
    final_html = f"""
    <div class="hero-container">
        <div class="hero-left">
            {img_tag}
            <div class="hero-titles">
                <h1>BotScape</h1>
                <p>Scope: {start_date} → {end_date}</p>
            </div>
        </div>
        <div style="display:flex; align-items:center; gap:25px;">
            <div class="hero-kpis">
                {bots_html}
                {msgs_html}
                {ents_html}
            </div>
            {chart_html}
        </div>
    </div>
    """
    
    st.markdown(final_html, unsafe_allow_html=True)
def render_action_grid():
    """Grid de 3 botones."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="action-card"><span class="action-icon">🛡️</span><div class="action-title">Breach Monitor</div><div class="action-desc">Detección de exfiltraciones</div></div>', unsafe_allow_html=True)
        if st.button("Ver Alertas", key="act_breach", use_container_width=True): st.switch_page("pages/10_Breach_Monitor.py")
    with c2:
        st.markdown('<div class="action-card"><span class="action-icon">🕸️</span><div class="action-title">Traceability</div><div class="action-desc">Visión global del ecosistema</div></div>', unsafe_allow_html=True)
        if st.button("Ver Grafos", key="act_graph", use_container_width=True): st.switch_page("pages/9_Graph_Analysis.py")
    with c3:
        st.markdown('<div class="action-card"><span class="action-icon">📥</span><div class="action-title">Ingest Manager</div><div class="action-desc">Monitorizar nuevo Bot</div></div>', unsafe_allow_html=True)
        if st.button("Añadir", key="act_ingest", use_container_width=True): st.switch_page("pages/13_Ingest.py")

def render_live_wire_interactive(df_feed):
    """
    Lista interactiva. Usa columnas nativas para insertar botones.
    """
    st.markdown("### ⚡ Mensajes recientes")
    
    if df_feed.empty:
        st.caption("Esperando tráfico...")
        return

    st.markdown("""
    <div style="display:flex; font-size:0.75rem; color:#8b949e; border-bottom:1px solid #30363d; padding-bottom:5px; margin-bottom:5px;">
        <div style="width:60px;">HORA</div>
        <div style="width:60px; text-align:center;">TIPO</div>
        <div style="width:140px;">BOT</div>
        <div style="flex-grow:1;">CONTENIDO</div>
    </div>
    """, unsafe_allow_html=True)

    for i, row in df_feed.iterrows():
        c_time, c_icon, c_btn, c_text = st.columns([0.8, 0.4, 1.8, 5])
        
        with c_time:
            st.markdown(f"<span style='color:#58a6ff; font-family:monospace; font-weight:bold; font-size:0.85rem'>{row['time_str']}</span>", unsafe_allow_html=True)
        
        with c_icon:
            icon = "📎" if row['has_media'] else "💬"
            st.markdown(f"<div style='text-align:center;'>{icon}</div>", unsafe_allow_html=True)
            
        with c_btn:
            # BOTÓN MÁGICO: Redirige al perfil
            label = row['token'][:12] + "..."
            if st.button(label, key=f"btn_live_{i}", help=f"Ir al perfil de {row['token']}", use_container_width=True):
                st.session_state['selected_token'] = row['token']
                st.switch_page("pages/2_Bots.py")
        
        with c_text:
            snippet = row['snippet'] or ""
            snippet = snippet.replace("<", "&lt;").replace(">", "&gt;")
            if len(snippet) > 70: snippet = snippet[:70] + "..."
            st.markdown(f"<span style='color:#c9d1d9; font-family:monospace; font-size:0.85rem; font-style:italic;'>{snippet}</span>", unsafe_allow_html=True)
        
        st.markdown("<div style='border-bottom: 1px solid #21262d; margin-bottom: 4px;'></div>", unsafe_allow_html=True)

def render_entity_sunburst(df_top_vals):
    """Sunburst Chart para Entidades."""
    st.markdown("##### 🧩 ¿Qué contienen los mensajes?")
    if df_top_vals.empty:
        st.info("Sin datos.")
        return

    df_clean = df_top_vals[~df_top_vals['etype'].isin(['generic_kv', 'user_filepath'])]
    if df_clean.empty:
        st.caption("Datos insuficientes.")
        return

    fig = px.sunburst(
        df_clean,
        path=['etype', 'value'],
        values='cnt',
        color='cnt',
        color_continuous_scale='RdBu_r',
        template="plotly_dark"
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300, paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

def render_top_bots_chart(df_top):
    """Renderiza un gráfico de barras horizontal para los Top Bots."""
    st.markdown("##### 🤖 Bots más activos")
    if df_top.empty:
        st.info("Sin bots activos.")
        return

    df_top['label'] = df_top['token'].apply(lambda x: x[:15] + "...")
    
    fig = px.bar(
        df_top, 
        x="msgs", 
        y="label", 
        orientation='h',
        color="media",
        template="plotly_dark",
        labels={"msgs": "Mensajes", "label": "Bot Token", "media": "Adjuntos"},
        color_continuous_scale="Bluered"
    )
    
    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis={'categoryorder':'total ascending'},
        xaxis=dict(showgrid=True, gridcolor='#30363d')
    )
    st.plotly_chart(fig, use_container_width=True)