# botscape/dashboard/pages/2_Bots.py
import sys
import os
import streamlit as st
import networkx as nx
from datetime import date, timedelta
import textwrap
from botscape.config import settings
from botscape.shared.db.caching import list_tokens, read_sql
import botscape.shared.db.queries as queries
import botscape.shared.db.actions as actions
import botscape.shared.db.queries.profiling as prof_queries
import botscape.dashboard.ui.bots as ui

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Bot Profile", page_icon="🤖", layout="wide")
ui.inject_css() # Inyectamos los estilos centralizados

# -----------------------------
# Helpers Lógicos (Controlador)
# -----------------------------
def dt_range(start_date: date, end_date: date):
    return f"{start_date.isoformat()}T00:00:00Z", f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"

@st.cache_data(ttl=600)
def calculate_cluster_metrics_logic(target_token: str):
    """Lógica pura de cálculo de cluster (sin UI)."""
    df_h = queries.get_graph_edges_hashes()
    df_c = queries.get_graph_edges_chats()
    
    G = nx.Graph()
    for _, r in df_h.iterrows(): G.add_edge(r['token'], r['sample_sha256'], type='hash')
    for _, r in df_c.iterrows(): G.add_edge(r['token'], r['chat_id'], type='chat')
        
    if target_token not in G:
        return {"size": 1, "bots": 1, "hashes": 0, "chats": 0, "is_isolated": True}
        
    try:
        cluster_nodes = nx.node_connected_component(G, target_token)
    except:
        return {"size": 1, "bots": 1, "hashes": 0, "chats": 0, "is_isolated": True}
        
    bots = [n for n in cluster_nodes if ":" in str(n) and len(str(n)) > 20]
    hashes = [n for n in cluster_nodes if len(str(n)) == 64 and " " not in str(n)]
    chats = [n for n in cluster_nodes if str(n).lstrip("-").isdigit()]
    
    return {
        "size": len(cluster_nodes),
        "bots": len(bots),
        "hashes": len(hashes),
        "chats": len(chats),
        "is_isolated": len(bots) <= 1
    }

# -----------------------------
# 1. Header & State Management
# -----------------------------
tokens = list_tokens()
if not tokens:
    st.warning("No hay bots en la base de datos.")
    st.stop()

if 'selected_token' not in st.session_state:
    st.session_state.selected_token = tokens[0]

current_idx = tokens.index(st.session_state.selected_token) if st.session_state.selected_token in tokens else 0

