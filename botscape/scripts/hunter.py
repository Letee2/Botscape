import os
import re
import logging
import asyncio
import aiohttp
import yara
import base64
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import Set, Dict, List, Optional, Tuple

# --- Configuración e Importaciones ---
from botscape.config import settings
from botscape.shared.db.core import get_conn

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
VT_API_KEY = settings.VT_API_KEY
YARA_RULES_PATH = "botscape/rules/telegram_hunter.yar"
MAX_CONCURRENT_TASKS = 5

# ⚙️ Estrategia de Tiempo: 
# Usamos 1 día para barridos rápidos, pero sin filtrar calidad.
SEARCH_TIMEFRAME_DAYS = 10  

VT_SEARCH_URL = "https://www.virustotal.com/api/v3/intelligence/search"
VT_DOWNLOAD_URL = "https://www.virustotal.com/api/v3/files/{id}/download"
VT_FILE_REPORT_URL = "https://www.virustotal.com/api/v3/files/{id}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Hunter")

INFRA_ALLOWLIST = {
    "api.telegram.org", "telegram.org", "windowsupdate.com", "microsoft.com",
    "live.com", "digicert.com", "identrust.com", "sectigo.com", "cloudflare.com",
    "msocsp.com", "bing.com", "google-analytics.com", "doubleclick.net",
    "googleapis.com", "azure.com", "amazonaws.com", "crashlytics.com"
}

# ==============================================================================
# 1. DECODIFICACIÓN
# ==============================================================================
class ObfuscationHandler:
    @staticmethod
    def _xor_decrypt(data: bytes, key: int) -> str:
        try:
            return bytes([b ^ key for b in data]).decode('utf-8', errors='ignore')
        except: return ""

    @staticmethod
    def deep_decode(content: bytes) -> List[Tuple[str, str]]:
        results = [] 
        try: 
            text = content.decode('utf-8', errors='ignore')
            results.append((text, "Plaintext / Raw"))
        except: pass
        
        b64_candidates = re.findall(b'[a-zA-Z0-9+/=]{20,}', content)
        for i, cand in enumerate(b64_candidates):
            try:
                cand_padded = cand + b'=' * (-len(cand) % 4)
                decoded = base64.b64decode(cand_padded).decode('utf-8', errors='ignore')
                if len(decoded) > 15: results.append((decoded, f"Base64 Block #{i}"))
            except: pass

        anchor = b"telegram"
        potential_keys = set()
        for key in range(1, 256):
            if bytes([b ^ key for b in anchor]) in content:
                potential_keys.add(key)
        
        if potential_keys:
            # logger.debug(f"   🔓 XOR Detectado. Claves: {list(potential_keys)}")
            for key in potential_keys:
                res = ObfuscationHandler._xor_decrypt(content, key)
                if res: results.append((res, f"XOR Decrypted (Key: {key})"))
        return results

# ==============================================================================
# 2. MOTOR YARA
# ==============================================================================
class YaraHunter:
    def __init__(self, rule_path: str):
        if not os.path.exists(rule_path):
            raise FileNotFoundError(f"Missing YARA rules: {rule_path}")
        try:
            self.rules = yara.compile(filepath=rule_path)
            logger.info(f"✅ Reglas YARA cargadas desde {rule_path}")
        except yara.Error as e:
            logger.error(f"❌ Error compilando YARA: {e}")
            raise

    def scan_memory(self, data: str) -> List[str]:
        try: matches = self.rules.match(data=data)
        except Exception: return []
        if not matches: return []
        

        token_regex = re.compile(r"(\d{8,10}:[a-zA-Z0-9_-]{35})")
        extracted_tokens = set(token_regex.findall(data))
        return list(extracted_tokens)

