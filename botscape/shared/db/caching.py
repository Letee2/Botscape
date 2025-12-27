import pandas as pd
from typing import List, Dict, Any
import streamlit as st
import logging

# Importamos la función de conexión de psycopg
from .core import get_conn

@st.cache_data(show_spinner=False, ttl=30)
def read_sql(sql: str, params: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Función centralizada para leer SQL en un DataFrame de Pandas.
    Ejecuta la consulta manualmente con psycopg para evitar
    problemas de 'pd.read_sql_query' con los parámetros.
    """
    if params is None:
        params = {}
        
    try:
        # Usamos un 'context manager' para la conexión
        with get_conn() as con:
            
            # Usar un cursor para ejecutar la consulta con params
            with con.cursor() as cur:
                cur.execute(sql, params)
                
                # Si no hay resultados (ej. un UPDATE/INSERT), 
                # o el cursor no tiene descripción, devolver un DF vacío.
                if cur.description is None:
                    return pd.DataFrame()
                    
                # Obtener resultados. Como 'conn' usa 'dict_row',
                # 'results' será una lista de diccionarios.
                results = cur.fetchall()
                
                # Obtener nombres de columnas desde la descripción del cursor
                # (esto funciona incluso si 'results' está vacío)
                columns = [desc[0] for desc in cur.description]
                
                # Crear DataFrame desde la lista de dicts (results)
                df = pd.DataFrame(results, columns=columns)
        return df
        
    except Exception as e:
        # Damos más contexto en el error
        logging.error(f"Error SQL (manual exec): {e}\nQuery: {sql}\nParams: {params}")
        st.error(f"❌ Error SQL: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def list_tokens() -> List[str]:
    """Carga la lista de tokens."""
    # Esta consulta no tiene parámetros
    sql = "SELECT token FROM bots ORDER BY last_seen DESC NULLS LAST"
    try:
        with get_conn() as con:
            # fetchall() con dict_row devuelve una lista de dicts
            rows = con.execute(sql).fetchall()
            # Devolvemos una lista de strings
            return [r['token'] for r in rows]
            
    except Exception as e:
        logging.error(f"Error al listar tokens: {e}")
        st.error(f"Error al listar tokens: {e}")
        return []