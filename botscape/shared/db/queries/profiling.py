from botscape.shared.db.caching import read_sql
from typing import List, Dict, Any

# --- Lógica de Ingesta (Existente) ---
def get_candidates_for_profiling(limit: int = 10) -> List[str]:
    sql = """
    SELECT b.token
    FROM bots b
    LEFT JOIN bot_profiles bp ON b.token = bp.token
    JOIN messages m ON b.token = m.token
    WHERE b.is_active = true
      AND (bp.analyzed_at IS NULL OR bp.analyzed_at < NOW() - INTERVAL '7 days')
      AND (SELECT COUNT(*) FROM messages WHERE token = b.token) > 10
    GROUP BY b.token
    ORDER BY MAX(m.date_utc) DESC
    LIMIT %(limit)s;
    """
    df = read_sql(sql, params={"limit": limit})
    return df['token'].tolist() if not df.empty else []

def get_bot_fingerprint(token: str) -> Dict[str, Any]:
    sql = """
    SELECT COUNT(*) as total_msgs, SUM(has_media) as media_count,
           MIN(date_utc) as first_seen, MAX(date_utc) as last_seen,
           COUNT(DISTINCT chat_id) as unique_chats
    FROM messages WHERE token = %(token)s;
    """
    df = read_sql(sql, params={"token": token})
    return df.iloc[0].to_dict() if not df.empty else {}

def get_top_templates(token: str, limit: int = 5) -> List[str]:
    sql = """
    SELECT t.example_text, COUNT(*) as cnt
    FROM metrics_text_templates t
    JOIN messages m ON m.text_sha1 = t.text_sha1
    WHERE m.token = %(token)s
    GROUP BY t.text_sha1, t.example_text
    ORDER BY cnt DESC LIMIT %(limit)s;
    """
    df = read_sql(sql, params={"token": token, "limit": limit})
    return [f"({r['cnt']}x) {r['example_text']}" for _, r in df.iterrows()]

def get_entity_summary(token: str) -> Dict[str, int]:
    sql = """
    SELECT e.etype, COUNT(*) as cnt FROM entities e
    JOIN messages m ON m.id = e.message_pk
    WHERE m.token = %(token)s AND e.etype != 'generic_kv'
    GROUP BY e.etype ORDER BY cnt DESC;
    """
    df = read_sql(sql, params={"token": token})
    return dict(zip(df.etype, df.cnt))

def get_generic_kv_samples(token: str, limit: int = 15) -> List[str]:
    sql = """
    SELECT e.value, COUNT(*) as cnt FROM entities e
    JOIN messages m ON m.id = e.message_pk
    WHERE m.token = %(token)s AND e.etype = 'generic_kv'
    GROUP BY e.value ORDER BY cnt DESC LIMIT %(limit)s;
    """
    df = read_sql(sql, params={"token": token, "limit": limit})
    return [f"{r['value']}" for _, r in df.iterrows()]

# --- Lógica de Visualización (Dashboard) ---

def get_profiling_kpis():
    """Métricas globales de inteligencia."""
    return read_sql("""
    SELECT 
        COUNT(*) as total_profiled,
        COUNT(*) FILTER (WHERE risk_level = 'CRITICAL') as critical,
        COUNT(*) FILTER (WHERE risk_level = 'HIGH') as high,
        COUNT(*) FILTER (WHERE actor_intent = 'Stealer') as stealers
    FROM bot_profiles;
    """)

def get_profiles_leaderboard(limit: int = 100):
    """Lista de bots perfilados ordenados por riesgo."""
    return read_sql("""
    SELECT 
        bp.token, 
        b.display_name,
        bp.risk_level, 
        bp.actor_intent, 
        bp.analyzed_at,
        -- Ordenación personalizada para riesgo
        CASE bp.risk_level 
            WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 
            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 
            ELSE 5 END as risk_score
    FROM bot_profiles bp
    JOIN bots b ON bp.token = b.token
    ORDER BY risk_score ASC, bp.analyzed_at DESC
    LIMIT %(limit)s;
    """, params={"limit": limit})

def get_bot_profile(token: str):
    """Detalle completo de un perfil."""
    return read_sql("SELECT * FROM bot_profiles WHERE token = %(token)s;", params={"token": token})

def get_diverse_raw_samples(token: str, limit: int = 8) -> List[Dict[str, str]]:
    """
    Obtiene muestras de mensajes crudos ENRIQUECIDAS con extensiones de adjuntos.
    Devuelve una lista de dicts: [{'text': '...', 'extensions': '.jpg, .txt'}]
    """
    sql = r"""
    WITH samples AS (
        (
            -- Mensajes largos (posibles logs)
            SELECT id, text, date_utc FROM messages 
            WHERE token = %(token)s AND LENGTH(text) > 50
            ORDER BY date_utc DESC LIMIT 4
        )
        UNION ALL
        (
            -- Mensajes cortos (posibles heartbeats/comandos)
            SELECT id, text, date_utc FROM messages 
            WHERE token = %(token)s AND LENGTH(text) BETWEEN 0 AND 50
            ORDER BY date_utc DESC LIMIT 4
        )
    )
    SELECT 
        s.text,
        -- Regex: busca un punto seguido de cualquier cosa que NO sea punto, barra o backslash, hasta el final.
        -- El uso de r"" asegura que '\\' se envíe como dos backslashes a Postgres.
        STRING_AGG(DISTINCT LOWER(SUBSTRING(a.path FROM '\.[^./\\]+$')), ', ') as extensions
    FROM samples s
    LEFT JOIN attachments a ON s.id = a.message_pk
    GROUP BY s.id, s.text, s.date_utc
    ORDER BY s.date_utc DESC;
    """
    
    df = read_sql(sql, params={"token": token})
    
    # Convertimos a lista de dicts para fácil manejo en el builder
    results = []
    for _, row in df.iterrows():
        results.append({
            "text": row['text'] or "",
            # Si extensions es None (sin adjuntos), ponemos string vacío
            "extensions": row['extensions'] if row['extensions'] else ""
        })
    
    return results