# ==============================================================================
# 3. ENRIQUECIMIENTO
# ==============================================================================
class AsyncArtifactAnalyzer:
    def __init__(self, vt_api_key: str):
        self.vt_headers = {"x-apikey": vt_api_key, "User-Agent": "Botscape-Intel/2.5_Async"}

    def _is_suspicious_url(self, url: str) -> bool:
        try:
            if not url or url.startswith("udp://"): return False
            if "://" not in url: url = f"http://{url}"
            parsed = urlparse(url)
            domain = parsed.hostname
            if not domain: return False
            domain = domain.lower()
            for safe in INFRA_ALLOWLIST:
                if domain == safe or domain.endswith("." + safe): return False
            return True
        except: return False

    async def get_vt_attributes(self, session: aiohttp.ClientSession, file_hash: str) -> Optional[Dict]:
        url = VT_FILE_REPORT_URL.format(id=file_hash)
        try:
            async with session.get(url, headers=self.vt_headers, timeout=15) as resp:
                if resp.status == 200:
                    json_data = await resp.json()
                    return json_data.get("data", {}).get("attributes", {})
        except Exception: pass
        return None

    async def _check_telegram_getme(self, session: aiohttp.ClientSession, token: str) -> Optional[Dict]:
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"): return data.get("result")
        except: pass
        return None

    async def _check_telegram_webhook(self, session: aiohttp.ClientSession, token: str) -> Optional[str]:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"): 
                        result_url = data.get("result", {}).get("url")
                        if result_url: logger.info(f"   📡 Webhook encontrado: {result_url}")
                        return result_url
        except: pass
        return None

    async def _get_vt_itw_urls(self, session: aiohttp.ClientSession, file_hash: str) -> Optional[str]:
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}/itw_urls"
        try:
            async with session.get(url, headers=self.vt_headers, timeout=15) as resp:
                if resp.status == 200:
                    json_data = await resp.json()
                    data = json_data.get("data", [])
                    if data: 
                        itw = data[0].get("attributes", {}).get("url")
                        logger.info(f"   🌍 ITW URL encontrada: {itw}")
                        return itw
        except: pass
        return None

    async def analyze(self, session: aiohttp.ClientSession, file_hash: str, token: str, known_attributes: dict = None) -> Dict:
        result = {
            "token": token, "bot_id": None, "bot_username": None,
            "is_active": False, "c2_webhook": None, "file_type": "unknown",
            "origin_url": None, "origin_source": None, "imphash": None, "ssdeep": None
        }

        # Check Telegram
        bot_info = await self._check_telegram_getme(session, token)
        if bot_info:
            result["is_active"] = True
            result["bot_id"] = bot_info.get("id")
            result["bot_username"] = bot_info.get("username")
            result["c2_webhook"] = await self._check_telegram_webhook(session, token)

        # Check VT (Si ya tenemos atributos pasados por el orchestrator, los usamos)
        if result["is_active"]:
            attrs = known_attributes
            if not attrs:
                 attrs = await self.get_vt_attributes(session, file_hash)
            
            if attrs:
                result["imphash"] = attrs.get("pe_info", {}).get("imphash") or attrs.get("imphash")
                result["ssdeep"] = attrs.get("ssdeep")
                result["file_type"] = attrs.get("type_description", "unknown").lower()
                
                # Intentar ITW primero
                itw = await self._get_vt_itw_urls(session, file_hash)
                if itw:
                    result["origin_url"] = itw
                    result["origin_source"] = "vt_itw"
                else:
                    # Sandbox C2 extraction
                    candidates = []
                    for item in attrs.get("contacted_urls", []):
                        u = item.get("url")
                        if self._is_suspicious_url(u): candidates.append(u)
                    if not candidates:
                        for item in attrs.get("contacted_ips", []):
                            ip = item.get("ip_address")
                            if ip and not ip.startswith(("127.", "10.", "192.168.")):
                                candidates.append(f"http://{ip}")
                    if candidates:
                        result["origin_url"] = candidates[0]
                        result["origin_source"] = "vt_sandbox_c2"
                        logger.info(f"   🕸️ Origen inferido (Sandbox): {candidates[0]}")
        return result

