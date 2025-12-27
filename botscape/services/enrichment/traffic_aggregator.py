import logging
from botscape.shared.db.core import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [TRAFFIC] %(message)s")

def aggregate_actor_traffic():
    """
    Calcula los flujos de tráfico (Sankey).
    """
    conn = get_conn()
    try:
        logging.info("🔄 Iniciando agregación de tráfico (In/Out/Lateral)...")
        
        # 1. Limpieza inicial
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE intel_traffic_flow;")
        conn.commit()

        # 2. Obtener lista de actores
        with conn.cursor() as cur:
            cur.execute("SELECT sender_id FROM operator_profiles WHERE role IN ('COMMANDER', 'COLLECTOR')")
            actors = [row['sender_id'] for row in cur.fetchall()]
        
        logging.info(f"👥 Procesando {len(actors)} actores...")

        total_in = 0
        total_out = 0
        total_lat = 0
        
        for idx, actor_id in enumerate(actors):
            try:
                with conn.cursor() as cur:
                    # --- PASO 0: IDENTIFICAR FLOTA ---
                    cur.execute("""
                        SELECT DISTINCT token 
                        FROM messages 
                        WHERE (sender_id = %(aid)s OR chat_id = %(aid)s)
                          AND chat_type = 'private'
                    """, {'aid': actor_id})
                    
                    my_tokens = [row['token'] for row in cur.fetchall()]
                    
                    if not my_tokens:
                        continue 

                    # Convertimos a lista (Postgres lo maneja mejor como Array)
                    tokens_list = list(my_tokens)

                    # --- FASE 1: INBOUND ---
                    sql_in = """
                        INSERT INTO intel_traffic_flow 
                        (actor_id, direction, remote_entity, remote_type, via_bot_token, via_bot_name, volume, last_activity)
                        SELECT 
                            %(aid)s,
                            'INBOUND',
                            m.sender_id,
                            'USER',
                            m.token,
                            b.display_name,
                            COUNT(*),
                            MAX(m.date_utc)
                        FROM messages m
                        JOIN bots b ON m.token = b.token
                        WHERE 
                            m.token = ANY(%(tokens)s)   -- <--- CORREGIDO
                            AND m.sender_id != %(aid)s
                            AND m.chat_type = 'private'
                        GROUP BY m.sender_id, m.token, b.display_name
                        HAVING COUNT(*) > 2
                    """
                    cur.execute(sql_in, {'aid': actor_id, 'tokens': tokens_list})
                    total_in += cur.rowcount
                    
                    # --- FASE 2: OUTBOUND ---
                    sql_out = """
                        INSERT INTO intel_traffic_flow 
                        (actor_id, direction, remote_entity, remote_type, via_bot_token, via_bot_name, volume, last_activity)
                        SELECT 
                            %(aid)s,
                            'OUTBOUND',
                            m.chat_id,
                            'GROUP',
                            m.token,
                            b.display_name,
                            COUNT(*),
                            MAX(m.date_utc)
                        FROM messages m
                        JOIN bots b ON m.token = b.token
                        WHERE 
                            m.token = ANY(%(tokens)s)   -- <--- CORREGIDO
                            AND m.chat_id LIKE '-%%'
                        GROUP BY m.chat_id, m.token, b.display_name
                        HAVING COUNT(*) > 1
                    """
                    cur.execute(sql_out, {'aid': actor_id, 'tokens': tokens_list})
                    total_out += cur.rowcount

                    # --- FASE 3: LATERAL ---
                    sql_lat = """
                        INSERT INTO intel_traffic_flow 
                        (actor_id, direction, remote_entity, remote_type, via_bot_token, via_bot_name, volume, last_activity)
                        SELECT 
                            %(aid)s,
                            'LATERAL',
                            src_bot.display_name,
                            'BOT',
                            dst_bot.token,
                            dst_bot.display_name,
                            COUNT(*),
                            MAX(dst_msg.date_utc)
                        FROM messages dst_msg
                        JOIN bots dst_bot ON dst_msg.token = dst_bot.token
                        JOIN social_graph_edges sge ON dst_msg.id = sge.message_pk
                        JOIN bots src_bot ON sge.identity_id::text = split_part(src_bot.token, ':', 1)
                        WHERE 
                            dst_msg.token = ANY(%(tokens)s) -- <--- CORREGIDO (Receptor es mío)
                            AND src_bot.token = ANY(%(tokens)s) -- <--- CORREGIDO (Emisor es mío)
                            AND sge.relation_type = 'FORWARD_FROM'
                            AND src_bot.token != dst_bot.token
                        GROUP BY src_bot.display_name, dst_bot.token, dst_bot.display_name
                    """
                    cur.execute(sql_lat, {'aid': actor_id, 'tokens': tokens_list})
                    total_lat += cur.rowcount
                
                conn.commit()
                if idx % 10 == 0: logging.info(f"⏳ Progreso: {idx}/{len(actors)}...")
                    
            except Exception as e:
                logging.error(f"⚠️ Error en actor {actor_id}: {e}")
                conn.rollback()

        logging.info(f"✅ Finalizado. In: {total_in} | Out: {total_out} | Lateral: {total_lat}")

    except Exception as e:
        logging.error(f"❌ Error fatal: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    aggregate_actor_traffic()