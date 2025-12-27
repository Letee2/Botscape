# Archivo: botscape/config.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Detectar raíz del proyecto (un nivel arriba de este archivo 'botscape/')
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'

# Cargar .env
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logging.warning(f"⚠️ No se encontró archivo .env en {BASE_DIR}")

class Config:
    """Configuración centralizada para Listener, Dashboard y Scripts."""
    
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "botscape_db")
    DB_USER = os.getenv("DB_USER", "botscape_user")
    DB_PASS = os.getenv("DB_PASS", "")

    # --- Telegram Credentials ---
    API_ID = os.getenv("TELEGRAM_API_ID")
    API_HASH = os.getenv("TELEGRAM_API_HASH")
    FORWARDER_TOKEN = os.getenv("FORWARDER_BOT_TOKEN")
    TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

    # --- External APIs ---
    VT_API_KEY = os.getenv("VT_API_KEY")

    # --- Paths ---
    # Usamos rutas absolutas basadas en BASE_DIR para evitar errores al ejecutar desde distintas carpetas
    MEDIA_DIR = BASE_DIR / "media"
    SESSIONS_DIR = BASE_DIR / "sessions"
    LOG_DIR = BASE_DIR / "logs"

    # Asegurar directorios
    MEDIA_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    @property
    def DATABASE_URI(self):
        """DSN para psycopg."""
        return f"host={self.DB_HOST} port={self.DB_PORT} dbname={self.DB_NAME} user={self.DB_USER} password={self.DB_PASS}"

# Instancia singleton
settings = Config()