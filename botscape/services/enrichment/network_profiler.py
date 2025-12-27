import socket
import logging
import requests
from urllib.parse import urlparse
from botscape.shared.db.core import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [NET] %(message)s")

def resolve_and_enrich(url):
    """
    Resuelve DNS y obtiene GeoIP para una URL dada.
    Filtra dominios legítimos de Telegram para evitar ruido.
    """
    if not url or "telegram.org" in url: return None
    
    try:
        # 1. Limpieza y Extracción de Host
        if "://" not in url: url = "http://" + url
        parsed = urlparse(url)
        host = parsed.hostname
        
        if not host: return None
        
        # 2. Resolución DNS
        try:
            ip = socket.gethostbyname(host)
        except:
            return None # Dominio no resuelve (posiblemente caído)
            
        # 3. Enriquecimiento GeoIP (ip-api.com)
        # Nota: En entorno productivo, considerar cachear respuestas o usar DB local (MaxMind)
        geo = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode,city,isp,query", timeout=5).json()
        
        if geo.get('status') == 'success':
            return {
                "indicator": host,
                "ip": geo['query'],
                "country": geo['countryCode'],
                "city": geo['city'],
                "asn": geo['isp']
            }
    except Exception as e:
        logging.error(f"Error analizando {url}: {e}")
    return None

def run_network_profiling():
    """
    Escanea la flota de bots vinculada a Actores (Chats Privados) en busca de 
    infraestructura externa (Webhooks C2 y Orígenes de Malware).
    """
    conn = get_conn()
    try:

        sql = """
            SELECT 
                m.chat_id as sender_id, -- El Actor (Dueño del Chat Privado)
                b.token, 
                b.c2_webhook_url, 
                s.origin_url
            FROM messages m
            JOIN bots b ON m.token = b.token
            -- Unimos con inteligencia de samples si existe (Opcional)
            LEFT JOIN samples_intelligence s ON b.token = s.associated_token
            WHERE m.chat_id NOT LIKE '-%' -- CLAVE: IDs que no empiezan por '-' son Actores Privados
              AND (b.c2_webhook_url IS NOT NULL OR s.origin_url IS NOT NULL)
            GROUP BY m.chat_id, b.token, b.c2_webhook_url, s.origin_url
        """
        
        with conn.cursor() as cur:
            cur.execute(sql)
            targets = cur.fetchall()
            
        logging.info(f"🔎 Iniciando barrido de infraestructura sobre {len(targets)} activos detectados...")
        
        hits = 0
        for row in targets:
            # Recopilar URLs candidatas (Webhook del Bot o Origen del Malware)
            urls_to_check = [u for u in [row['c2_webhook_url'], row['origin_url']] if u]
            
            for url in urls_to_check:
                intel = resolve_and_enrich(url)
                
                if intel:
                    hits += 1
                    # A. Persistir la Inteligencia de Infraestructura
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO infrastructure_intelligence (indicator, type, ip_address, country_code, city, asn)
                            VALUES (%s, 'HOST', %s, %s, %s, %s)
                            ON CONFLICT (indicator) DO UPDATE SET last_seen = NOW()
                            RETURNING id;
                        """, (intel['indicator'], intel['ip'], intel['country'], intel['city'], intel['asn']))
                        
                        infra_id = cur.fetchone()['id']
                        
                        # B. Vincular al Actor (Atribución)
                        # Aquí asumimos inserción directa para vincular la IP al Actor/Bot.
                        cur.execute("""
                            INSERT INTO operator_infrastructure (sender_id, infra_id, bot_token)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """, (row['sender_id'], infra_id, row['token']))
                        
                    logging.info(f"📍 [HIT] {intel['country']} | {intel['asn']} -> Actor: {row['sender_id']}")
                    
        conn.commit()
        logging.info(f"✅ Perfilado de red completado. {hits} nuevos puntos de infraestructura catalogados.")
        
    except Exception as e:
        logging.error(f"❌ Error crítico en network_profiler: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_network_profiling()