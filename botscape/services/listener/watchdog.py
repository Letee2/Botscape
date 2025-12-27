import os
import sys
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# --- Configuración ---
from botscape.config import settings
PROJECT_DIR = settings.BASE_DIR

# Umbral: Si no hay mensajes en este tiempo, reiniciar.
MAX_SILENCE_MINUTES = 30 

# Rutas críticas
SESSIONS_PATH = os.path.join(PROJECT_DIR, 'sessions')
COMPOSE_FILE = os.path.join(PROJECT_DIR, 'docker-compose.yml')
LOG_FILE = os.path.join(PROJECT_DIR, 'watchdog.log')

# Cargar el .env para obtener las credenciales de la BBDD
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

# Configurar logging para este script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- Importar el conector de BBDD ---
# Debe estar instalado en el host, no solo en Docker.
# Ejecuta: pip install psycopg2-binary
try:
    import psycopg2
except ImportError:
    logging.error("Error: 'psycopg2' no está instalado.")
    logging.error("Por favor, ejecútalo en el servidor: pip install psycopg2-binary")
    sys.exit(1)


def trigger_fix():
    """
    Ejecuta la secuencia de reinicio:
    1. Para el listener.
    2. Borra las sesiones de los bots.
    3. Vuelve a iniciar el listener.
    """
    logging.warning("Iniciando secuencia de reinicio automático...")
    
    try:
        # --- Paso 1: Parar el listener ---
        logging.info("Paso 1: Parando el contenedor 'botscape_listener'...")
        # Usamos 'stop' en lugar de 'down' para no parar la BBDD
        subprocess.run(
            ["docker-compose", "-f", COMPOSE_FILE, "stop", "listener"],
            check=True, capture_output=True, text=True
        )

        # --- Paso 2: Borrar sesiones inválidas ---
        logging.info("Paso 2: Borrando sesiones de bots monitorizados...")
        # IMPORTANTE: Este comando asume que docker/sudo no pide contraseña.
        # Es mejor ejecutar este script como un usuario que pueda gestionar docker.
        rm_command = f"rm -rf {SESSIONS_PATH}/*/"
        subprocess.run(
            rm_command, shell=True, check=True, capture_output=True, text=True
        )
        logging.info("Sesiones de bots eliminadas.")

        # --- Paso 3: Reiniciar el listener ---
        logging.info("Paso 3: Iniciando 'botscape_listener'...")
        subprocess.run(
            ["docker-compose", "-f", COMPOSE_FILE, "up", "-d", "listener"],
            check=True, capture_output=True, text=True
        )
        
        logging.info("✅ Reinicio completado. El listener debería re-autenticarse.")

    except subprocess.CalledProcessError as e:
        logging.error(f"Fallo al ejecutar el comando de reinicio: {e.stderr}")
    except Exception as e:
        logging.error(f"Error inesperado durante el reinicio: {e}")


def check_health():
    """
    Comprueba la BBDD para ver cuándo llegó el último mensaje.
    """
    conn = None
    try:
        # CONEXIÓN: Nos conectamos a 'localhost' porque el script corre en el HOST,
        # no en la red de Docker. El puerto 5432 está expuesto.
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            host='localhost', # <-- ¡Importante!
            port=os.getenv('DB_PORT', 5432)
        )
        
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date_utc) FROM messages;")
            last_message_time = cur.fetchone()[0]

        if last_message_time is None:
            logging.warning("No hay mensajes en la BBDD. Asumiendo que es nuevo. Saliendo.")
            return

        # Comprobar la diferencia de tiempo
        now_utc = datetime.now(timezone.utc)
        delta = now_utc - last_message_time
        
        if delta > timedelta(minutes=MAX_SILENCE_MINUTES):
            logging.warning(
                f"¡Alerta! El último mensaje llegó hace {delta.total_seconds() / 60:.0f} minutos."
            )
            trigger_fix()
        else:
            logging.info(
                f"Sistema OK. Último mensaje hace {delta.total_seconds() / 60:.0f} minutos."
            )

    except psycopg2.OperationalError as e:
        logging.error(f"Error al conectar a la BBDD en localhost: {e}")
    except Exception as e:
        logging.error(f"Error inesperado al comprobar la salud: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logging.info("--- Iniciando comprobación del Watchdog ---")
    check_health()
    logging.info("--- Fin de la comprobación del Watchdog ---")