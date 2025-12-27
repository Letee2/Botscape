import logging
import requests
import re
from urllib.parse import urlparse
from typing import Dict, Optional, List

# Imports del proyecto
from botscape.config import settings

logger = logging.getLogger(__name__)

INFRA_ALLOWLIST = {
    "api.telegram.org",       # Ya lo rastreamos como 'Token', no queremos duplicarlo como 'Network Infra'
    "telegram.org",
    "windowsupdate.com",      # Ruido Windows
    "microsoft.com",          # Ruido Windows (generalmente)
    "live.com",               # Ruido Windows
    "digicert.com",           # Verificación SSL
    "identrust.com",          # Verificación SSL
    "sectigo.com",            # Verificación SSL
    "cloudflare.com",         # CDN genérico (cuidado, a veces usado como proxy, pero ruidoso)
    "msocsp.com",             # Verificación Certificados Microsoft
    "bing.com",               # Connectivity Check
    "google-analytics.com",   # Tracking irrelevante
    "doubleclick.net"         # Ads
}

class ArtifactAnalyzer:
    """
    Analiza un artefacto (Hash + Token) utilizando inteligencia extendida de VT.
    Capacidades:
    1. Extracción de C2 Webhook (Telegram API).
    2. Extracción de Origen ITW (In-The-Wild).
    3. Análisis de Tráfico de Sandbox (Network C2) para encontrar paneles ocultos.
    """

    def __init__(self, vt_api_key: str):
        self.vt_api_key = vt_api_key
        self.vt_headers = {
            "x-apikey": vt_api_key,
            "User-Agent": "Botscape-Intel/2.0"
        }

    def _is_suspicious_url(self, url: str) -> bool:
        """
        Filtra URLs legítimas de sistema operativo o infraestructura conocida (Telegram).
        Deja pasar AWS, Azure, IPs directas, etc.
        """
        try:
            if not url or url.startswith("udp://"): return False
            
            # Limpieza básica
            if "://" not in url: 
                url = f"http://{url}"
            
            parsed = urlparse(url)
            domain = parsed.hostname
            
            if not domain: return False
            
            # Normalización
            domain = domain.lower()
            
            # 1. Check Allowlist (Coincidencia parcial segura)
            for safe in INFRA_ALLOWLIST:
                # Si el dominio es exactamente el safe o un subdominio (ej: ocsp.digicert.com)
                if domain == safe or domain.endswith("." + safe): 
                    return False
            
            return True
        except:
            return False

    def _check_telegram_webhook(self, token: str) -> Optional[str]:
        """Consulta la API de Telegram para ver si hay un Webhook C2 configurado."""
        try:
            url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", {}).get("url")
        except Exception as e:
            logger.warning(f"Error consultando Webhook para {token[:10]}: {e}")
        return None

    def _get_vt_report(self, file_hash: str) -> Dict:
        """Obtiene el reporte completo de atributos del archivo en VT."""
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}"
        try:
            resp = requests.get(url, headers=self.vt_headers, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("attributes", {})
        except Exception as e:
            logger.error(f"Error VT API (File Report): {e}")
        return {}

    def _get_vt_itw_urls(self, file_hash: str) -> Optional[str]:
        """Consulta las URLs 'In The Wild' (ITW) explícitas."""
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}/itw_urls"
        try:
            resp = requests.get(url, headers=self.vt_headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    # Retornamos la primera URL encontrada
                    return data[0].get("attributes", {}).get("url")
        except Exception as e:
            logger.error(f"Error VT API (ITW): {e}")
        return None

    def analyze(self, file_hash: str, token: str) -> Dict:
        """
        Ejecuta el flujo de decisión completo.
        Retorna un diccionario enriquecido con la mejor inteligencia posible.
        """
        result = {
            "file_type": "unknown",
            "c2_webhook": None,
            "origin_url": None,
            "origin_source": None, # 'vt_itw' o 'vt_sandbox_c2'
            "network_c2_candidates": [], # Lista completa para uso futuro
            "imphash": None,
            "ssdeep": None,
            "is_phishing_candidate": False
        }

        # 1. Análisis Forense de Telegram (C2 Backend Directo)
        result["c2_webhook"] = self._check_telegram_webhook(token)
        if result["c2_webhook"]:
            logger.info(f"🚨 [C2 DETECTADO] Webhook: {result['c2_webhook']}")

        # 2. Consulta a VirusTotal (File Object)
        attrs = self._get_vt_report(file_hash)
        if not attrs:
            return result

        # --- Extracción de Metadatos ---
        result["imphash"] = attrs.get("pe_info", {}).get("imphash") or attrs.get("imphash")
        result["ssdeep"] = attrs.get("ssdeep")
        
        type_desc = attrs.get("type_description", "").lower()
        result["file_type"] = type_desc
        
        # Marcador de Phishing (útil para priorización)
        if "html" in type_desc or "pdf" in type_desc or "script" in type_desc:
            result["is_phishing_candidate"] = True

        # --- 3. Búsqueda de Infraestructura (Deep Origin Discovery) ---
        
        # A. Intentar obtener ITW (Origen de descarga/infección real)
        itw_url = self._get_vt_itw_urls(file_hash)
        if itw_url:
            result["origin_url"] = itw_url
            result["origin_source"] = "vt_itw"
            logger.info(f"   -> 🎯 [ORIGEN ITW] {itw_url}")

        # B. Análisis de Sandbox (Tráfico de red saliente)
        # Si no hay ITW, o para enriquecer, miramos a dónde se conecta.
        candidates = set()
        
        # URLs contactadas
        for item in attrs.get("contacted_urls", []):
            u = item.get("url")
            if self._is_suspicious_url(u):
                candidates.add(u)

        # IPs contactadas
        for item in attrs.get("contacted_ips", []):
            ip = item.get("ip_address")
            # Ignorar IPs locales
            if ip and not (ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168.")):
                candidates.add(f"http://{ip}") # Normalizar como URL

        result["network_c2_candidates"] = list(candidates)

        # --- Lógica de Fallback---
        # Si no tenemos un origen ITW, usamos el primer C2 de red detectado como "Origen"
        # Esto permite perfilar la infraestructura aunque no sepamos de dónde se descargó el malware.
        if not result["origin_url"] and candidates:
            # Priorizamos dominios sobre IPs puras si es posible
            sorted_candidates = sorted(list(candidates), key=lambda x: 1 if re.match(r"http://\d+\.\d+", x) else 0)
            
            best_candidate = sorted_candidates[0]
            result["origin_url"] = best_candidate
            result["origin_source"] = "vt_sandbox_c2"
            logger.info(f"   -> ⚡ [ORIGEN INFERIDO] Sandbox C2: {best_candidate}")

        return result