from dataclasses import dataclass
from typing import Optional, List, Tuple
import psycopg # Importamos el nuevo driver
from .core import execute, executemany

# --- Los Dataclasses no cambian ---
@dataclass
class MessageRecord:
    token: str
    message_id: Optional[int]
    chat_id: Optional[str]
    chat_type: Optional[str]
    sender_id: Optional[str]
    date_utc: str
    text: Optional[str]
    text_sha1: Optional[str]
    has_media: bool
    media_path: Optional[str]
    raw_json: Optional[str]

@dataclass
class EntityRecord:
    etype: str
    value: str
    context_snippet: Optional[str]
    confidence: float

@dataclass
class AttachmentRecord:
    mime: Optional[str]
    size: Optional[int]
    sha256: Optional[str]
    path: str

# --- Las funciones de BBDD se actualizan ---

def upsert_bot(conn: psycopg.Connection, token: str, bot_id: Optional[int], username: Optional[str], display_name: Optional[str]) -> None:
    # Esta sintaxis SQL es compatible con PostgreSQL
    execute(conn, """
    INSERT INTO bots(token, bot_id, username, display_name, first_seen_utc, last_seen)
    VALUES(%s, %s, %s, %s, NOW(), NOW())
    ON CONFLICT(token) DO UPDATE SET
      bot_id=excluded.bot_id,
      username=COALESCE(excluded.username, bots.username),
      display_name=COALESCE(excluded.display_name, bots.display_name),
      last_seen=NOW();
    """, (token, bot_id, username, display_name))

def insert_message(conn: psycopg.Connection, m: MessageRecord) -> int:
    sql_insert = """
    INSERT INTO messages(
        token, message_id, chat_id, chat_type, sender_id, date_utc, 
        text, text_sha1, has_media, media_path, raw_json
    )
    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (token, message_id, date_utc) DO NOTHING
    RETURNING id;
    """
    
    params = (
        m.token, m.message_id, m.chat_id, m.chat_type, m.sender_id, m.date_utc, 
        m.text, m.text_sha1, int(m.has_media), m.media_path, m.raw_json
    )
    
    row = conn.execute(sql_insert, params).fetchone()
    
    if row:
        return int(row['id'])
    else:
        # Conflicto: recuperar ID existente
        sql_select = "SELECT id FROM messages WHERE token=%s AND message_id=%s AND date_utc=%s"
        row_select = conn.execute(sql_select, (m.token, m.message_id, m.date_utc)).fetchone()
        return int(row_select['id'])

def insert_entities_batch(conn: psycopg.Connection, message_pk: int, entities: List[EntityRecord]) -> None:
 
    if not entities:
        return

    rows: List[Tuple] = [
        (
            message_pk,
            e.etype,
            e.value,
            (e.context_snippet or None),
            (e.confidence if e.confidence is not None else 0.0),
        )
        for e in entities
    ]

    # Usamos '%s' como placeholder para psycopg
    sql = """
    INSERT INTO entities(message_pk, etype, value, context_snippet, confidence)
    VALUES(%s, %s, %s, %s, %s)
    ON CONFLICT (message_pk, etype, value) DO UPDATE SET
      confidence = CASE
        WHEN excluded.confidence > entities.confidence THEN excluded.confidence
        ELSE entities.confidence
      END,
      context_snippet = CASE
        WHEN (entities.context_snippet IS NULL OR entities.context_snippet = '')
             AND (excluded.context_snippet IS NOT NULL AND excluded.context_snippet <> '')
        THEN excluded.context_snippet
        ELSE entities.context_snippet
      END
    ;
    """
    executemany(conn, sql, rows)


def insert_attachments_batch(conn: psycopg.Connection, message_pk: int, atts: List[AttachmentRecord]) -> None:
    if not atts:
        return
    rows: List[Tuple] = [(message_pk, a.mime, a.size, a.sha256, a.path) for a in atts]
    executemany(conn, """
    INSERT INTO attachments(message_pk, mime, size, sha256, path)
    VALUES(%s, %s, %s, %s, %s);
    """, rows)


def upsert_hash_origin(conn: psycopg.Connection, token: str, sample_sha256: str) -> None:
    # Reemplazamos 'INSERT OR IGNORE' (SQLite) por 'ON CONFLICT DO NOTHING' (PG)
    execute(conn, """
    INSERT INTO hash_origin(token, sample_sha256) 
    VALUES(%s, %s)
    ON CONFLICT (token, sample_sha256) DO NOTHING;
    """, (token, sample_sha256))

def upsert_social_identity(conn: psycopg.Connection, tg_id: int, username: str, full_name: str, id_type: str) -> None:
    """Registra una identidad (Nodo del grafo)."""
    sql = """
    INSERT INTO social_identities (telegram_id, username, full_name, type, first_seen)
    VALUES (%s, %s, %s, %s, NOW())
    ON CONFLICT (telegram_id) DO UPDATE SET
        username = COALESCE(EXCLUDED.username, social_identities.username),
        full_name = COALESCE(EXCLUDED.full_name, social_identities.full_name);
    """
    execute(conn, sql, (tg_id, username, full_name, id_type))

def insert_social_edge(conn: psycopg.Connection, token: str, identity_id: int, relation: str, msg_pk: int) -> None:
    """Registra la conexión (Arista del grafo)."""
    sql = """
    INSERT INTO social_graph_edges (bot_token, identity_id, relation_type, message_pk, detected_at)
    VALUES (%s, %s, %s, %s, NOW())
    ON CONFLICT DO NOTHING;
    """
    execute(conn, sql, (token, identity_id, relation, msg_pk))