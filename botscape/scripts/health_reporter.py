import os
import sys
import logging
import psutil  
import pathlib
from dotenv import load_dotenv

# --- Configuración de Path ---
from botscape.config import settings

# Importar la conexión de PostgreSQL
from botscape.shared.db.core import get_conn

# --- Configuración ---
# Cargar variables (.env) para DB_HOST=localhost, etc.


# Definir la ruta de la carpeta de media
MEDIA_PATH = os.path.join(settings.BASE_DIR, "media")
# Usamos el directorio del proyecto para asegurarnos de medir el disco correcto
DISK_CHECK_PATH = settings.BASE_DIR 

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def bytes_to_gb(bytes_val):
    """Convierte bytes a GB y redondea."""
    if not bytes_val:
        return 0.0
    return round(bytes_val / (1024**3), 2)

def get_disk_usage(path):
    """Obtiene el uso del disco del host donde reside el path."""
    try:
        # CORRECCIÓN: Convertir el objeto Path a string con str()
        usage = psutil.disk_usage(str(path))
        return {
            "total_gb": bytes_to_gb(usage.total),
            "used_gb": bytes_to_gb(usage.used),
            "free_gb": bytes_to_gb(usage.free),
            "percent": usage.percent
        }
    except Exception as e:
        logging.error(f"Error al leer el disco con psutil: {e}")
        return None

def get_dir_size_gb(path_str: str) -> float:
    """Calcula el tamaño de un directorio en GB."""
    try:
        root = pathlib.Path(path_str)
        if not root.exists():
            logging.warning(f"Directorio no encontrado: {path_str}")
            return 0.0
        
        total_size = sum(f.stat().st_size for f in root.rglob('*') if f.is_file())
        return bytes_to_gb(total_size)
    except Exception as e:
        logging.error(f"Error al calcular el tamaño de {path_str}: {e}")
        return 0.0

def main():
    logging.info("--- Iniciando Health Reporter ---")
    
    # 1. Recolectar métricas del host
    logging.info(f"Calculando uso de disco para: {DISK_CHECK_PATH}")
    disk_info = get_disk_usage(DISK_CHECK_PATH)
    
    logging.info(f"Calculando tamaño de carpeta: {MEDIA_PATH}")
    media_size_gb = get_dir_size_gb(MEDIA_PATH)

    if not disk_info:
        logging.error("No se pudo obtener información del disco. Abortando.")
        return

    # 2. Preparar los datos para la BBDD
    # (metric_name, value_numeric)
    metrics_to_update = [
        ('disk_total_gb', disk_info['total_gb']),
        ('disk_used_gb', disk_info['used_gb']),
        ('disk_free_gb', disk_info['free_gb']),
        ('disk_percent_used', disk_info['percent']),
        ('media_folder_gb', media_size_gb)
    ]

    # 3. Actualizar la BBDD
    conn = None
    try:
        conn = get_conn() # Se conecta a localhost (según .env)
        with conn.cursor() as cur:
            # Usamos ON CONFLICT... DO UPDATE para actualizar los valores
            sql_upsert = """
                INSERT INTO system_health (metric_name, value_numeric, last_updated)
                VALUES (%s, %s, NOW())
                ON CONFLICT (metric_name) DO UPDATE SET
                    value_numeric = excluded.value_numeric,
                    last_updated = excluded.last_updated;
            """
            cur.executemany(sql_upsert, metrics_to_update)
        
        conn.commit()
        logging.info("Métricas de salud actualizadas en la BBDD.")
        
    except Exception as e:
        logging.error(f"Error al actualizar la BBDD: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            
    logging.info("--- Health Reporter finalizado ---")

if __name__ == "__main__":
    # Recordatorio: Instalar psutil en la RPi
    # pip install psutil psycopg
    main()