# botscape/services/ingest_tools.py
import re
import requests
import logging
import os
from botscape.config import settings
from botscape.shared.db.core import get_conn

# Regex canónica de Token
REGEX_BOT_TOKEN = re.compile(r"\d{8,10}:[0-9A-Za-z_-]{35}")

def extract_and_inject_from_hash(file_hash: str) -> dict:
    """
    Descarga una muestra de VT, busca tokens y los inyecta en la BBDD.
    Retorna un reporte de lo sucedido.
    """
    report = {"status": "error", "msg": "", "tokens_found": []}
    
    if not settings.VT_API_KEY:
        report["msg"] = "Falta la API Key de VirusTotal en .env"
        return report

    try:
        # 1. Descargar de VT
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}/download"
        headers = {"x-apikey": settings.VT_API_KEY}
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            report["msg"] = f"Error VT: {response.status_code} (¿Hash válido? ¿Tienes permiso?)"
            return report
            
        # 2. Extraer Tokens del binario
        content = response.content.decode("latin-1", errors="ignore")
        tokens = set(REGEX_BOT_TOKEN.findall(content))
        
        if not tokens:
            report["status"] = "warning"
            report["msg"] = "No se encontraron tokens en el archivo."
            return report
            
        # 3. Inyectar en BBDD
        new_count = 0
        with get_conn() as conn:
            with conn.cursor() as cur:
                for token in tokens:
                    try:
                        bot_id = int(token.split(":")[0])
                        # Insertamos o Reactivamos
                        cur.execute("""
                            INSERT INTO bots (token, bot_id, is_active, first_seen_utc, last_checked_utc)
                            VALUES (%s, %s, true, NOW(), NOW())
                            ON CONFLICT (token) DO UPDATE SET
                                is_active = true,
                                last_checked_utc = NOW()
                            RETURNING (xmax = 0) AS is_insert;
                        """, (token, bot_id))
                        
                        res = cur.fetchone()
                        if res and res['is_insert']:
                            new_count += 1
                            
                        # Trazabilidad (Hash <-> Token)
                        cur.execute("""
                            INSERT INTO hash_origin (token, sample_sha256, first_seen)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT DO NOTHING;
                        """, (token, file_hash))
                        
                    except Exception as e:
                        logging.error(f"Error inyectando token {token}: {e}")
            conn.commit()
            
        report["status"] = "success"
        report["tokens_found"] = list(tokens)
        report["msg"] = f"Procesado. {len(tokens)} tokens encontrados ({new_count} nuevos)."
        return report

    except Exception as e:
        report["msg"] = f"Excepción crítica: {e}"
        return report

def inject_manual_token(token: str) -> dict:
    """Inyecta un token manual directamente."""
    if not REGEX_BOT_TOKEN.match(token):
        return {"status": "error", "msg": "Formato de token inválido."}
        
    try:
        bot_id = int(token.split(":")[0])
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bots (token, bot_id, is_active, first_seen_utc, last_checked_utc)
                    VALUES (%s, %s, true, NOW(), NOW())
                    ON CONFLICT (token) DO UPDATE SET is_active = true, last_checked_utc = NOW();
                """, (token, bot_id))
            conn.commit()
        return {"status": "success", "msg": f"Bot {token[:15]}... añadido/reactivado."}
    except Exception as e:
        return {"status": "error", "msg": f"Error BBDD: {e}"}