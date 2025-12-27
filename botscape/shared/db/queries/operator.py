# botscape/shared/db/queries/operator.py
import logging
import pandas as pd
from botscape.shared.db.caching import read_sql

# --- A. LEADERBOARD ---
def get_unified_actors_leaderboard(limit: int = 200):
    sql = """
    WITH actor_metrics AS (
        SELECT 
            chat_id,
            COUNT(*) as total_msgs,
            COUNT(DISTINCT token) as bot_fleet_size,
            MAX(date_utc) as last_seen,
            COUNT(*) FILTER (WHERE sender_id = chat_id AND (text LIKE '/%%' OR text LIKE '!%%')) as cmd_count,
            COUNT(*) FILTER (WHERE (LENGTH(text) > 60 OR has_media = 1)) as intake_count
        FROM messages
        WHERE chat_id IS NOT NULL AND chat_id NOT LIKE '-%%' 
        GROUP BY chat_id
    )
    SELECT 
        chat_id as actor_id, bot_fleet_size, total_msgs, cmd_count, intake_count, last_seen,
        CASE 
            WHEN cmd_count > 0 THEN 'COMMANDER'
            WHEN intake_count > 0 THEN 'COLLECTOR'
            ELSE 'OBSERVER'
        END as calculated_role,
        (bot_fleet_size * 50) + (cmd_count * 20) + (intake_count * 0.1) as risk_score
    FROM actor_metrics
    ORDER BY risk_score DESC LIMIT %(limit)s;
    """
    return read_sql(sql, params={"limit": limit})

def get_specific_actor_stats(actor_id: str):
    sql = """
    SELECT 
        chat_id as actor_id,
        COUNT(DISTINCT token) as bot_fleet_size,
        COUNT(*) as total_msgs,
        CASE WHEN COUNT(*) FILTER (WHERE sender_id = chat_id AND text LIKE '/%%') > 0 THEN 'COMMANDER' ELSE 'COLLECTOR' END as calculated_role,
        0 as risk_score
    FROM messages WHERE chat_id = %(target)s GROUP BY chat_id;
    """
    return read_sql(sql, params={"target": actor_id})

# --- B. TOPOLOGÍA DE RED (GRAFO) ---
def get_actor_ego_graph(actor_id: str):
    # 1. Bots
    df_bots = read_sql("""
        SELECT DISTINCT b.token, b.display_name, b.c2_webhook_url
        FROM messages m JOIN bots b ON m.token = b.token
        WHERE m.chat_id = %(aid)s
    """, params={"aid": actor_id})
    
    # 2. Infra
    try:
        df_infra = read_sql("""
            SELECT DISTINCT i.ip_address, i.asn, i.country_code, oi.bot_token as linked_bot
            FROM operator_infrastructure oi
            JOIN infrastructure_intelligence i ON oi.infra_id = i.id
            WHERE oi.sender_id = %(aid)s
        """, params={"aid": actor_id})
    except: df_infra = pd.DataFrame()

    # 3. Partners
    try:
        df_partners = read_sql("""
            WITH my_bots AS (SELECT DISTINCT token FROM messages WHERE chat_id = %(aid)s)
            SELECT DISTINCT m.chat_id as partner_id, m.token as shared_token
            FROM messages m JOIN my_bots mb ON m.token = mb.token
            WHERE m.chat_id != %(aid)s AND m.chat_id NOT LIKE '-%%' LIMIT 20
        """, params={"aid": actor_id})
    except: df_partners = pd.DataFrame()

    # 4. Hubs
    try:
        df_hubs = read_sql("""
            SELECT DISTINCT m.chat_id as hub_id, m.token as connected_bot
            FROM messages m
            WHERE m.token IN (SELECT DISTINCT token FROM messages WHERE chat_id = %(aid)s)
            AND m.chat_id LIKE '-%%' LIMIT 10
        """, params={"aid": actor_id})
    except: df_hubs = pd.DataFrame()

    return df_bots, df_infra, df_partners, df_hubs

