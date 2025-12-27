from botscape.shared.db.caching import read_sql
import pandas as pd

from botscape.shared.db.core import get_conn

def get_filtered_messages(token: str, start_iso: str, end_iso: str, text_query: str = None, only_media: bool = False, etype: str = None, evalue: str = None, limit: int = 5000):
    
    where_clauses = ["m.token = %(token)s", "m.date_utc >= %(start)s", "m.date_utc < %(end)s"]
    params = {"token": token, "start": start_iso, "end": end_iso, "limit": limit}
    
    join_entities = False
    
    # MEJORA: Añadimos % automáticamente para búsqueda flexible (LIKE %texto%)
    if text_query: 
        where_clauses.append("m.text ILIKE %(text_q)s") # ILIKE para ignorar mayúsculas/minúsculas (Postgres)
        params["text_q"] = f"%{text_query}%"
        
    if only_media: 
        where_clauses.append("m.has_media = 1")
        
    if (etype and etype != "(cualquiera)") or evalue:
        join_entities = True
        if etype and etype != "(cualquiera)": 
            where_clauses.append("e.etype = %(etype)s")
            params["etype"] = etype
        if evalue: 
            where_clauses.append("e.value ILIKE %(evalue)s")
            params["evalue"] = f"%{evalue}%"

    # CORRECCIÓN CLAVE: 
    # 1. Seleccionamos 'm.text' completo (no snippet) para que el frontend no falle.
    # 2. Quitamos 'to_char' para que Pandas reciba un objeto datetime real.
    sql = f"""
        SELECT 
            m.id, 
            m.date_utc, 
            m.message_id, 
            m.chat_id, 
            m.sender_id, 
            m.text,  
            m.has_media 
        FROM messages m 
        {'JOIN entities e ON e.message_pk = m.id' if join_entities else ''} 
        WHERE {' AND '.join(where_clauses)} 
        ORDER BY m.date_utc DESC 
        LIMIT %(limit)s;
    """
    
    return read_sql(sql, params=params)

def get_message_detail(message_pk: int):
    return read_sql("SELECT m.id, m.token, to_char(m.date_utc, 'YYYY-MM-DD HH24:MI:SS') AS date_utc, m.message_id, m.chat_id, m.sender_id, m.text, m.has_media, m.media_path FROM messages m WHERE m.id = %(id)s;", params={"id": message_pk})

def get_message_entities(message_pk: int):
    return read_sql("SELECT etype, value, LEFT(context_snippet, 180) AS context_snippet FROM entities WHERE message_pk = %(id)s ORDER BY etype, value LIMIT 2000;", params={"id": message_pk})

def get_message_attachments(message_pk: int):
    return read_sql("SELECT mime, size, path FROM attachments WHERE message_pk = %(id)s ORDER BY id DESC;", params={"id": message_pk})


def get_filtered_messages(token: str, start_iso: str, end_iso: str, text_query: str = None, only_media: bool = False, etype: str = None, evalue: str = None, limit: int = 5000):
    """Recupera mensajes filtrados para la tabla principal."""
    where_clauses = ["m.token = %(token)s", "m.date_utc >= %(start)s", "m.date_utc < %(end)s"]
    params = {"token": token, "start": start_iso, "end": end_iso, "limit": limit}
    
    join_entities = False
    
    if text_query: 
        where_clauses.append("m.text ILIKE %(text_q)s")
        params["text_q"] = f"%{text_query}%"
        
    if only_media: 
        where_clauses.append("m.has_media = 1")
        
    if (etype and etype != "(cualquiera)") or evalue:
        join_entities = True
        if etype and etype != "(cualquiera)": 
            where_clauses.append("e.etype = %(etype)s")
            params["etype"] = etype
        if evalue: 
            where_clauses.append("e.value ILIKE %(evalue)s")
            params["evalue"] = f"%{evalue}%"

    sql = f"""
        SELECT 
            m.id, 
            m.date_utc, 
            m.message_id, 
            m.chat_id, 
            m.sender_id, 
            m.text,  
            m.has_media 
        FROM messages m 
        {'JOIN entities e ON e.message_pk = m.id' if join_entities else ''} 
        WHERE {' AND '.join(where_clauses)} 
        ORDER BY m.date_utc DESC 
        LIMIT %(limit)s;
    """
    return read_sql(sql, params=params)

