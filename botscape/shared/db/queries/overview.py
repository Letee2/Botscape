from botscape.shared.db.caching import read_sql

def get_daily_activity(start_iso: str, end_iso: str):
    return read_sql("SELECT CAST(date_utc AS DATE) AS day, COUNT(*) AS msgs FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s GROUP BY day ORDER BY day ASC;", params={"start": start_iso, "end": end_iso})

def get_top_bots_by_volume(start_iso: str, end_iso: str, limit: int = 8):
    return read_sql("SELECT LEFT(token, 32) AS token, COUNT(*) AS msgs, SUM(has_media) AS media FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s GROUP BY token ORDER BY msgs DESC LIMIT %(limit)s;", params={"start": start_iso, "end": end_iso, "limit": limit})

def get_botscape_scatter_data(start_iso: str, end_iso: str, limit: int = 100):
    return read_sql("""
    WITH msg AS (SELECT token, COUNT(*) AS msgs, SUM(has_media) AS media FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s GROUP BY token),
    ent AS (SELECT m.token, COUNT(e.id) AS ents FROM entities e JOIN messages m ON m.id = e.message_pk WHERE m.date_utc >= %(start)s AND date_utc < %(end)s GROUP BY m.token)
    SELECT b.token, COALESCE(msg.msgs,0) AS msgs, COALESCE(msg.media,0) AS media, COALESCE(ent.ents,0) AS ents
    FROM (SELECT DISTINCT token FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s) b
    LEFT JOIN msg ON b.token = msg.token LEFT JOIN ent ON b.token = ent.token ORDER BY msgs DESC LIMIT %(limit)s;
    """, params={"start": start_iso, "end": end_iso, "limit": limit})

def get_hourly_heatmap_data(start_iso: str, end_iso: str):
    return read_sql("SELECT CAST(date_utc AS DATE) AS day, EXTRACT(HOUR FROM date_utc) AS hour, COUNT(*) AS msgs FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s GROUP BY day, hour ORDER BY day, hour;", params={"start": start_iso, "end": end_iso})

def get_stacked_timeline_data(start_iso: str, end_iso: str, limit: int = 8):
    return read_sql("""
    WITH daily AS (SELECT token, CAST(date_utc AS DATE) AS day, COUNT(*) AS msgs FROM messages WHERE date_utc >= %(start)s AND date_utc < %(end)s GROUP BY token, day),
    tops AS (SELECT token, SUM(msgs) AS tot FROM daily GROUP BY token ORDER BY tot DESC LIMIT %(limit)s)
    SELECT d.day, d.token, d.msgs FROM daily d JOIN tops t ON t.token = d.token ORDER BY d.day ASC, t.tot DESC;
    """, params={"start": start_iso, "end": end_iso, "limit": limit})