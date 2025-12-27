import logging
from botscape.shared.db.core import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [OPS] %(message)s")

def run_profiler():
    logging.info("🕵️‍♂️ Iniciando Perfilado de Actores...")
    
    conn = get_conn()
    try:
        # 1. CONSULTA UNIFICADA (V4 Logic)
        # Extraemos métricas basadas en el CHAT_ID (La identidad real en privado),
        # no solo en quien envía el mensaje.
        sql = """
            SELECT 
                m.chat_id as actor_id,
                COUNT(DISTINCT m.token) as bot_count,
                MIN(m.date_utc) as first_seen,
                MAX(m.date_utc) as last_seen,
                
                -- Heurística Commander: ¿El dueño del chat ha escrito comandos?
                COUNT(*) FILTER (
                    WHERE m.sender_id = m.chat_id 
                      AND (m.text LIKE '/%%' OR m.text LIKE '!%%' OR m.text LIKE '.%%')
                ) as cmd_count
            FROM messages m
            WHERE m.chat_id NOT LIKE '-%%' -- Solo chats privados (IDs positivos)
              AND m.chat_id IS NOT NULL
            GROUP BY m.chat_id
        """
        
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            
        logging.info(f"Analizando {len(rows)} identidades operativas...")
        
        updates = []
        for r in rows:
            actor_id = r['actor_id']
            bot_count = r['bot_count']
            cmd_count = r['cmd_count']
            
            # 2. CLASIFICACIÓN DE ROL
            if cmd_count > 0:
                role = "COMMANDER"     # Control Activo
                confidence = 1.0
            else:
                role = "COLLECTOR"     # Buzón Pasivo (Data Drop)
                confidence = 0.8       # Alta probabilidad si es chat privado recibiendo datos
            
            # Solo guardamos si tiene al menos 1 bot asociado
            if bot_count >= 1:
                updates.append((actor_id, role, confidence, bot_count, r['first_seen'], r['last_seen']))
            
        # 3. UPSERT MASIVO (Inserción segura)
        # Esto garantiza que el ID exista para que otras tablas (network_profiler) puedan referenciarlo.
        if updates:
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO operator_profiles 
                    (sender_id, role, confidence, bots_controlled, first_seen, last_seen, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (sender_id) DO UPDATE SET
                        role = EXCLUDED.role,
                        confidence = EXCLUDED.confidence,
                        bots_controlled = EXCLUDED.bots_controlled,
                        last_seen = EXCLUDED.last_seen,
                        updated_at = NOW();
                """, updates)
                
            conn.commit()
            logging.info(f"✅ {len(updates)} perfiles de actor sincronizados exitosamente.")
        else:
            logging.info("No se encontraron nuevos actores para perfilar.")

    except Exception as e:
        logging.error(f"❌ Error en profiler: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_profiler()