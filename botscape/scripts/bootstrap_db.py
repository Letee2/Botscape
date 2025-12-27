import os
import sys
import logging

# --- Imports de la nueva arquitectura ---
from botscape.config import settings
from botscape.shared.db.core import get_conn, exec_script

# Configurar logging para ver qué pasa dentro del contenedor
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


SCHEMA_PATH = settings.BASE_DIR / "botscape" / "shared" / "db" / "schema.sql"

def main():
    logging.info("Iniciando Bootstrap de Base de Datos...")
    
    if not os.path.exists(SCHEMA_PATH):
        logging.error(f"❌ Error: No se encontró el archivo de esquema en {SCHEMA_PATH}")
        sys.exit(1)

    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        
        logging.info(f"Conectando a PostgreSQL ({settings.DB_HOST})...")
        conn = get_conn() 
        
        logging.info("Conexión establecida. Ejecutando script de esquema...")
        exec_script(conn, schema_sql)
        
        conn.commit()
        conn.close()
        
        logging.info("✅ Esquema de base de datos creado/actualizado correctamente.")
        
    except Exception as e:
        logging.error(f"❌ Error fatal al preparar la base de datos: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()