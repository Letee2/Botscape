from botscape.shared.db.caching import read_sql

def get_entity_types_stats(start_iso: str, end_iso: str):
    return read_sql("SELECT e.etype, COUNT(*) AS cnt FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s GROUP BY e.etype ORDER BY cnt DESC;", params={"start": start_iso, "end": end_iso})

def get_raw_entities_sample(start_iso: str, end_iso: str, etype: str = None, value_like: str = None, limit: int = 100000):
    where = ["m.date_utc >= %(start)s", "m.date_utc < %(end)s"]
    params = {"start": start_iso, "end": end_iso, "limit": limit}
    if etype and etype != "(todos)": where.append("e.etype = %(etype)s"); params["etype"] = etype
    if value_like: where.append("e.value LIKE %(val)s"); params["val"] = value_like
    sql = f"SELECT e.etype, e.value, m.token, to_char(m.date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, m.id AS message_pk FROM entities e JOIN messages m ON m.id = e.message_pk WHERE {' AND '.join(where)} LIMIT %(limit)s;"
    return read_sql(sql, params=params)

def get_entities_by_type(start_iso: str, end_iso: str, etype: str):
    return read_sql("SELECT e.message_pk, e.value FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s AND e.etype = %(etype)s;", params={"start": start_iso, "end": end_iso, "etype": etype})

def get_messages_by_ids(msg_ids: list):
    """
    Recupera detalles de mensajes basados en una lista de IDs.
    Usa ANY() para compatibilidad robusta con arrays en Postgres.
    """
    if not msg_ids: 
        # Devuelve DF vacío con las columnas correctas para evitar KeyErrors posteriores
        return read_sql("SELECT id AS message_pk, token, date_utc, text AS snippet, has_media FROM messages WHERE 1=0;")
    ids_list = list(msg_ids)
    
    
    return read_sql("""
        SELECT 
            m.id AS message_pk, 
            m.token, 
            to_char(m.date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, 
            LEFT(m.text, 240) AS snippet, 
            m.has_media 
        FROM messages m 
        WHERE m.id = ANY(%(ids)s)
    """, params={"ids": ids_list})

def get_top_entities_values(start_iso: str, end_iso: str, limit: int = 10):
    return read_sql("""
    WITH base AS (SELECT e.etype, e.value, COUNT(*) AS cnt FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s GROUP BY e.etype, e.value),
    ranked AS (SELECT etype, value, cnt, ROW_NUMBER() OVER (PARTITION BY etype ORDER BY cnt DESC) rn FROM base)
    SELECT etype, value, cnt FROM ranked WHERE rn <= %(limit)s ORDER BY etype, cnt DESC;
    """, params={"start": start_iso, "end": end_iso, "limit": limit})