# --- C. FLUJO Y TRÁFICO ---
def get_traffic_flow(actor_id: str) -> pd.DataFrame:
    return read_sql("""
        SELECT direction, remote_entity, remote_type, via_bot_name, volume 
        FROM intel_traffic_flow WHERE actor_id = %(aid)s ORDER BY volume DESC
    """, params={"aid": actor_id})

def get_all_bot_identities() -> pd.DataFrame:
    return read_sql("SELECT token, display_name, split_part(token, ':', 1) as bot_id FROM bots")

def get_topology_balance(actor_id: str) -> pd.DataFrame:
    """
    Tabla de Enrutamiento: Muestra volumen de entrada y EL DESTINO FINAL de salida.
    """
    sql = """
        WITH channel_destinations AS (
            -- Buscamos a qué canales está enviando mensajes cada bot
            SELECT 
                token, 
                mode() WITHIN GROUP (ORDER BY chat_id) as top_channel_id, -- El canal más frecuente
                COUNT(DISTINCT chat_id) as total_channels
            FROM messages
            WHERE chat_type IN ('channel', 'group', 'supergroup')
            GROUP BY token
        )
        SELECT 
            b.display_name as bot_name, 
            b.username,
            
            -- 1. INPUT (Fuente Externa)
            COUNT(*) FILTER (
                WHERE m.sender_id != %(aid)s 
                AND CAST(m.sender_id AS VARCHAR) != split_part(m.token, ':', 1)
            ) as volume_in,
            
            -- 2. OUTPUT (Hacia Canales/Grupos)
            COUNT(*) FILTER (
                WHERE m.chat_type IN ('channel', 'group', 'supergroup')
            ) as volume_out_channels,

            -- 3. DESTINO PRINCIPAL (Para correlacionar con Sankey)
            COALESCE(cd.top_channel_id, '⛔ N/A') as main_destination,
            cd.total_channels
            
        FROM messages m 
        JOIN bots b ON m.token = b.token
        LEFT JOIN channel_destinations cd ON b.token = cd.token
        WHERE (m.sender_id = %(aid)s OR m.chat_id = %(aid)s)
        GROUP BY b.display_name, b.username, cd.top_channel_id, cd.total_channels
        ORDER BY volume_in DESC, volume_out_channels DESC
    """
    return read_sql(sql, params={'aid': actor_id})

# --- D. INVENTARIO ---
def get_bot_inventory(actor_id: str) -> pd.DataFrame:
    sql = """
        SELECT 
            b.token, b.display_name, b.username,
            (SELECT MIN(date_utc) FROM messages m WHERE m.token = b.token) as first_seen,
            split_part(b.token, ':', 1) as bot_id_num,
            (SELECT COUNT(*) FROM messages m WHERE m.token = b.token) as msg_count
        FROM bots b
        WHERE b.token IN (
            SELECT DISTINCT token FROM messages 
            WHERE (sender_id = %(aid)s OR chat_id = %(aid)s)
        )
        ORDER BY msg_count DESC
    """
    return read_sql(sql, params={"aid": actor_id})

# En tu archivo de queries (ej. op_queries.py)

def get_infrastructure_intelligence(tokens_list: list) -> pd.DataFrame:
    """
    Recupera la infraestructura vinculada enriquecida con datos del Bot y del ASN.
    Objetivo: Identificar infraestructura compartida y origen de red.
    """
    if not tokens_list: 
        return pd.DataFrame()

    query = """
        SELECT 
            ii.indicator,
            ii.type,
            ii.asn,
            ii.country_code,
            ii.last_seen,
            b.display_name as bot_name,
            b.username as bot_username
        FROM infrastructure_intelligence ii
        JOIN operator_infrastructure oi ON ii.id = oi.infra_id
        JOIN bots b ON oi.bot_token = b.token
        WHERE oi.bot_token = ANY(%(tokens)s)
        ORDER BY ii.last_seen DESC
        LIMIT 100
    """

    try:
        return read_sql(query, params={"tokens": tokens_list})
    except Exception as e:
        logging.error(f"Error fetching infrastructure linkage: {e}")
        return pd.DataFrame()
    
