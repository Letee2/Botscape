# botscape/shared/db/actions.py
from botscape.shared.db.core import execute_sql, get_conn
import json
import logging

def set_bot_status(token: str, is_active: bool) -> bool:
    """
    Activa o desactiva la monitorización de un bot.
    """
    sql = """
        UPDATE bots 
        SET is_active = %(active)s, last_checked_utc = NOW() 
        WHERE token = %(token)s
    """
    return execute_sql(sql, params={"token": token, "active": is_active})

def add_monitored_asset(asset_type: str, asset_value: str, description: str) -> bool:
    """Añade un nuevo activo a la lista de vigilancia."""
    sql = """
        INSERT INTO monitored_assets (asset_type, asset_value, description)
        VALUES (%(type)s, %(value)s, %(desc)s)
        ON CONFLICT (asset_type, asset_value) DO NOTHING;
    """
    return execute_sql(sql, params={"type": asset_type, "value": asset_value, "desc": description})

def delete_monitored_asset(asset_id: int) -> bool:
    """Elimina un activo de la lista."""
    sql = "DELETE FROM monitored_assets WHERE id = %(id)s"
    return execute_sql(sql, params={"id": asset_id})

def save_bot_profile(token: str, profile_data: dict, model_version: str) -> bool:
    """
    Guarda el perfil generado por IA y actualiza las etiquetas semánticas.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # 1. Guardar Perfil (Tabla bot_profiles)
            sql_profile = """
                INSERT INTO bot_profiles (
                    token, risk_level, actor_intent, summary, detected_ttps, model_version, analyzed_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (token) DO UPDATE SET
                    risk_level = excluded.risk_level,
                    actor_intent = excluded.actor_intent,
                    summary = excluded.summary,
                    detected_ttps = excluded.detected_ttps,
                    model_version = excluded.model_version,
                    analyzed_at = NOW();
            """
            
            ttps_json = json.dumps(profile_data.get("detected_ttps", []))
            
            cur.execute(sql_profile, (
                token,
                profile_data.get("risk_level", "UNKNOWN"),
                profile_data.get("actor_intent", "Unknown"),
                profile_data.get("summary", ""),
                ttps_json,
                model_version
            ))
            
            # 2. GESTIÓN DE ETIQUETAS (TAGGING DINÁMICO)
            new_tags = profile_data.get("tags", [])
            
            # A) Borrar asociaciones antiguas para este bot (Clean Slate)
            cur.execute("DELETE FROM bot_tag_map WHERE bot_token = %s", (token,))
            
            if new_tags:
                # Normalizamos etiquetas: Mayúsculas primera letra, strip
                clean_tags = list(set([t.strip().title() for t in new_tags if t]))
                
                for tag in clean_tags:
                    # B) Insertar Tag si no existe y obtener ID
                    # Usamos una técnica CTE para manejar el "Get or Create" en Postgres de forma atómica
                    cur.execute("""
                        WITH s AS (
                            SELECT id FROM bot_tags WHERE tag = %s
                        ), i AS (
                            INSERT INTO bot_tags (tag)
                            SELECT %s
                            WHERE NOT EXISTS (SELECT 1 FROM s)
                            RETURNING id
                        )
                        SELECT id FROM i UNION ALL SELECT id FROM s;
                    """, (tag, tag))
                    
                    tag_id_row = cur.fetchone()
                    if tag_id_row:
                        tag_id = tag_id_row['id'] # Al usar dict_row factory
                        
                        # C) Crear el vínculo
                        cur.execute("""
                            INSERT INTO bot_tag_map (bot_token, tag_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (token, tag_id))

        conn.commit()
        return True

    except Exception as e:
        logging.error(f"❌ Error guardando perfil/tags: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()