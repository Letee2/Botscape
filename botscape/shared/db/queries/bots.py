from botscape.shared.db.caching import read_sql

def get_bot_kpis(token: str, start_iso: str, end_iso: str):
    return read_sql("""
    WITH msg AS (SELECT COUNT(*) AS msgs, SUM(has_media) AS media, MIN(date_utc) AS first_seen_w, MAX(date_utc) AS last_seen_w FROM messages WHERE token = %(token)s AND date_utc >= %(start)s AND date_utc < %(end)s),
    ent AS (SELECT COUNT(*) AS ents FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.token = %(token)s AND m.date_utc >= %(start)s AND m.date_utc < %(end)s),
    glob AS (SELECT first_seen_utc, last_seen, is_active FROM bots WHERE token = %(token)s)
    SELECT msg.msgs, COALESCE(msg.media,0) AS media, COALESCE(ent.ents,0) AS ents, glob.first_seen_utc, glob.last_seen, msg.first_seen_w, msg.last_seen_w, glob.is_active
    FROM msg, ent, glob;
    """, params={"token": token, "start": start_iso, "end": end_iso})

def get_bot_tags(token: str):
    return read_sql("SELECT t.tag, t.description FROM bot_tags t JOIN bot_tag_map m ON t.id = m.tag_id WHERE m.bot_token = %(token)s", params={"token": token})

def get_bot_daily_evolution(token: str, start_iso: str, end_iso: str):
    return read_sql("SELECT CAST(date_utc AS DATE) AS day, COUNT(*) AS msgs, SUM(has_media) AS media FROM messages WHERE token = %(token)s AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY day ORDER BY day ASC;", params={"token": token, "start": start_iso, "end": end_iso})

def get_bot_hourly_heatmap(token: str, start_iso: str, end_iso: str):
    return read_sql("SELECT EXTRACT(HOUR FROM date_utc) AS hour, COUNT(*) AS msgs FROM messages WHERE token = %(token)s AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY hour ORDER BY hour;", params={"token": token, "start": start_iso, "end": end_iso})

def get_bot_entity_types(token: str, start_iso: str, end_iso: str):
    return read_sql("SELECT e.etype, COUNT(*) AS cnt FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.token = %(token)s AND m.date_utc >= %(start)s AND m.date_utc < %(end)s GROUP BY e.etype ORDER BY cnt DESC;", params={"token": token, "start": start_iso, "end": end_iso})

def get_bot_top_entity_values(token: str, start_iso: str, end_iso: str, limit: int):
    return read_sql("""
    WITH base AS (SELECT e.etype, e.value, COUNT(*) AS cnt FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.token = %(token)s AND m.date_utc >= %(start)s AND m.date_utc < %(end)s GROUP BY e.etype, e.value),
    ranked AS (SELECT etype, value, cnt, ROW_NUMBER() OVER (PARTITION BY etype ORDER BY cnt DESC) rn FROM base)
    SELECT etype, value, cnt FROM ranked WHERE rn <= %(limit)s ORDER BY etype, cnt DESC;
    """, params={"token": token, "start": start_iso, "end": end_iso, "limit": limit})

def get_bot_text_templates(token: str, start_iso: str, end_iso: str):
    return read_sql("""
    WITH recent AS (SELECT text_sha1, text, date_utc FROM messages WHERE token = %(token)s AND date_utc >= %(start)s AND date_utc < %(end)s AND text_sha1 IS NOT NULL),
    agg AS (SELECT text_sha1, MIN(text) AS example_text, COUNT(*) AS cnt, MAX(date_utc) AS last_seen FROM recent GROUP BY text_sha1)
    SELECT text_sha1, cnt, to_char(last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen, LEFT(example_text, 300) AS example_text FROM agg ORDER BY cnt DESC LIMIT 20;
    """, params={"token": token, "start": start_iso, "end": end_iso})

def get_bot_media_gallery(token: str, start_iso: str, end_iso: str, limit: int = 100):
    return read_sql("SELECT a.path, a.mime, a.size, m.date_utc, m.message_id FROM attachments a JOIN messages m ON m.id = a.message_pk WHERE m.token = %(token)s AND m.date_utc >= %(start)s AND m.date_utc < %(end)s ORDER BY m.date_utc DESC LIMIT %(limit)s;", params={"token": token, "start": start_iso, "end": end_iso, "limit": limit})

def export_bot_messages(token: str, start_iso: str, end_iso: str, limit: int = 5000):
    return read_sql("SELECT id, to_char(date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, message_id, chat_id, sender_id, text, has_media, media_path FROM messages WHERE token = %(token)s AND date_utc >= %(start)s AND date_utc < %(end)s ORDER BY date_utc DESC LIMIT %(limit)s;", params={"token": token, "start": start_iso, "end": end_iso, "limit": limit})

def export_bot_entities(token: str, start_iso: str, end_iso: str, limit: int = 20000):
    return read_sql("SELECT e.etype, e.value, to_char(m.date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, m.message_id FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.token = %(token)s AND m.date_utc >= %(start)s AND m.date_utc < %(end)s ORDER BY m.date_utc DESC LIMIT %(limit)s;", params={"token": token, "start": start_iso, "end": end_iso, "limit": limit})

def get_bot_operators(token: str):
    """
    Recupera operadores únicos, mostrando la última vez que fueron vistos
    y cuántas interacciones han tenido (fuerza de la relación).
    """
    return read_sql("""
        SELECT 
            op.telegram_id,
            op.username,
            op.full_name,
            op.type, -- 'USER' o 'CHANNEL'
            rel.relation_type, -- 'FORWARD_FROM', 'FORWARD_TO'
            
            -- AGREGACIÓN: Tomamos la fecha más reciente
            to_char(MAX(rel.detected_at), 'YYYY-MM-DD HH24:MI') as last_detected,
            
            -- METRICA: Cuántas veces hemos visto esta relación (Fuerza)
            COUNT(rel.message_pk) as interaction_count
            
        FROM social_graph_edges rel
        JOIN social_identities op ON rel.identity_id = op.telegram_id
        WHERE rel.bot_token = %(token)s
        
        -- CLAVE: Agrupamos por la identidad y el tipo de relación
        GROUP BY 
            op.telegram_id, 
            op.username, 
            op.full_name, 
            op.type, 
            rel.relation_type
            
        ORDER BY MAX(rel.detected_at) DESC;
    """, params={"token": token})