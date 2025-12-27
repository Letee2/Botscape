import logging
from botscape.shared.db.caching import read_sql

logger = logging.getLogger(__name__)

def get_unified_actors_leaderboard(limit: int = 200):
    """
    Recupera el Top Actores (Dueños de Chats Privados).
    """
    sql = """
    WITH actor_metrics AS (
        SELECT 
            chat_id,
            COUNT(*) as total_msgs,
            COUNT(DISTINCT token) as bot_fleet_size,
            MAX(date_utc) as last_seen,
            COUNT(*) FILTER (
                WHERE sender_id = chat_id 
                  AND (text LIKE '/%%' OR text LIKE '!%%' OR text LIKE '.%%')
            ) as cmd_count,
            COUNT(*) FILTER (
                WHERE (LENGTH(text) > 60 OR has_media = 1)
            ) as intake_count
        FROM messages
        WHERE chat_id IS NOT NULL
          AND chat_id NOT LIKE '-%%' 
        GROUP BY chat_id
    )
    SELECT 
        chat_id as actor_id,
        bot_fleet_size,
        total_msgs,
        cmd_count,
        intake_count,
        last_seen,
        CASE 
            WHEN cmd_count > 0 THEN 'COMMANDER'
            WHEN intake_count > 0 THEN 'COLLECTOR'
            ELSE 'OBSERVER'
        END as calculated_role,
        (bot_fleet_size * 50) + (cmd_count * 20) + (intake_count * 0.1) as risk_score
    FROM actor_metrics
    ORDER BY risk_score DESC
    LIMIT %(limit)s;
    """
    return read_sql(sql, params={"limit": limit})

def get_specific_actor_stats(actor_id: str):
    """
    Busca un actor específico por ID.
    """
    sql = """
    SELECT 
        chat_id as actor_id,
        COUNT(DISTINCT token) as bot_fleet_size,
        COUNT(*) as total_msgs,
        COUNT(*) FILTER (WHERE sender_id = chat_id AND (text LIKE '/%%' OR text LIKE '!%%' OR text LIKE '.%%')) as cmd_count,
        COUNT(*) FILTER (WHERE (LENGTH(text) > 60 OR has_media = 1)) as intake_count,
        MAX(date_utc) as last_seen,
        CASE 
            WHEN COUNT(*) FILTER (WHERE sender_id = chat_id AND (text LIKE '/%%' OR text LIKE '!%%')) > 0 THEN 'COMMANDER'
            ELSE 'COLLECTOR'
        END as calculated_role,
        0 as risk_score
    FROM messages
    WHERE chat_id = %(target)s
    GROUP BY chat_id;
    """
    return read_sql(sql, params={"target": actor_id})

def get_actor_ego_graph(actor_id: str):
    """
    CORREGIDO: Restaurada la columna b.c2_webhook_url real.
    """
    
    # 1. BOTS CONTROLADOS
    sql_bots = """
    SELECT DISTINCT 
        b.token, 
        b.display_name,
        b.c2_webhook_url,  -- <--- RECUPERADO (Antes era NULL)
        'OWNED_BOT' as rel_type
    FROM messages m
    JOIN bots b ON m.token = b.token
    WHERE m.chat_id = %(aid)s
    """
    
    # 2. INFRAESTRUCTURA IP (Vinculada al Bot)
    sql_infra = """
    SELECT DISTINCT 
        i.ip_address, 
        i.asn, 
        i.country_code,
        oi.bot_token as linked_bot,
        'ASSOCIATED_IP' as rel_type
    FROM operator_infrastructure oi
    JOIN infrastructure_intelligence i ON oi.infra_id = i.id
    WHERE oi.sender_id = %(aid)s
    """

    # 3. PARTNERS (Comparten Bots)
    sql_partners = """
    WITH my_bots AS (
        SELECT DISTINCT token FROM messages WHERE chat_id = %(aid)s
    )
    SELECT DISTINCT 
        m.chat_id as partner_id,
        m.token as shared_token,
        'CO_OWNER' as rel_type
    FROM messages m
    JOIN my_bots mb ON m.token = mb.token
    WHERE m.chat_id != %(aid)s 
      AND m.chat_id NOT LIKE '-%%'
      AND (LENGTH(m.text) > 60 OR m.has_media = 1)
    LIMIT 20
    """

    # 4. HUBS PÚBLICOS
    sql_public_hubs = """
    SELECT DISTINCT 
        m.chat_id as hub_id,
        m.chat_id as hub_title,
        m.token as connected_bot
    FROM messages m
    WHERE m.token IN (SELECT DISTINCT token FROM messages WHERE chat_id = %(aid)s)
      AND m.chat_id LIKE '-%%'
    GROUP BY m.chat_id, m.token
    HAVING COUNT(*) > 2 
    LIMIT 10
    """

    df_bots = read_sql(sql_bots, params={"aid": actor_id})
    

    try: df_infra = read_sql(sql_infra, params={"aid": actor_id})
    except Exception: df_infra = read_sql("SELECT 1 WHERE 1=0")

    try: df_partners = read_sql(sql_partners, params={"aid": actor_id})
    except Exception: df_partners = read_sql("SELECT 1 WHERE 1=0")

    try: df_hubs = read_sql(sql_public_hubs, params={"aid": actor_id})
    except Exception: df_hubs = read_sql("SELECT 1 WHERE 1=0")
    
    return df_bots, df_infra, df_partners, df_hubs

