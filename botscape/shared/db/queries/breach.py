from botscape.shared.db.caching import read_sql

def get_monitored_assets():
    """Recupera la lista de activos bajo vigilancia."""
    return read_sql("""
        SELECT id, asset_type, asset_value, description 
        FROM monitored_assets 
        ORDER BY asset_type, asset_value
    """)

def find_asset_breaches(start_iso: str, end_iso: str):
    """
    Busca coincidencias de activos monitorizados en los mensajes interceptados.
    
    Mejoras v2.0:
    - Matching difuso para dominios (detecta emails/subdominios).
    - Enriquecimiento con el perfil de riesgo del bot (Threat Intel).
    - Ordenación por criticidad.
    """
    sql = """
    SELECT 
        a.asset_value,
        a.asset_type,
        a.description,
        m.token, 
        m.date_utc, 
        COALESCE(e.context_snippet, LEFT(m.text, 250)) AS snippet, 
        m.id as message_pk,
        
        -- Enriquecimiento: Perfil del Bot (Threat Intel)
        COALESCE(bp.risk_level, 'UNKNOWN') as risk_level,
        COALESCE(bp.actor_intent, 'Unknown') as actor_intent

    FROM entities e
    JOIN messages m ON e.message_pk = m.id
    
    -- JOIN DE DETECCIÓN (Lógica Híbrida)
    JOIN monitored_assets a ON 
        -- Caso A: Coincidencia Exacta (Ideal para IPs, Emails VIP o Hash)
        (e.value = a.asset_value)
        OR
        -- Caso B: Coincidencia de Dominio (Broad Match)
        -- Si monitorizamos 'empresa.com', queremos ver 'user@empresa.com' o 'admin.empresa.com'
        (a.asset_type = 'domain' AND e.value LIKE '%%' || a.asset_value || '%%')

    -- JOIN CON PERFILES (Para contexto de riesgo)
    LEFT JOIN bot_profiles bp ON m.token = bp.token

    WHERE 
        m.date_utc >= %(start)s 
        AND m.date_utc < %(end)s

    ORDER BY 
        -- Prioridad 1: Riesgo del Bot
        CASE bp.risk_level 
            WHEN 'CRITICAL' THEN 1 
            WHEN 'HIGH' THEN 2 
            WHEN 'MEDIUM' THEN 3 
            WHEN 'LOW' THEN 4 
            ELSE 5 
        END ASC,
        -- Prioridad 2: Recencia
        m.date_utc DESC;
    """
    return read_sql(sql, params={"start": start_iso, "end": end_iso})

def get_breach_summary(start_iso: str, end_iso: str):
    """
    Obtiene un resumen de activos comprometidos para el selector principal.
    """
    sql = """
    SELECT 
        a.asset_value,
        a.asset_type,
        COUNT(DISTINCT m.id) as breach_count,
        -- Calculamos el riesgo máximo detectado para este activo
        MAX(CASE COALESCE(bp.risk_level, 'UNKNOWN')
            WHEN 'CRITICAL' THEN 4
            WHEN 'HIGH' THEN 3
            WHEN 'MEDIUM' THEN 2
            WHEN 'LOW' THEN 1
            ELSE 0 END
        ) as max_risk_score
    FROM monitored_assets a
    JOIN entities e ON 
        (e.value = a.asset_value) OR 
        (a.asset_type = 'domain' AND e.value LIKE '%%' || a.asset_value || '%%')
    JOIN messages m ON e.message_pk = m.id
    LEFT JOIN bot_profiles bp ON m.token = bp.token
    WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s
    GROUP BY a.asset_value, a.asset_type
    ORDER BY max_risk_score DESC, breach_count DESC;
    """
    return read_sql(sql, params={"start": start_iso, "end": end_iso})

def find_breaches_by_asset(asset_value: str, start_iso: str, end_iso: str):
    """
    Recupera los incidentes detallados para UN activo específico.
    """
    sql = """
    SELECT 
        m.token, 
        m.date_utc, 
        COALESCE(e.context_snippet, LEFT(m.text, 250)) AS snippet, 
        m.id as message_pk,
        COALESCE(bp.risk_level, 'UNKNOWN') as risk_level,
        COALESCE(bp.actor_intent, 'Unknown') as actor_intent,
        e.value as matched_value
    FROM entities e
    JOIN messages m ON e.message_pk = m.id
    JOIN monitored_assets a ON 
        (e.value = a.asset_value) OR 
        (a.asset_type = 'domain' AND e.value LIKE '%%' || a.asset_value || '%%')
    LEFT JOIN bot_profiles bp ON m.token = bp.token
    WHERE 
        a.asset_value = %(asset)s
        AND m.date_utc >= %(start)s 
        AND m.date_utc < %(end)s
    ORDER BY m.date_utc DESC;
    """
    return read_sql(sql, params={"asset": asset_value, "start": start_iso, "end": end_iso})