# ==============================================================================
# 4. ORQUESTADOR 
# ==============================================================================
class ThreatHunterOrchestrator:
    def __init__(self, vt_api_key: str, db_conn):
        self.vt_api_key = vt_api_key
        self.conn = db_conn
        self.yara_hunter = YaraHunter(YARA_RULES_PATH)
        self.obfuscator = ObfuscationHandler()
        self.analyzer = AsyncArtifactAnalyzer(vt_api_key)

    def _extract_tokens_from_metadata(self, attributes: dict) -> Set[str]:
        """Extrae tokens de los metadatos de VT sin descargar el archivo."""
        tokens = set()
        token_regex = re.compile(r"(\d{8,10}:[a-zA-Z0-9_-]{35})")
        
        # Fuentes de texto enriquecido en VT
        sources = [
            str(attributes.get('malware_config', '')), 
            str(attributes.get('tags', [])),
            str(attributes.get('names', [])),
            str(attributes.get('signature_info', {}))
        ]
        
        combined = " ".join(sources)
        tokens.update(token_regex.findall(combined))
        
        # Búsqueda de base64 simple en metadatos
        b64_candidates = re.findall(r"[a-zA-Z0-9+/=]{20,}", combined)
        for cand in b64_candidates:
            try:
                padded = cand + '=' * (-len(cand) % 4)
                decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
                tokens.update(token_regex.findall(decoded))
            except: pass
            
        return tokens

    async def search_vt_candidates(self, session: aiohttp.ClientSession) -> List[Dict]:
        since_date = (datetime.now() - timedelta(days=SEARCH_TIMEFRAME_DAYS)).strftime("%Y-%m-%d")
        logger.info(f"📅 Rango: {SEARCH_TIMEFRAME_DAYS} días (fs:{since_date}+)")

        
        queries = [
            
            f'malware_config:"api.telegram.org" fs:{since_date}+',
            f'type:peexe content:"api.telegram.org" fs:{since_date}+',
            f'type:elf content:"api.telegram.org" fs:{since_date}+',
            f'type:apk content:"api.telegram.org" fs:{since_date}+',
            f'(type:python OR type:powershell) content:"api.telegram.org" fs:{since_date}+',
            f'(type:html OR type:js) content:"api.telegram.org" fs:{since_date}+'
        ]

        candidates_map = {} 
        headers = {"x-apikey": self.vt_api_key}

        logger.info("🔎 Ejecutando estrategias HÍBRIDAS en VT...")
        for query in queries:
            params = {"query": query, "limit": 40} 
            try:
                async with session.get(VT_SEARCH_URL, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        current_batch = data.get('data', [])
                        logger.info(f"   ✅ Hits: {len(current_batch)} | Query: {query}")
                        
                        for item in current_batch:
                            candidates_map[item['id']] = item # Guardamos todo el objeto
                    else:
                        logger.warning(f"❌ Error API {resp.status} en query {query}")
            except Exception as e:
                logger.error(f"Error searching VT: {e}")

        # Filtro DB (Evitar reprocesar)
        final_candidates = []
        with self.conn.cursor() as cur:
            for sha, item in candidates_map.items():
                cur.execute("SELECT 1 FROM samples_intelligence WHERE sha256 = %s", (sha,))
                if not cur.fetchone():
                    final_candidates.append(item)
        
        logger.info(f"🔎 Total Muestras NUEVAS a procesar: {len(final_candidates)}")
        return final_candidates

    async def process_sample(self, session: aiohttp.ClientSession, sample_data: Dict):
        file_hash = sample_data.get('id')
        attributes = sample_data.get('attributes', {})
        found_tokens = set()
        origin_source_tag = "vt_yara_hunt"

        try:
            meta_tokens = self._extract_tokens_from_metadata(attributes)
            if meta_tokens:
                logger.info(f"⚡ METADATA HIT {file_hash[:8]} -> {len(meta_tokens)} tokens sin descarga.")
                found_tokens.update(meta_tokens)
                origin_source_tag = "vt_metadata_config"
            
            # 2. ES DESCARGA (Solo si no hay tokens en metadata)
            if not found_tokens:
                headers = {"x-apikey": self.vt_api_key}
                download_url = VT_DOWNLOAD_URL.format(id=file_hash)
                
                async with session.get(download_url, headers=headers) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        
                        # Hunting profundo (XOR/YARA)
                        decoded_layers = self.obfuscator.deep_decode(content)
                        for layer_content, layer_name in decoded_layers:
                            tokens_in_layer = self.yara_hunter.scan_memory(layer_content)
                            if tokens_in_layer:
                                found_tokens.update(tokens_in_layer)
                    elif resp.status == 429:
                        logger.warning("⛔ Cuota VT excedida durante descarga.")
                        return

            # --- CACHE NEGATIVO 1: Sin tokens ---
            if not found_tokens:
                self._mark_hash_as_processed(file_hash, "no_tokens_found")
                return

            if origin_source_tag == "vt_yara_hunt":
                logger.info(f"🔥 DEEP SCAN HIT {file_hash[:8]} -> {len(found_tokens)} Tokens")

            # 3. Persistencia
            active_count = 0
            for token in found_tokens:
                # Pasamos 'attributes' para evitar re-query a VT si ya los tenemos
                intel = await self.analyzer.analyze(session, file_hash, token, known_attributes=attributes)
                
                # Sobreescribimos source si fue metadata
                if intel["origin_source"] is None:
                    intel["origin_source"] = origin_source_tag

                if intel["is_active"]:
                    logger.info(f"🚨 BOT ACTIVO: {intel['bot_username']} (ID: {intel['bot_id']})")
                    self._save_to_db(intel, file_hash, token)
                    active_count += 1
                else:
                    logger.debug(f"   💀 Token inactivo: {token[:15]}...")
            
            # --- CACHE NEGATIVO 2: Todos muertos ---
            if active_count == 0:
                self._mark_hash_as_processed(file_hash, "all_tokens_dead")

        except Exception as e:
            logger.error(f"Error procesando {file_hash}: {e}")

    def _mark_hash_as_processed(self, file_hash, reason):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO samples_intelligence 
                    (sha256, origin_source, associated_token)
                    VALUES (%s, %s, NULL)
                    ON CONFLICT (sha256) DO NOTHING
                """, (file_hash, f"checked_{reason}"))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error saving processed hash: {e}")

    def _save_to_db(self, intel, file_hash, token):
        try:
            with self.conn.cursor() as cur:
                # Bot
                cur.execute("""
                    INSERT INTO bots (token, bot_id, is_active, c2_webhook_url, first_seen_utc, last_checked_utc)
                    VALUES (%s, %s, true, %s, NOW(), NOW())
                    ON CONFLICT (token) DO UPDATE SET 
                        is_active = true,
                        c2_webhook_url = COALESCE(EXCLUDED.c2_webhook_url, bots.c2_webhook_url),
                        last_checked_utc = NOW()
                """, (intel["token"], intel["bot_id"], intel["c2_webhook"]))

                # Sample
                cur.execute("""
                    INSERT INTO samples_intelligence 
                    (sha256, origin_source, origin_url, file_type, imphash, ssdeep, associated_token)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sha256) DO UPDATE SET
                        origin_url = EXCLUDED.origin_url,
                        associated_token = %s
                """, (
                    file_hash, 
                    intel["origin_source"], 
                    intel["origin_url"], 
                    intel["file_type"], 
                    intel["imphash"], 
                    intel["ssdeep"], 
                    token,
                    token
                ))

                # Relación
                cur.execute("""
                    INSERT INTO hash_origin (token, sample_sha256, first_seen)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (token, file_hash))
            self.conn.commit()
        except Exception as db_err:
            self.conn.rollback()
            logger.error(f"❌ Error DB: {db_err}")

    async def run(self):
        async with aiohttp.ClientSession() as session:
            # Obtenemos la LISTA DE OBJETOS (dicts), no solo hashes
            samples_data = await self.search_vt_candidates(session)
            
            tasks = []
            sem = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

            async def limited_process(s_data):
                async with sem:
                    await self.process_sample(session, s_data)

            for s in samples_data:
                tasks.append(limited_process(s))
            
            if tasks:
                await asyncio.gather(*tasks)
            else:
                logger.info("😴 Todo al día. No hay muestras nuevas.")

def main():
    logger.info("🚀 Iniciando Hunter...")
    conn = get_conn()
    try:
        orchestrator = ThreatHunterOrchestrator(VT_API_KEY, conn)
        asyncio.run(orchestrator.run())
    finally:
        conn.close()

if __name__ == "__main__":
    main()