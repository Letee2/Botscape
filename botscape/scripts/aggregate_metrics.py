import os
import sys
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from langdetect import DetectorFactory, LangDetectException, detect

from botscape.config import settings

from botscape.dashboard.modules.stopwords import COMMON_STOPS
from botscape.shared.db.core import get_conn
from botscape.shared.utils.templating import generate_structure_signature

try:
    DetectorFactory.seed = 0
except Exception:
    pass

TOKEN_RE = re.compile(r"[\w\d]+")

def iso_date(d):
    return d.strftime("%Y-%m-%d")


# ==================================
# AGREGACIÓN: BOT DIARIO
# ==================================
def compute_bot_daily(conn, date_str: str) -> None:
    """
    Rellena/actualiza metrics_bot_daily para una fecha (UTC) concreta.
    """
    print(f"  -> Agregando métricas de bots para {date_str}...")
    cur = conn.cursor()
    # Ventana del día [00:00, 24:00) UTC
    day_start = f"{date_str}T00:00:00Z"
    next_day = (datetime.fromisoformat(date_str) + timedelta(days=1)).date().isoformat()
    day_end = f"{next_day}T00:00:00Z"

    # Mensajes por bot (usando placeholders %s)
    cur.execute("""
    WITH base AS (
      SELECT token,
             COUNT(*) AS messages_count,
             SUM(has_media) AS has_media_count,
             MIN(date_utc) AS first_seen_day,
             MAX(date_utc) AS last_seen_day
      FROM messages
      WHERE date_utc >= %s AND date_utc < %s
      GROUP BY token
    ),
    ents AS (
      SELECT m.token, COUNT(e.id) AS entities_count
      FROM entities e
      JOIN messages m ON m.id = e.message_pk
      WHERE m.date_utc >= %s AND m.date_utc < %s
      GROUP BY m.token
    )
    SELECT b.token,
           b.messages_count,
           COALESCE(e.entities_count, 0) AS entities_count,
           COALESCE(b.has_media_count, 0) AS has_media_count,
           b.first_seen_day, b.last_seen_day
    FROM base b
    LEFT JOIN ents e ON e.token = b.token;
    """, (day_start, day_end, day_start, day_end))
    rows = cur.fetchall()

    if not rows:
        return

    # Usamos un cursor para executemany (aunque un loop de execute también funciona)
    with conn.cursor() as insert_cur:
        for r in rows:
            insert_cur.execute("""
            INSERT INTO metrics_bot_daily(date, token, messages_count, entities_count, has_media_count, first_seen, last_seen)
            VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(date, token) DO UPDATE SET
               messages_count=excluded.messages_count,
               entities_count=excluded.entities_count,
               has_media_count=excluded.has_media_count,
               first_seen=excluded.first_seen,
               last_seen=excluded.last_seen;
            """, (date_str, r["token"], r["messages_count"], r["entities_count"], r["has_media_count"], r["first_seen_day"], r["last_seen_day"]))
    conn.commit()


# ==================================
# AGREGACIÓN: PLANTILLAS DE TEXTO (MEJORADA)
# ==================================
def compute_text_templates(conn, days_back: int = 7) -> None:
    """
    Recalcula métricas de plantillas. 
    Ahora guarda la FIRMA ESTRUCTURAL legible en 'example_text' en lugar de un mensaje raw aleatorio.
    """
    print(f"  -> Agregando plantillas de texto (últimos {days_back} días)...")
    cur = conn.cursor()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat() + "T00:00:00Z"

    # 1. Agrupamos por text_sha1 (que ahora es el hash de la estructura)
    cur.execute("""
    WITH recent AS (
      SELECT text_sha1, text, token
      FROM messages
      WHERE text_sha1 IS NOT NULL AND date_utc >= %s
    ),
    agg AS (
      SELECT text_sha1,
             -- Tomamos cualquier texto raw para generar la firma de nuevo y asegurarnos
             MIN(text) AS sample_raw_text,
             COUNT(*) AS cnt,
             MAX(token) as sample_token -- Solo para referencia
      FROM recent
      GROUP BY text_sha1
      HAVING COUNT(*) >= 2
    ),
    sample_tokens AS (
      SELECT text_sha1,
             STRING_AGG(DISTINCT token, ',') AS tokens_sample
      FROM recent
      GROUP BY text_sha1
    )
    SELECT a.text_sha1, a.sample_raw_text, a.cnt, s.tokens_sample
    FROM agg a
    LEFT JOIN sample_tokens s USING(text_sha1)
    """, (since,))
    
    rows = cur.fetchall()
    if not rows:
        return

    print(f"     Procesando {len(rows)} plantillas únicas...")
    
    with conn.cursor() as insert_cur:
        for r in rows:
            # --- MEJORA CRÍTICA: Generamos la firma legible ---
            # Esto asegura que en la BBDD se guarde "Login: <EMAIL>" y no "Login: pepe@gmail"
            # aunque el worker ya haya hecho el hash, aquí recuperamos el texto legible.
            readable_template = generate_structure_signature(r["sample_raw_text"])
            
            insert_cur.execute("""
            INSERT INTO metrics_text_templates(text_sha1, example_text, count, last_seen, tokens_sample)
            VALUES(%s, %s, %s, NOW(), %s)
            ON CONFLICT(text_sha1) DO UPDATE SET
               example_text=excluded.example_text, -- Actualizamos con la plantilla limpia
               count=excluded.count,
               last_seen=NOW(),
               tokens_sample=excluded.tokens_sample;
            """, (r["text_sha1"], readable_template, r["cnt"], r["tokens_sample"]))
    
    conn.commit()


