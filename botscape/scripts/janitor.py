import os
import sys
import logging
import psutil
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from botscape.config import settings


# Importar la conexión de PostgreSQL
from botscape.shared.db.core import get_conn

# --- Configuración del Janitor ---

# Política estándar: Borrar datos de más de 90 días
DEFAULT_RETENTION_DAYS = 90
# Política de emergencia: Si el disco está lleno, borrar datos de más de 30 días
EMERGENCY_RETENTION_DAYS = 30
# Umbral para activar el modo emergencia
CRITICAL_DISK_PERCENT = 90.0

# Rutas
MEDIA_PATH = os.path.join(settings.BASE_DIR, "media")
# Usamos el directorio del proyecto para asegurarnos de medir el disco correcto
DISK_CHECK_PATH = settings.BASE_DIR

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Helpers ---

def get_disk_usage(path):
    """Obtiene el uso del disco del host donde reside el path."""
    try:
        # CORRECCIÓN: Convertir a string
        usage = psutil.disk_usage(str(path))
        return usage.percent
    except Exception as e:
        logging.error(f"Error al leer el disco con psutil: {e}")
        return 0.0 # Asumir 0% si falla (modo seguro)

# --- Tareas de Limpieza ---

def purge_attachments(conn, cutoff_date):
    """
    Tarea 1: Borra adjuntos físicos y sus registros en la BBDD
    que sean más antiguos que la fecha de corte.
    """
    logging.info(f"Tarea 1: Purgando adjuntos físicos anteriores a {cutoff_date.isoformat()}...")
    
    sql = """
    WITH deleted AS (
        DELETE FROM attachments a
        WHERE a.message_pk IN (
            SELECT m.id FROM messages m WHERE m.date_utc < %(cutoff)s
        )
        RETURNING a.path
    )
    SELECT path FROM deleted WHERE path IS NOT NULL;
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql, {"cutoff": cutoff_date})
            paths_to_delete = cur.fetchall()
            
            if not paths_to_delete:
                logging.info("  -> No se encontraron adjuntos antiguos para purgar.")
                return 0 # Retorna 0 borrados

            logging.info(f"  -> {len(paths_to_delete)} registros de adjuntos eliminados de la BBDD.")
            
            deleted_count = 0
            for (path,) in paths_to_delete:
                if not path.startswith(MEDIA_PATH):
                    logging.warning(f"  -> Omitiendo ruta no segura: {path}")
                    continue
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        deleted_count += 1
                except Exception as e:
                    logging.error(f"  -> No se pudo borrar el archivo {path}: {e}")
            
            logging.info(f"  -> {deleted_count} archivos físicos eliminados de /media.")
            return deleted_count

    except Exception as e:
        logging.error(f"Error fatal en Tarea 1 (purge_attachments): {e}")
        conn.rollback()
        raise e

# --- TAREA 2 (Archivar Mensajes) HA SIDO ELIMINADA ---

def vacuum_tables(conn):
    """
    Tarea 3: Ejecuta VACUUM en las tablas modificadas para
    reclamar espacio en disco.
    """
    logging.info("Tarea 3: Reclamando espacio en disco (VACUUM)...")
    
    # VACUUM no puede ejecutarse dentro de un bloque de transacción (BEGIN...COMMIT)
    # Guardamos los cambios pendientes antes de cambiar al modo autocommit.
    conn.commit()
    conn.autocommit = True
    
    try:
        with conn.cursor() as cur:
            logging.info("  -> Ejecutando VACUUM (ANALYZE) en 'attachments'...")
            cur.execute("VACUUM (ANALYZE) attachments;")
            # Aunque no modificamos 'messages', el DELETE en 'attachments'
            # afecta sus índices FK, por lo que un ANALYZE es bueno.
            logging.info("  -> Ejecutando ANALYZE en 'messages'...")
            cur.execute("ANALYZE messages;")
            logging.info("  -> VACUUM/ANALYZE completado.")
            
    except Exception as e:
        logging.error(f"Error durante la Tarea 3 (VACUUM): {e}")
    finally:
        # Volver al modo de transacción normal
        conn.autocommit = False

# --- FUNCIÓN PRINCIPAL ---

def main():
    logging.info("--- Iniciando Script Janitor ---")
    
    # 1. Comprobar uso de disco para "Modo Emergencia"
    retention_days = DEFAULT_RETENTION_DAYS
    try:
        current_percent = get_disk_usage(DISK_CHECK_PATH)
        if current_percent >= CRITICAL_DISK_PERCENT:
            logging.warning(f"¡MODO EMERGENCIA! Uso de disco ({current_percent}%) supera el umbral ({CRITICAL_DISK_PERCENT}%).")
            logging.warning(f"Se usará una retención agresiva de {EMERGENCY_RETENTION_DAYS} días.")
            retention_days = EMERGENCY_RETENTION_DAYS
        else:
            logging.info(f"Uso de disco ({current_percent}%) OK. Usando retención estándar de {retention_days} días.")
    except Exception as e:
        logging.error(f"No se pudo comprobar el uso del disco ({e}). Usando retención estándar.")

    # Calcular la fecha de corte
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    conn = None
    try:
        conn = get_conn()
        
        # 2. Ejecutar Tareas de Limpieza
        archived_count = purge_attachments(conn, cutoff_date)
        # (Llamada a archive_messages() eliminada)
        
        # 3. Comitear las transacciones
        conn.commit()
        
        # 4. Reclamar espacio (solo si borramos algo)
        if archived_count > 0:
            vacuum_tables(conn)
        else:
            logging.info("Tarea 3: Omitiendo VACUUM (no se borró nada).")

    except Exception as e:
        logging.error(f"Error fatal durante la ejecución del Janitor: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("Conexión a BBDD cerrada.")
    
    logging.info("--- Janitor finalizado ---")

if __name__ == "__main__":
    # Asegúrate de tener estas librerías instaladas en la RPi:
    # pip install psutil psycopg
    main()