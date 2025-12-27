# botscape/shared/db/queries/graph.py

from botscape.shared.db.caching import read_sql
import pandas as pd

def get_graph_nodes_bots(tokens: list = None):
    # AÑADIDO: first_seen_utc para la Timeline
    if tokens: 
        return read_sql("SELECT token, is_active, first_seen_utc FROM bots WHERE token = ANY(%(tokens)s);", params={"tokens": tokens})
    return read_sql("SELECT token, is_active, first_seen_utc FROM bots;")

def get_graph_nodes_tags(tokens: list = None):
    sql = "SELECT t.tag, m.bot_token AS token FROM bot_tags t JOIN bot_tag_map m ON t.id = m.tag_id"
    if tokens: 
        sql += " WHERE m.bot_token = ANY(%(tokens)s)"
        return read_sql(sql, params={"tokens": tokens})
    return read_sql(sql)

def get_graph_edges_hashes(tokens: list = None, hashes: list = None):
    # AÑADIDO: first_seen para la Timeline
    if tokens: 
        return read_sql("SELECT token, sample_sha256, first_seen FROM hash_origin WHERE token = ANY(%(tokens)s);", params={"tokens": tokens})
    if hashes: 
        return read_sql("SELECT token, sample_sha256, first_seen FROM hash_origin WHERE sample_sha256 = ANY(%(hashes)s);", params={"hashes": hashes})
    return read_sql("SELECT token, sample_sha256, first_seen FROM hash_origin;")

def get_graph_edges_chats(tokens: list = None, chat_ids: list = None):
    """
    Recupera las aristas entre Bots y Chats.
    [ACTUALIZADO]: Ahora incluye 'chat_type' para distinguir Actores de Infraestructura.
    """
    # Seleccionamos también chat_type
    base_sql = """
        SELECT DISTINCT token, chat_id, chat_type 
        FROM messages 
        WHERE chat_id IS NOT NULL AND token IS NOT NULL
    """
    
    if tokens: 
        return read_sql(f"{base_sql} AND token = ANY(%(tokens)s);", params={"tokens": tokens})
    if chat_ids: 
        return read_sql(f"{base_sql} AND chat_id = ANY(%(ids)s);", params={"ids": chat_ids})
        
    return read_sql(f"{base_sql};")


def get_bot_hashes(token: str):
    return read_sql("SELECT sample_sha256 FROM hash_origin WHERE token = %(token)s", params={"token": token})

def get_bot_chats(token: str):
    return read_sql("SELECT DISTINCT chat_id FROM messages WHERE token = %(token)s AND chat_id IS NOT NULL", params={"token": token})

def get_hash_bots(sample_sha256: str):
    return read_sql("SELECT token FROM hash_origin WHERE sample_sha256 = %(hash)s", params={"hash": sample_sha256})


def get_similarity_edges(hashes: list = None, min_score: int = 80):
    """
    Recupera enlaces de similitud entre muestras de malware.
    """
    sql = """
        SELECT sha256_a, sha256_b, score, method 
        FROM malware_similarity_links
        WHERE score >= %(min_score)s
    """
    params = {"min_score": min_score}
    
    if hashes:
        # Filtramos si cualquiera de los dos extremos está en nuestra lista de hashes visibles
        sql += " AND (sha256_a = ANY(%(hashes)s) OR sha256_b = ANY(%(hashes)s))"
        params["hashes"] = hashes
    
    # Ordenamos por score para priorizar las conexiones fuertes si hay límite
    sql += " ORDER BY score DESC LIMIT 2000;" 
    
    return read_sql(sql, params=params)


def get_graph_nodes_operators(tokens: list = None):
    """Obtiene nodos de Operadores (Humanos/Canales) conectados a los bots."""
    sql = """
        SELECT DISTINCT 
            op.telegram_id, 
            op.username, 
            op.full_name, 
            op.type 
        FROM social_identities op
        JOIN social_graph_edges rel ON op.telegram_id = rel.identity_id
    """
    if tokens:
        sql += " WHERE rel.bot_token = ANY(%(tokens)s)"
        return read_sql(sql, params={"tokens": tokens})
    return read_sql(sql)

def get_graph_edges_social(tokens: list = None):
    """Obtiene aristas Bot <-> Operador."""
    sql = """
        SELECT bot_token, identity_id, relation_type 
        FROM social_graph_edges
    """
    if tokens:
        sql += " WHERE bot_token = ANY(%(tokens)s)"
        return read_sql(sql, params={"tokens": tokens})
    return read_sql(sql)

def get_graph_edges_c2(tokens: list = None):
    """Obtiene aristas Bot -> Webhook URL."""
    # Filtramos vacíos y nulos para no ensuciar el grafo
    sql = """
        SELECT token, c2_webhook_url 
        FROM bots 
        WHERE c2_webhook_url IS NOT NULL AND c2_webhook_url != ''
    """
    if tokens:
        sql += " AND token = ANY(%(tokens)s)"
        return read_sql(sql, params={"tokens": tokens})
    return read_sql(sql)