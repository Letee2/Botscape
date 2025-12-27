from botscape.shared.db.caching import read_sql
def get_channel_leaderboard(start_iso: str, end_iso: str, limit: int = 100, types: list = None):
    """
    Obtiene ranking de chats.
    """
    
    # Construcción dinámica del WHERE para los tipos
    type_clause = ""
    params = {"start": start_iso, "end": end_iso, "limit": limit}
    
    if types:
        type_clause = "AND chat_type = ANY(%(types)s)"
        params["types"] = types

    sql = f"""
    SELECT
        chat_id,
        chat_type, -- Incluimos el tipo en la respuesta
        COUNT(*) AS total_messages,
        COUNT(DISTINCT token) AS unique_bots,
        COUNT(DISTINCT sender_id) AS unique_senders,
        TO_CHAR(MIN(date_utc), 'YYYY-MM-DD HH24:MI:SS') AS first_seen,
        TO_CHAR(MAX(date_utc), 'YYYY-MM-DD HH24:MI:SS') AS last_seen
    FROM messages
    WHERE
        chat_id IS NOT NULL
        AND date_utc >= %(start)s
        AND date_utc < %(end)s
        {type_clause}
    GROUP BY chat_id, chat_type
    ORDER BY total_messages DESC
    LIMIT %(limit)s;
    """
    return read_sql(sql, params=params)

def get_channel_bot_activity(chat_id: str, start_iso: str, end_iso: str):
    return read_sql("SELECT token, COUNT(*) AS message_count FROM messages WHERE chat_id = %(chat_id)s AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY token ORDER BY message_count DESC LIMIT 25;", params={"chat_id": str(chat_id), "start": start_iso, "end": end_iso})

def get_channel_sender_activity(chat_id: str, start_iso: str, end_iso: str):
    return read_sql("SELECT sender_id, COUNT(*) AS message_count FROM messages WHERE chat_id = %(chat_id)s AND sender_id IS NOT NULL AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY sender_id ORDER BY message_count DESC LIMIT 25;", params={"chat_id": str(chat_id), "start": start_iso, "end": end_iso})

def get_channel_timeline(chat_id: str, start_iso: str, end_iso: str):
    return read_sql("SELECT CAST(date_utc AS DATE) AS day, COUNT(*) as count FROM messages WHERE chat_id = %(chat_id)s AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY day ORDER BY day ASC;", params={"chat_id": str(chat_id), "start": start_iso, "end": end_iso})

def get_channel_recent_messages(chat_id: str, start_iso: str, end_iso: str, limit: int = 50):
    return read_sql("SELECT TO_CHAR(date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, token, sender_id, SUBSTRING(text FROM 1 FOR 150) AS snippet, has_media FROM messages WHERE chat_id = %(chat_id)s AND date_utc >= %(start)s AND date_utc < %(end)s ORDER BY date_utc DESC LIMIT %(limit)s;", params={"chat_id": str(chat_id), "start": start_iso, "end": end_iso, "limit": limit})