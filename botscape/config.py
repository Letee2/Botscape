# Archivo: botscape/config.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# 1. Definir Rutas Base
# BASE_DIR es la carpeta raíz del proyecto (donde está docker-compose.yml)
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'

# 2. Cargar variables de entorno
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logging.warning(f"⚠️  [Config] No se encontró .env en {BASE_DIR}")

class Config:
    """Configuración Global del Sistema (Singleton)."""
    
    # --- Rutas ---
    BASE_DIR = BASE_DIR
    MEDIA_DIR = BASE_DIR / "media"
    SESSIONS_DIR = BASE_DIR / "sessions"
    BACKUPS_DIR = BASE_DIR / "backups"
    LOG_DIR = BASE_DIR / "logs"
    # Asegurar que existan
    MEDIA_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    BACKUPS_DIR.mkdir(exist_ok=True)

    # --- Base de Datos ---
    # Lógica inteligente: Si DB_HOST no está definido, asumimos 'localhost'
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "botscape_db")
    DB_USER = os.getenv("DB_USER", "botscape_user")
    DB_PASS = os.getenv("DB_PASS", "")

    # --- Telegram ---
    # Convertimos a los tipos correctos para evitar errores de Telethon
    try:
        API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
    except ValueError:
        API_ID = 0
        
    API_HASH = os.getenv("TELEGRAM_API_HASH")
    FORWARDER_TOKEN = os.getenv("FORWARDER_BOT_TOKEN")
    
    # TARGET_CHANNEL puede ser entero (ID) o string (Username)
    _target = os.getenv("TARGET_CHANNEL", "")
    try:
        TARGET_CHANNEL = int(_target)
    except ValueError:
        TARGET_CHANNEL = _target

    # --- APIs Externas ---
    VT_API_KEY = os.getenv("VT_API_KEY")

    FORBIDDEN_COUNTRY = os.getenv("FORBIDDEN_COUNTRY", "ES")

    @property
    def DB_DSN(self):
        """Data Source Name para psycopg (Connection String)."""
        return f"host={self.DB_HOST} port={self.DB_PORT} dbname={self.DB_NAME} user={self.DB_USER} password={self.DB_PASS}"

# Instancia Singleton exportada
settings = Config()