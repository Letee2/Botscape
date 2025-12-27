import streamlit as st
import pandas as pd
from botscape.scripts.actor_deep_dive import ActorDeepDive
import botscape.shared.db.queries.operator as op_queries
import botscape.dashboard.ui.operator as op_ui
import time
# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Operator Intel", page_icon="👹", layout="wide")
st.markdown("""
<style>
    .stat-box { background: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 8px; text-align:center; }
</style>
<div style="background: linear-gradient(90deg, #0f2027 0%, #203a43 50%, #2c5364 100%); padding: 20px; border-radius: 10px; border-left: 5px solid #00d2d3;">
    <h2 style="margin:0; color: #f8f9fa;">Análisis de actores</h2>
    <div style="color: #adb5bd;">Mapeo de Infraestructura: Actores, Bots, Hubs e IPs Asociadas.</div>
</div><br>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 1. LOCALIZADOR
# -----------------------------------------------------------------------------
col_search, col_stats = st.columns([1, 2])
search_id = col_search.text_input("📍 ID Objetivo:", placeholder="Ej: 5474659567")

try:
    df_actors = op_queries.get_unified_actors_leaderboard(limit=20000)
except: df_actors = pd.DataFrame()

if search_id and not df_actors.empty and search_id not in df_actors['actor_id'].values:
    try:
        df_target = op_queries.get_specific_actor_stats(search_id)
        if not df_target.empty:
            df_actors = pd.concat([df_target, df_actors]).drop_duplicates(subset=['actor_id'], keep='first')
    except: pass

with col_stats:
    if not df_actors.empty:
        k1, k2, k3 = st.columns(3)
        k1.metric("Actores", len(df_actors))
        k2.metric("Commanders", len(df_actors[df_actors['calculated_role'] == 'COMMANDER']))
        k3.metric("Collectors", len(df_actors[df_actors['calculated_role'] == 'COLLECTOR']))

st.divider()

total_fleet_size = int(df_actors['bot_fleet_size'].sum())

selection = st.dataframe(
    df_actors,
    column_config={
        "actor_id": "Identidad", 
        "calculated_role": "Rol", 
        # CAMBIO: max_value es ahora el TOTAL, no el MAX.
        # Visualmente: Una barra llena significaría que ese actor controla el 100% de la red.
        "bot_fleet_size": st.column_config.ProgressColumn(
            "Cuota de Flota", 
            help=f"Contribución al total de {total_fleet_size} bots detectados",
            format="%d", 
            min_value=0, 
            max_value=total_fleet_size 
        )
    },
    use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True, height=250
)
target_row = df_actors.iloc[selection.selection['rows'][0]] if selection.selection['rows'] else (df_actors.iloc[0] if search_id and not df_actors.empty and df_actors.iloc[0]['actor_id'] == search_id else None)

# -----------------------------------------------------------------------------
# 2. VISTA PRINCIPAL
# -----------------------------------------------------------------------------
if target_row is not None:
    aid = target_row['actor_id']
    role = target_row['calculated_role']
    # --- ZONA DE ACCIÓN: DEEP DIVE BUTTON ---
    st.markdown("---")
    col_title, col_btn = st.columns([3, 1])
    col_title.subheader(f"📡 Topología: {aid}")
    
    # ESTADO DE SESIÓN PARA EL REPORTE
    if 'deep_dive_data' not in st.session_state:
        st.session_state.deep_dive_data = None
    
    # BOTÓN DE EXTRACCIÓN TOTAL
    if col_btn.button("🚀 FULL INTEL EXTRACTION", type="primary", use_container_width=True):
        with st.status("🕵️‍♂️ Ejecutando Protocolo Deep Dive...", expanded=True) as status:
            investigator = ActorDeepDive(aid)
            
            st.write("Conectando con Infraestructura...")
            time.sleep(0.5)
            
            st.write("Auditando Flota y C2...")
            report = investigator.run_full_audit()
            st.session_state.deep_dive_data = report
            
            status.update(label="✅ Extracción Completada", state="complete", expanded=False)

    # --- VISUALIZACIÓN DEL REPORTE (SI EXISTE) ---
    if st.session_state.deep_dive_data:
        data = st.session_state.deep_dive_data
        
        with st.expander("📂 REPORTE DE INTELIGENCIA FORENSE (360º)", expanded=True):
            
            # 1. ALERTAS DE ALTO NIVEL (C2)
            # Usamos .get() para evitar KeyErrors si la estructura cambia
            infra = data.get('infrastructure', {})
            if isinstance(infra, dict) and 'c2' in infra and not infra['c2'].empty:
                st.error(f"🚨 INFRAESTRUCTURA C2 DETECTADA")
                st.dataframe(infra['c2'], hide_index=True)

            # 2. PESTAÑAS DE DETALLE (Estructura Nueva)
            t1, t2, t3, t4, t5 = st.tabs([
                "💰 Crypto & Contactos", 
                "🔄 Movimiento de Datos", 
                "🤖 Huella Pública", 
                "🎧 Intereses (Input)", 
                "🗣️ Actor Directo"
            ])
            
            # TAB 1: CRYPTO & SOCIAL (NUEVO)
            with t1:
                st.caption("Wallets, Direcciones y @Usuarios detectados (Regex)")
                # Verificación segura de clave 'assets'
                if 'assets' in data and not data['assets'].empty:
                    st.dataframe(
                        data['assets'], 
                        column_config={
                            "tipo": st.column_config.TextColumn("Tipo", help="BTC, USDT, Alias..."),
                            "valor": "Identificador",
                            "contexto": "Fragmento Mensaje"
                        },
                        use_container_width=True
                    )
                else:
                    st.info("No se detectaron patrones financieros ni de contacto explícitos.")

           # TAB 2: MOVIMIENTO (PAGINADO)
            with t2:
                st.caption("Visualización de rutas de datos confirmadas (Similitud >= 92%)")
                
                if 'content_movement' in data and not data['content_movement'].empty:
                    df_mov = data['content_movement']
                    total_matches = len(df_mov)
                    
                    # --- CONFIGURACIÓN DE PAGINACIÓN ---
                    ITEMS_PER_PAGE = 5
                    
                    # Inicializar estado de página si no existe
                    if 'trace_page' not in st.session_state:
                        st.session_state.trace_page = 0
                        
                    # Cálculos de índices
                    start_idx = st.session_state.trace_page * ITEMS_PER_PAGE
                    end_idx = start_idx + ITEMS_PER_PAGE
                    
                    # Controles de Paginación
                    c_prev, c_info, c_next = st.columns([1, 2, 1])
                    
                    with c_prev:
                        if st.session_state.trace_page > 0:
                            if st.button("⬅️ Anterior", key="prev_trace"):
                                st.session_state.trace_page -= 1
                                st.rerun()
                                
                    with c_next:
                        if end_idx < total_matches:
                            if st.button("Siguiente ➡️", key="next_trace"):
                                st.session_state.trace_page += 1
                                st.rerun()
                                
                    with c_info:
                        st.markdown(f"<div style='text-align: center'>Mostrando {start_idx + 1}-{min(end_idx, total_matches)} de {total_matches}</div>", unsafe_allow_html=True)

                    st.divider()

                    # --- RENDERIZADO DE ELEMENTOS (SLICE) ---
                    # Solo iteramos sobre el subconjunto de la página actual
                    subset = df_mov.iloc[start_idx:end_idx]
                    
                    for i, row in subset.iterrows():
                        # Usamos el índice original del DF para el título
                        real_index = start_idx + list(subset.index).index(i) + 1
                        
                        with st.container(border=True):
                            # Encabezado
                            c1, c2 = st.columns([3, 1])
                            c1.markdown(f"**#{real_index} {row['match_type']}**")
                            c2.metric("Latencia", row['latency_str'])
                            src = str(row['src_node']).replace('"', "'")
                            dst = str(row['dst_node']).replace('"', "'")
                            bot_in = str(row['bot_in']).replace('"', "'")
                            bot_out = str(row['bot_out']).replace('"', "'")
                            
                            internal_label = "Transfer" if bot_in != bot_out else "Pass"
                            
                            dot_code = f"""
                                digraph G {{
                                    rankdir=LR;
                                    bgcolor="transparent";
                                    
                                    node [
                                        shape=box, 
                                        style="filled,rounded", 
                                        fontname="Sans-Serif", 
                                        fontsize=10,
                                        fontcolor="#eeeeee",
                                        color="#444444"
                                    ];
                                    
                                    edge [color="#888888", fontcolor="#aaaaaa", fontsize=9];

                                    /* Nodos: IDs Puros */
                                    Src [label="{src}", fillcolor="#1E3D59"];       
                                    BotA [label="In: {bot_in}", fillcolor="#333333"]; 
                                    BotB [label="Out: {bot_out}", fillcolor="#333333"];
                                    Dst [label="{dst}", fillcolor="#1E593D"];       
                                    
                                    Src -> BotA [label="Input"];
                                    BotA -> BotB [style=dashed, label="{internal_label}"];
                                    BotB -> Dst [label="Publish", color="#FF4B4B", penwidth=2];
                                }}
                            """
                            st.graphviz_chart(dot_code, use_container_width=True)
                            
                            # Comparativa de Texto
                            col_in, col_out = st.columns(2)
                            with col_in:
                                st.caption("📥 Entrada (Raw)")
                                st.text_area("Inbound", value=row.get('input_full_text', ''), height=100, disabled=True, key=f"in_{i}")
                            with col_out:
                                st.caption("📤 Salida (Publicado)")
                                st.text_area("Outbound", value=row['content_snippet'], height=100, disabled=True, key=f"out_{i}")
                                
                else:
                    st.warning("No se encontraron trazas con similitud >= 92%.")

            # TAB 3: HUELLA BOTS (Output)
            with t3:
                # 1. Obtenemos el DataFrame de forma segura
                df_footprint = data.get('bot_footprint', pd.DataFrame()).copy()

                if not df_footprint.empty:
                    # 2. AUTO-CORRECCIÓN DE NOMBRE DE COLUMNA
                    # Buscamos la columna numérica (count, volume, etc) y la normalizamos a 'activity_volume'
                    possible_names = ['count', 'cnt', 'volume', 'vol', 'total_msgs']
                    
                    # Si 'activity_volume' no existe, buscamos candidatos
                    if 'activity_volume' not in df_footprint.columns:
                        found_col = None
                        for name in possible_names:
                            if name in df_footprint.columns:
                                found_col = name
                                break
                        
                        if found_col:
                            # Renombramos la columna encontrada a la que espera el código
                            df_footprint = df_footprint.rename(columns={found_col: 'activity_volume'})
                        else:
                            # Fallback: Si no encontramos nada, creamos la columna con 0
                            df_footprint['activity_volume'] = 0

                    # 3. Cálculo seguro del total (evitando NaN)
                    total_vol = int(df_footprint['activity_volume'].fillna(0).sum())
                    if total_vol == 0: total_vol = 1  # Evitar división por cero visual

                    st.success(f"Operando en {len(df_footprint)} canales públicos")
                    
                    # 4. Renderizado con la configuración corregida
                    st.dataframe(
                        df_footprint, 
                        column_config={
                            "bot": "Bot", #
                            "display_name": "Bot",
                            "location": "Canal/Grupo",
                            "chat_title": "Canal/Grupo", 
                            
                            "activity_volume": st.column_config.ProgressColumn(
                                "Peso en Campaña", 
                                format="%d",     
                                min_value=0,
                                max_value=total_vol
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Bots confinados a privado o sin actividad reciente.")

            # TAB 4: INTERESES (Input)
            with t4:
                if 'subscriptions' in data and not data['subscriptions'].empty:
                    st.dataframe(data['subscriptions'], use_container_width=True)
                else:
                    st.info("No hay reenvíos detectados.")

            # TAB 5: ACTOR DIRECTO
            with t5:
                if 'direct_activity' in data and not data['direct_activity'].empty:
                    st.dataframe(data['direct_activity'], use_container_width=True)
                else:
                    st.info("Modo Fantasma activo.")
    
    st.markdown("---")
    st.subheader(f"📡 Topología: {aid}")
    
    tab_graph, tab_traffic, tab_details = st.tabs(["🗺️ Topología", "🚦 Flujo de Tráfico", "📝 Inventario"])

    with tab_graph:
        df_bots, df_infra, df_partners, df_hubs = op_queries.get_actor_ego_graph(aid)
        
        if not df_bots.empty:
            # Usamos la nueva función visual limpia
            op_ui.render_network_graph(aid, role, df_bots, df_infra, df_partners, df_hubs)
            
            # Leyenda simple
            st.caption("🔴 Actor | 🔵 Bots | 🟢 Grupos/Canales | 🟡 Partners | 🟠 Infraestructura")
        else:
            st.warning("Datos insuficientes para generar la topología.")

    # --- TAB 2: FLUJO ---
    with tab_traffic:
        # A. Sankey
        df_flow = op_queries.get_traffic_flow(aid)
        if not df_flow.empty:
            bot_resolver, known_bot_ids = {}, set()
            try:
                df_ref = op_queries.get_all_bot_identities()
                known_bot_ids = set(df_ref['bot_id'].astype(str).tolist())
                for _, b in df_ref.iterrows():
                    bid = str(b['bot_id'])
                    if b['display_name']: bot_resolver[b['display_name']] = bid
                    if b['token']: bot_resolver[b['token']] = bid
                    bot_resolver[bid] = bid 
            except: pass
            
            op_ui.render_sankey_diagram(aid, df_flow, bot_resolver, known_bot_ids)
        else:
            st.warning("No hay datos de flujo.")

        # B. Topología (Tabla)
        st.divider()
        st.markdown("### 🌉 Flujo del tráfico")
        try:
            df_topo = op_queries.get_topology_balance(aid)
            if not df_topo.empty:
                op_ui.render_topology_table(df_topo)
            else:
                st.info("Sin datos de topología.")
        except Exception as e: st.error(f"Error topología: {e}")

        # C. Auditoría Forense
        st.divider()
        st.markdown("### 🕵️‍♂️ Deep Forensic Audit")
        if st.button("🚀 Ejecutar Análisis Forense", type="primary"):
            from botscape.services.enrichment.forensics import get_actor_forensic_data, generate_llm_forensic_prompt
            from botscape.shared.llm.provider import query_llm 
            import re, json
            
            with st.spinner("Analizando..."):
                raw = get_actor_forensic_data(aid, limit=100)
                if raw and (not raw['harvest'].empty or not raw['commands'].empty):
                    prompt = generate_llm_forensic_prompt(aid, raw)
                    try:
                        resp = query_llm(prompt)
                        match = re.search(r'\{.*\}', resp, re.DOTALL)
                        analysis = json.loads(match.group(0)) if match else {}
                        st.session_state.forensic_report = {"data": raw, "analysis": analysis}
                    except: st.error("Error LLM")
        
        if st.session_state.get('forensic_report'):
            rep = st.session_state.forensic_report
            an = rep['analysis']
            st.info(f"🧠 Veredicto: {an.get('role_hypothesis', 'N/A')}")
            st.write(an.get('operational_profile', ''))
            t1, t2 = st.tabs(["Harvest", "Commands"])
            t1.dataframe(rep['data']['harvest'])
            t2.dataframe(rep['data']['commands'])

    # --- TAB 3: INVENTARIO ---
    with tab_details:
        st.markdown("### 🛠️ Inventario de Activos")
        df_inv = op_queries.get_bot_inventory(aid)
        
        if not df_inv.empty:
            total_msgs = int(df_inv['msg_count'].sum()) or 1
            
            k1, k2 = st.columns(2)
            k1.metric("Flota", len(df_inv))
            k2.metric("Tráfico Total", total_msgs)
            
            st.dataframe(
                df_inv[['bot_id_num', 'display_name', 'token', 'msg_count']],
                column_config={
                    # CAMBIO: max_value es el tráfico total del actor
                    "msg_count": st.column_config.ProgressColumn(
                        "Actividad Relativa", 
                        format="%d",
                        max_value=total_msgs
                    )
                },
                use_container_width=True, hide_index=True
            )
            st.divider()
            st.subheader("🌍 Infraestructura y Atribución")

            # Recuperación defensiva de tokens
            tokens = df_inv['token'].dropna().tolist() if 'token' in df_inv.columns else []

            if tokens:
                df_net = op_queries.get_infrastructure_intelligence(tokens)

                if not df_net.empty:
                    # Layout: Tabla principal a la izquierda, Métricas a la derecha
                    c_table, c_metrics = st.columns([3, 1])

                    with c_table:
                        st.caption("Detalle de conexión: Bot vs Infraestructura")
                        
                        # Configuración de columnas para una UI limpia
                        column_config = {
                            "indicator": st.column_config.TextColumn("Indicador (IP/Host)", help="IP o Dominio del C2"),
                            "country_code": st.column_config.TextColumn("País", width="small"),
                            "asn": st.column_config.TextColumn("ASN / Proveedor", width="medium"),
                            "bot_name": st.column_config.TextColumn("Bot Vinculado", help="Bot que conectó a esta infra"),
                            "last_seen": st.column_config.DatetimeColumn("Última vez", format="DD/MM HH:mm"),
                            "type": None,          # Ocultamos columnas técnicas no esenciales
                            "bot_username": None   # Ocultamos si ya mostramos el display_name
                        }

                        # Mostramos la tabla. 
                        # hide_index=True para limpiar ruido visual.
                        st.dataframe(
                            df_net, 
                            column_config=column_config, 
                            use_container_width=True, 
                            hide_index=True,
                            height=350
                        )

                    with c_metrics:
                        st.caption("Top Jurisdicciones")
                        
                        # Agregación por País
                        if 'country_code' in df_net.columns:
                            top_countries = df_net['country_code'].value_counts().reset_index()
                            top_countries.columns = ['País', 'Hosts']
                            st.dataframe(
                                top_countries, 
                                hide_index=True, 
                                use_container_width=True
                            )
                        
                        st.divider()
                        
                        # Agregación por ASN (Detector de Proveedores de Hosting/Bulletproof)
                        st.caption("Top ASNs")
                        if 'asn' in df_net.columns:
                            top_asn = df_net['asn'].value_counts().head(5).reset_index()
                            top_asn.columns = ['ASN', 'Freq']
                            st.dataframe(
                                top_asn, 
                                hide_index=True, 
                                use_container_width=True
                            )

                else:
                    st.info("No se ha detectado infraestructura externa vinculada a estos bots.")

            else:
                st.warning("No hay bots seleccionados para analizar.")

else:
    st.info("👈 Selecciona un actor.")