# === HEADER LAYOUT ===
with st.container():
    c_sel, c_date, c_risk = st.columns([2, 1.5, 1.5])
    
    with c_sel:
        st.markdown("#### 🎯 Objetivo")
        selected_token = st.selectbox(
            "Seleccionar Bot", tokens, index=current_idx, label_visibility="collapsed"
        )
        st.session_state.selected_token = selected_token
        st.code(selected_token, language="text")

    with c_date:
        st.markdown("#### 📅 Ventana temporal")
        cd1, cd2 = st.columns(2)
        with cd1:
            days = st.number_input("Días", min_value=1, max_value=365, value=30, label_visibility="collapsed")
        with cd2:
            end_date = st.date_input("Hasta", value=date.today(), label_visibility="collapsed")
        start_iso, end_iso = dt_range(end_date - timedelta(days=days-1), end_date)

    with c_risk:
        # Fetch de datos rápidos para el header
        df_profile = prof_queries.get_bot_profile(selected_token)
        profile = df_profile.iloc[0] if not df_profile.empty else None
        risk_level = profile['risk_level'] if profile is not None else "UNKNOWN"
        intent = profile['actor_intent'] if profile is not None else "N/A"
        
        kpi_check = queries.get_bot_kpis(selected_token, "2000-01-01", "2100-01-01")
        is_active_db = kpi_check.iloc[0]["is_active"] if not kpi_check.empty else False

        # Badge
        st.markdown(f"""
        <div style="text-align: right; margin-bottom: 5px;">
            {ui.get_risk_badge(risk_level)}
            <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px;">
                Intent: <strong style="color: #e6edf3;">{intent}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Acción
        if is_active_db:
            if st.button("🔴 Stop Listening", use_container_width=True):
                actions.set_bot_status(selected_token, False)
                st.rerun()
        else:
            if st.button("🟢 Reactivate Listening", use_container_width=True):
                actions.set_bot_status(selected_token, True)
                st.rerun()

st.divider()

# -----------------------------
# 1.5. SECCIÓN ORIGEN
# -----------------------------
# Consultamos la nueva inteligencia vinculada
df_intel = read_sql("""
    SELECT 
        b.c2_webhook_url,
        s.origin_url,
        s.file_type,
        s.sha256,
        s.imphash,
        s.ssdeep
    FROM bots b
    LEFT JOIN samples_intelligence s ON b.token = s.associated_token
    WHERE b.token = %(token)s
    -- Si hay múltiples samples, priorizamos el que tenga origen web confirmado
    ORDER BY s.origin_url IS NULL, s.ingest_at DESC
    LIMIT 1;
""", params={"token": selected_token})

if not df_intel.empty:
    intel_row = df_intel.iloc[0]
    webhook = intel_row['c2_webhook_url']
    origin_url = intel_row['origin_url']
    
    # Solo mostramos la sección si hay inteligencia valiosa
    if webhook or origin_url or intel_row['sha256']:
        st.markdown("### 🕵️‍♂️ Información general")
        
        # Tarjetas de Infraestructura
        ic1, ic2 = st.columns(2)
        
        with ic1:
            if webhook:
                st.error(f"🚨 **C2 Webhook Confirmado (Backend)**")
                st.code(webhook, language="text")
                st.caption("El bot envía los datos robados directamente a esta URL (Infraestructura del Atacante).")
            else:
                st.info("📡 Modo C2: **Long Polling** (Sin Webhook fijo)")
                st.caption("El atacante consulta manualmente la API de Telegram.")

        with ic2:
            if origin_url:
                st.warning(f"🎣 **Origen de Infección / Phishing (Frontend)**")
                st.code(origin_url, language="text")
                st.caption(f"URL In-The-Wild desde donde se distribuyó el malware (Fuente: VT).")
            elif intel_row['file_type'] == 'html/web':
                st.warning("📄 **Artefacto HTML Detectado**")
                st.caption("Se detectó código fuente de phishing, pero no se ha confirmado la URL pública.")
            elif intel_row['file_type'] == 'executable':
                st.info("⚙️ **Artefacto Binario (.EXE)**")
                st.caption("El origen es un ejecutable compilado (Stealer/Malware).")

        # Detalles Técnicos del Artefacto (Expander)
        if intel_row['sha256']:
            with st.expander("🧬 Detalles Técnicos de la Muestra (Hash, Imphash, SSDeep)", expanded=False):
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.text_input("SHA256", value=intel_row['sha256'], disabled=True)
                    st.text_input("Tipo de Archivo", value=intel_row['file_type'] or "Desconocido", disabled=True)
                with tc2:
                    st.text_input("Imphash (Import Hash)", value=intel_row['imphash'] or "N/A", disabled=True, help="Útil para agrupar variantes del mismo malware.")
                    st.text_input("SSDeep (Fuzzy Hash)", value=intel_row['ssdeep'] or "N/A", disabled=True, help="Hash de similitud para detectar código reutilizado.")
                
                st.markdown(f"[🔎 Analizar en VirusTotal](https://www.virustotal.com/gui/file/{intel_row['sha256']})")

        st.divider()

df_operators = queries.get_bot_operators(selected_token)

if not df_operators.empty:
    st.markdown("### 👤 Atribución & Social Graph")
    
    for _, row in df_operators.iterrows():
        # Definimos icono y rol
        if row['type'] == 'CHANNEL':
            icon = "📢"
            role_desc = "Canal de Exfiltración (Dump)"
        else:
            icon = "💀"
            role_desc = "Operador / Admin"

        # 1. Lógica del Botón (Renderizado limpio)
        if row['username']:
            # Usamos \ al final de f""" para evitar la primera línea vacía
            btn_html = f"""\
<a href="https://t.me/{row['username']}" target="_blank" 
style="background:#3498db; color:white; padding:6px 12px; border-radius:4px; text-decoration:none; font-size:0.8rem;">
Ver Perfil ↗
</a>"""
        else:
            btn_html = """\
<span style="background:#4a4a4a; color:#888; padding:6px 12px; border-radius:4px; font-size:0.8rem; cursor:not-allowed;">
Privado
</span>"""

        html_card = f"""
<div style="background: linear-gradient(90deg, #2c1e1e 0%, #1a1a1a 100%); border-left: 4px solid #e74c3c; padding: 15px; border-radius: 6px; margin-bottom: 10px;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
            <div style="font-size:0.8rem; color:#e74c3c; font-weight:bold; text-transform:uppercase;">
                {role_desc}
            </div>
            <div style="font-size:1.2rem; font-weight:bold; color:#fff;">
                {icon} {row['full_name'] or 'Desconocido'} 
                <span style="font-family:monospace; color:#888; font-size:0.9rem;">(@{row['username'] or 'No Alias'})</span>
            </div>
            <div style="font-size:0.8rem; color:#888; margin-top:4px;">
                ID: <span style="font-family:monospace;">{row['telegram_id']}</span> 
                | Última vez: {row['last_detected']} | <b>{row['interaction_count']} Interacciones</b>
            </div>
        </div>
        <div>
            {btn_html}
        </div>
    </div>
</div>
"""
        
        st.markdown(textwrap.dedent(html_card), unsafe_allow_html=True)

# -----------------------------
# 2. Panel de Inteligencia 
# -----------------------------
# Data Fetching para UI
df_kpi = queries.get_bot_kpis(selected_token, start_iso, end_iso)
kpi = df_kpi.iloc[0] if not df_kpi.empty else {'msgs':0, 'ents':0, 'media':0}
df_tags = queries.get_bot_tags(selected_token)

# Layout
col_intel_1, col_intel_2 = st.columns([1, 1.8])

# --- IZQUIERDA: CARDS ---
with col_intel_1:
    # 1. Profiler Card
    ui.render_profiler_card(profile, df_tags)
    
    # 2. Cluster Analysis Card (Con lógica separada)
    cluster_metrics = calculate_cluster_metrics_logic(selected_token)
    
    # Si el botón "Explorar" se pulsa dentro de esta función, maneja la navegación
    ui.render_cluster_card(cluster_metrics, selected_token)

    # Acción Manual para Profiler
    if profile is None:
        if st.button("⚡ Ejecutar Análisis Manual (Profiler)"):
            from botscape.scripts.profiler import analyze_single_bot
            with st.spinner("Analizando con IA local..."):
                analyze_single_bot(selected_token)
            st.rerun()

# --- DERECHA: GRAFO EGO ---
with col_intel_2:
    # Data Fetching para el Grafo Ego
    df_hashes = queries.get_bot_hashes(selected_token)
    t_hashes = df_hashes['sample_sha256'].tolist() if not df_hashes.empty else []
    df_chats = queries.get_bot_chats(selected_token)
    t_chats = df_chats['chat_id'].tolist() if not df_chats.empty else []
    
    # Render
    ui.render_ego_graph(selected_token, t_hashes, t_chats)

# -----------------------------
# 3. Métricas y Tabs (Usa UI Library)
# -----------------------------
st.write("")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Mensajes Totales", f"{kpi['msgs']:,}")
c2.metric("Entidades Extraídas", f"{kpi['ents']:,}")
c3.metric("Archivos/Media", f"{kpi['media']:,}")

daily = queries.get_bot_daily_evolution(selected_token, start_iso, end_iso)
last_act = "Inactivo hoy"
if not daily.empty:
    last = daily.iloc[-1]
    if str(last['day']) == str(date.today()):
        last_act = f"Activo ({last['msgs']} msgs)"
c4.metric("Estado Hoy", last_act)

st.divider()

# Renderizado de Tabs completo
ui.render_metrics_tabs(selected_token, start_iso, end_iso)