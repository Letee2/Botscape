import os
import psycopg
import logging
from typing import Iterator, Sequence, Any
from dotenv import load_dotenv
from botscape.config import settings

# Configurar logging básico para DB
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_conn() -> psycopg.Connection:
    """Establece conexión a PostgreSQL."""
    try:
        conn = psycopg.connect(settings.DB_DSN, row_factory=psycopg.rows.dict_row)
        return conn
    except psycopg.OperationalError as e:
        logging.error(f"Error al conectar a PostgreSQL en {settings.DB_HOST}: {e}")
        raise

def execute_sql(sql: str, params: dict = None) -> bool:
    """
    Ejecuta un comando SQL de escritura (INSERT/UPDATE/DELETE) y comitea.
    Retorna True si fue exitoso.
    """
    if params is None: params = {}
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ Error en execute_sql: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def exec_script(conn: psycopg.Connection, schema_sql: str) -> None:
    conn.execute(schema_sql)

def execute(conn: psycopg.Connection, sql: str, params: Sequence[Any] = ()) -> None:
    conn.execute(sql, params)

def executemany(conn: psycopg.Connection, sql: str, rows: Sequence[Sequence[Any]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(sql, rows)