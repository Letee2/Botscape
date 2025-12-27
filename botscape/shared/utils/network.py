import requests
import logging
import time
from botscape.config import settings

# Servicios de IP que devuelven metadatos (país)
# Usamos ipapi.co y ip-api.com que son fiables para geolocalización básica
IP_PROVIDERS = [
    "https://ipapi.co/json/",
    "http://ip-api.com/json", 
    "https://ipinfo.io/json"
]

def get_public_ip_info():
    """
    Consulta la IP pública y geolocalización con reintentos.
    Retorna dict con keys normalizadas: 'ip', 'country', 'org'.
    """
    for url in IP_PROVIDERS:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                
                # Normalización de campos según el proveedor
                ip = data.get("ip") or data.get("query")
                
                # Intentamos obtener el código de país (ej: 'ES', 'US')
                country = data.get("country") or data.get("countryCode")
                
                org = data.get("org") or data.get("isp") or data.get("as")
                
                if ip and country:
                    return {
                        "ip": ip,
                        "country": country.upper(), # Siempre mayúsculas (ES, US)
                        "org": org
                    }
        except Exception as e:
            logging.warning(f"Fallo consultando geo-IP en {url}: {e}")
            continue
    return None

def validate_anonymity() -> bool:
    """
    OpSec Check: Verifica si estamos operando desde un país seguro.
    """
    logging.info("🕵️  Verificando ubicación y seguridad de red...")
    
    info = get_public_ip_info()
    
    if not info:
        logging.error("❌ No se pudo determinar la ubicación (IP/País). Abortando por seguridad.")
        # En OpSec estricto, si no sabes dónde estás, no operas.
        return False

    current_ip = info["ip"]
    current_country = info["country"]
    current_org = info.get("org", "Unknown")

    logging.info(f"🌍 Ubicación Detectada: {current_country} (IP: {current_ip}) - ISP: {current_org}")

    # --- KILL SWITCH POR PAÍS ---
    forbidden_country = settings.FORBIDDEN_COUNTRY
    
    if forbidden_country and current_country == forbidden_country.upper():
        logging.critical("="*60)
        logging.critical(f"🚨 ¡ALERTA DE OPSEC! ESTÁS EN UN PAÍS PROHIBIDO ({current_country}).")
        logging.critical(f"   La configuración prohíbe operar desde: {forbidden_country}.")
        logging.critical("   -> Conéctate a una VPN (fuera de este país) para continuar.")
        logging.critical("="*60)
        return False

    logging.info("✅ Ubicación segura confirmada. Iniciando operaciones.")
    return True