from botscape.shared.db.caching import read_sql # Usaremos caching.py (antes read.py)

def get_global_kpis(start_iso: str, end_iso: str):
    return read_sql("SELECT COUNT(DISTINCT token) AS bots, COUNT(*) AS msgs, SUM(has_media) AS media FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s;", params={"start": start_iso, "end": end_iso})

def get_global_entity_count(start_iso: str, end_iso: str):
    return read_sql("SELECT COUNT(*) AS ents FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s;", params={"start": start_iso, "end": end_iso})

def get_latest_message_timestamp():
    return read_sql("SELECT MAX(date_utc) AS maxdt FROM messages;")

def get_last_aggregation_date():
    return read_sql("SELECT MAX(date) AS last_aggr FROM metrics_bot_daily;")

def get_entity_types_distribution(start_iso: str, end_iso: str):
    """Distribución de tipos de entidades (email, ip, etc.)."""
    return read_sql("""
        SELECT e.etype, COUNT(*) AS cnt
        FROM entities e JOIN messages m ON m.id = e.message_pk
        WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s
        GROUP BY e.etype ORDER BY cnt DESC;
    """, params={"start": start_iso, "end": end_iso})

def get_top_entities_values(start_iso: str, end_iso: str, limit: int = 10):
    """Devuelve los valores de entidades más frecuentes por tipo (Top N)."""
    return read_sql("""
        WITH base AS (
          SELECT e.etype, e.value, COUNT(*) AS cnt
          FROM entities e JOIN messages m ON m.id = e.message_pk
          WHERE m.date_utc >= %(start)s AND m.date_utc < %(end)s
          GROUP BY e.etype, e.value
        ),
        ranked AS (
          SELECT etype, value, cnt, ROW_NUMBER() OVER (PARTITION BY etype ORDER BY cnt DESC) rn
          FROM base
        )
        SELECT etype, value, cnt
        FROM ranked WHERE rn <= %(limit)s
        ORDER BY etype, cnt DESC;
    """, params={"start": start_iso, "end": end_iso, "limit": limit})