# ==================================
# AGREGACIÓN: IDIOMAS (NUEVO)
# ==================================
def compute_language_daily(conn, date_str: str) -> None:
    """
    Agrega métricas de idioma para un día específico.
    """
    print(f"  -> Agregando idiomas para {date_str}...")
    day_start = f"{date_str}T00:00:00Z"
    next_day = (datetime.fromisoformat(date_str) + timedelta(days=1)).date().isoformat()
    day_end = f"{next_day}T00:00:00Z"

    cur = conn.cursor()
    cur.execute(
        "SELECT text FROM messages WHERE date_utc >= %s AND date_utc < %s AND text IS NOT NULL",
        (day_start, day_end)
    )
    
    lang_counts = Counter()
    
    for row in cur:
        text = row["text"]
        if not text or not text.strip():
            continue
        try:
            lang = detect(text)
            lang_counts[lang] += 1
        except LangDetectException:
            pass # Ignoramos texto no fiable/corto
        except Exception:
            pass # Ignoramos otros errores

    if not lang_counts:
        return

    # Insertar en la nueva tabla
    rows_to_insert = [
        (date_str, lang, count) for lang, count in lang_counts.items()
    ]
    
    with conn.cursor() as insert_cur:
        insert_cur.executemany("""
        INSERT INTO metrics_language_daily(date, language, count)
        VALUES(%s, %s, %s)
        ON CONFLICT(date, language) DO UPDATE SET
           count=excluded.count;
        """, rows_to_insert)
    conn.commit()
    print(f"      ... {len(rows_to_insert)} idiomas guardados.")

# ==================================
# AGREGACIÓN: PALABRAS (NUEVO)
# ==================================
def compute_word_daily(conn, date_str: str) -> None:
    """
    Agrega métricas de palabras (tokens) para un día específico.
    """
    print(f"  -> Agregando palabras para {date_str}...")
    day_start = f"{date_str}T00:00:00Z"
    next_day = (datetime.fromisoformat(date_str) + timedelta(days=1)).date().isoformat()
    day_end = f"{next_day}T00:00:00Z"

    cur = conn.cursor()
    cur.execute(
        "SELECT text FROM messages WHERE date_utc >= %s AND date_utc < %s AND text IS NOT NULL",
        (day_start, day_end)
    )

    word_counts = Counter()

    for row in cur:
        text = row["text"]
        if not text or not text.strip():
            continue
        
        words = TOKEN_RE.findall(text.lower())
        filtered = [
            w for w in words 
            if w not in COMMON_STOPS 
            and len(w) >= 3 # Mismo filtro que antes
            and not w.isnumeric()
        ]
        word_counts.update(filtered)

    if not word_counts:
        return

    # Insertar en la nueva tabla (solo el Top 1000 del día para no saturar)
    rows_to_insert = [
        (date_str, word, count) for word, count in word_counts.most_common(1000)
    ]
    
    with conn.cursor() as insert_cur:
        insert_cur.executemany("""
        INSERT INTO metrics_word_daily(date, word, count)
        VALUES(%s, %s, %s)
        ON CONFLICT(date, word) DO UPDATE SET
           count=excluded.count;
        """, rows_to_insert)
    conn.commit()
    print(f"      ... {len(rows_to_insert)} palabras guardadas.")

# ==================================
# FUNCIÓN PRINCIPAL (Resumida)
# ==================================
# Copia aquí las funciones compute_bot_daily, compute_language_daily, compute_word_daily del archivo original
# y usa esta versión de compute_text_templates.

def main():
    conn = get_conn()
    today = datetime.now(timezone.utc).date()
    print(f"Iniciando agregación para {today}")
    
    compute_bot_daily(conn, iso_date(today))
    compute_language_daily(conn, iso_date(today))
    compute_word_daily(conn, iso_date(today))
    
    # Llamamos a la nueva función mejorada
    compute_text_templates(conn, days_back=30) # Aumentamos a 30 días para cubrir más histórico
    
    conn.close()
    print("\n✅ Agregaciones actualizadas.")

if __name__ == "__main__":
    main()