def get_message_detail(msg_id: int):
    """Recupera toda la info de un mensaje específico."""
    sql = """
        SELECT m.*, b.display_name as bot_name, b.c2_webhook_url 
        FROM messages m 
        LEFT JOIN bots b ON m.token = b.token 
        WHERE m.id = %(id)s
    """
    return read_sql(sql, params={'id': msg_id})

def get_message_entities(msg_id: int):
    """Recupera entidades extraídas (emails, urls, etc)."""
    sql = "SELECT type, value, confidence FROM entities WHERE message_pk = %(id)s"
    return read_sql(sql, params={'id': msg_id})

def get_message_attachments(msg_id: int):
    """Recupera archivos adjuntos."""
    sql = "SELECT filename, mime, size, path FROM attachments WHERE message_id = %(id)s"
    return read_sql(sql, params={'id': msg_id})

# ==============================================================================
# 2. TRAZABILIDAD Y FORENSE (LA FUNCIÓN QUE FALTABA)
# ==============================================================================

def get_message_trace(text: str):
    """
    Recupera la línea de tiempo completa de un mensaje exacto para graficar su ruta.
    """
    if not text: return pd.DataFrame()
    sql = """
        SELECT 
            m.date_utc, 
            m.sender_id, 
            m.sender_first_name, 
            m.chat_id, 
            m.chat_title, 
            m.chat_type, 
            m.token, 
            b.display_name, 
            b.c2_webhook_url, 
            m.forward_from_name
        FROM messages m 
        JOIN bots b ON m.token = b.token
        WHERE m.text = %(text)s 
        ORDER BY m.date_utc ASC
    """
    conn = get_conn()
    try:
        return pd.read_sql(sql, conn, params={'text': text})
    finally:
        conn.close()

# ==============================================================================
# 3. ESTADÍSTICAS GLOBALES (MACRO VIEW)
# ==============================================================================

def get_global_metrics(days=30):
    """Devuelve estadísticas de alto nivel para el Dashboard Macro."""
    conn = get_conn()
    try:
        metrics = {}
        
        # 1. Totales
        sql_totals = """
            SELECT COUNT(*) as msgs, COUNT(DISTINCT sender_id) as actors, COUNT(DISTINCT chat_id) as chans
            FROM messages 
            WHERE date_utc > NOW() - INTERVAL '%(d)s days'
        """
        df_tot = pd.read_sql(sql_totals, conn, params={'d': days})
        metrics['totals'] = df_tot.iloc[0] if not df_tot.empty else {'msgs':0, 'actors':0, 'chans':0}
        
        # 2. Actividad Diaria
        sql_daily = """
            SELECT DATE(date_utc) as dia, COUNT(*) as volumen
            FROM messages 
            WHERE date_utc > NOW() - INTERVAL '%(d)s days'
            GROUP BY 1 ORDER BY 1
        """
        metrics['daily'] = pd.read_sql(sql_daily, conn, params={'d': days})
        
        # 3. Top Bots
        sql_bots = """
            SELECT b.display_name, COUNT(*) as cnt
            FROM messages m JOIN bots b ON m.token = b.token
            WHERE m.date_utc > NOW() - INTERVAL '%(d)s days'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """
        metrics['top_bots'] = pd.read_sql(sql_bots, conn, params={'d': days})

        # 4. Top Canales
        sql_chans = """
            SELECT chat_title, COUNT(*) as cnt
            FROM messages
            WHERE date_utc > NOW() - INTERVAL '%(d)s days'
              AND chat_type IN ('channel', 'supergroup')
            GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """
        metrics['top_chans'] = pd.read_sql(sql_chans, conn, params={'d': days})
        
        return metrics
    finally:
        conn.close()