def get_operator_loot_stream(actor_id: str, limit: int = 15):
    sql = """
    SELECT 
        m.id, m.date_utc, m.token, b.display_name as bot_name,
        m.text, m.has_media, m.media_path, m.sender_id
    FROM messages m
    JOIN bots b ON m.token = b.token
    WHERE m.chat_id = %(aid)s
      AND (LENGTH(m.text) > 20 OR m.has_media = 1)
    ORDER BY m.date_utc DESC 
    LIMIT %(limit)s;
    """
    return read_sql(sql, params={"aid": actor_id, "limit": limit})

def get_coordination_hubs(actor_id: str):
    sql = """
    SELECT 
        m.chat_id, 
        m.chat_id as chat_title, 
        COUNT(DISTINCT m.token) as bots_present,
        COUNT(*) as msg_volume
    FROM messages m
    WHERE m.token IN (SELECT DISTINCT token FROM messages WHERE chat_id = %(aid)s)
    AND m.chat_id LIKE '-%%'
    GROUP BY m.chat_id
    HAVING COUNT(DISTINCT m.token) > 1
    ORDER BY bots_present DESC
    LIMIT 5;
    """
    return read_sql(sql, params={"aid": actor_id})

def get_operator_shared_sources(sender_id: str):
    return read_sql("SELECT 1 as dummy WHERE 1=0")


from botscape.shared.db.caching import read_sql

def get_network_graph_data():
    """
    Recupera nodos y aristas para el gráfico general de Network Analysis.
    (Utilizado por la página 9_Graph_Analysis.py)
    """
    # 1. Nodos de Bots
    bots = read_sql("SELECT token, display_name FROM bots WHERE is_active = true")
    
    # 2. Nodos de Hash (Malware) vinculados
    hashes = read_sql("""
        SELECT h.token, h.sample_sha256 
        FROM hash_origin h
        JOIN bots b ON h.token = b.token
        WHERE b.is_active = true
    """)
    
    # 3. Nodos de Chat (Infraestructura compartida)
    chats = read_sql("""
        SELECT DISTINCT chat_id, token 
        FROM messages 
        WHERE chat_id LIKE '-%%' -- Solo grupos/canales
    """)
    
    return bots, hashes, chats

def get_c2_webhooks():
    """
    Recupera todos los Webhooks C2 únicos detectados en la flota de bots.
    (Utilizado por Network_Intel.py)
    """
    sql = """
    SELECT 
        c2_webhook_url as url,
        COUNT(token) as bot_count,
        MAX(last_seen) as last_active
    FROM bots
    WHERE c2_webhook_url IS NOT NULL 
      AND c2_webhook_url != ''
    GROUP BY c2_webhook_url
    ORDER BY bot_count DESC;
    """
    return read_sql(sql)

def get_confirmed_origins():
    """
    Recupera la inteligencia de infraestructura confirmada (IPs/Dominios).
    (Utilizado por Network_Intel.py)
    """
    sql = """
    SELECT 
        id,
        indicator,       -- IP o Dominio
        type,            -- 'IP' o 'DOMAIN'
        ip_address,      -- IP resuelta (si es dominio)
        asn,             -- Proveedor (ISP)
        country_code,    -- Geo
        city,
        first_seen,
        last_seen
    FROM infrastructure_intelligence
    ORDER BY last_seen DESC;
    """
    try:
        return read_sql(sql)
    except Exception:
       
        return read_sql("SELECT 1 as indicator WHERE 1=0")



def get_cluster_flow_sankey(cluster_tokens: list, limit: int = 300):
    """
    Calcula el flujo MACRO (Sankey) para un Cluster.
    Usa chat_id como etiqueta de destino.
    """

    tokens_list = list(cluster_tokens)
    
    sql = """
    WITH 
    cluster_ids AS (
        SELECT 
            token, 
            split_part(token, ':', 1)::bigint as bot_telegram_id,
            display_name
        FROM bots 
        WHERE token = ANY(%(tokens)s)
    ),
    
    inbound AS (
        SELECT 
            'INBOUND' as direction,
            '👥 VICTIMS / SOURCES' as source_label,
            '🤖 ' || b.display_name as target_label,
            COUNT(*) as volume
        FROM messages m
        JOIN cluster_ids b ON m.token = b.token
        WHERE 
            m.chat_type = 'private'
            AND m.sender_id IS NOT NULL
            AND m.sender_id::bigint NOT IN (SELECT bot_telegram_id FROM cluster_ids)
        GROUP BY 1, 2, 3
    ),
    
    lateral_flow AS (
        SELECT 
            'LATERAL' as direction,
            '🤖 ' || src_bot.display_name as source_label,
            '🤖 ' || dst_bot.display_name as target_label,
            COUNT(*) as volume
        FROM messages m
        JOIN cluster_ids dst_bot ON m.token = dst_bot.token
        JOIN social_graph_edges sge ON m.id = sge.message_pk
        JOIN cluster_ids src_bot ON sge.identity_id::bigint = src_bot.bot_telegram_id
        WHERE 
            sge.relation_type = 'FORWARD_FROM'
        GROUP BY 1, 2, 3
    ),
    
    outbound AS (
        SELECT 
            'OUTBOUND' as direction,
            '🤖 ' || b.display_name as source_label,
            -- CORRECCIÓN: Usamos directamente el ID porque chat_title no existe
            '📢 ' || m.chat_id as target_label,
            COUNT(*) as volume
        FROM messages m
        JOIN cluster_ids b ON m.token = b.token
        WHERE m.chat_id LIKE '-%%' -- Grupos/Canales
        GROUP BY 1, 2, 3
    )

    SELECT * FROM inbound
    UNION ALL
    SELECT * FROM lateral_flow
    UNION ALL
    (SELECT * FROM outbound ORDER BY volume DESC LIMIT %(limit)s)
    """
    
    return read_sql(sql, params={"tokens": tokens_list, "limit": limit})