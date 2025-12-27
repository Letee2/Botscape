import pandas as pd
import streamlit as st
from datetime import date

# Importamos el lector de BBDD
from botscape.shared.db.caching import read_sql

@st.cache_data(show_spinner="Cargando idiomas...", ttl=300)
def get_aggregated_languages(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Lee las estadísticas de idioma pre-agregadas de la BBDD.
    """
    # CAMBIO: Se usa %(name)s para los placeholders
    sql = """
    SELECT language, SUM(count) as count
    FROM metrics_language_daily
    WHERE date >= %(start)s AND date <= %(end)s
    GROUP BY language
    ORDER BY count DESC;
    """
    # CAMBIO: Se pasan params como un DICT
    params = {
        "start": start_date.isoformat(), 
        "end": end_date.isoformat()
    }
    # CAMBIO: Se elimina 'db_path' de la llamada
    return read_sql(sql, params=params)


@st.cache_data(show_spinner="Cargando palabras...", ttl=300)
def get_aggregated_words(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Lee las palabras (tokens) más comunes pre-agregadas.
    """
    # CAMBIO: Se usa %(name)s para los placeholders
    sql = """
    SELECT word, SUM(count) as count
    FROM metrics_word_daily
    WHERE date >= %(start)s AND date <= %(end)s
    GROUP BY word
    ORDER BY count DESC
    LIMIT 200;
    """
    # CAMBIO: Se pasan params como un DICT
    params = {
        "start": start_date.isoformat(), 
        "end": end_date.isoformat()
    }
    # CAMBIO: Se elimina 'db_path' de la llamada
    return read_sql(sql, params=params)


@st.cache_data(show_spinner=False, ttl=300)
def get_word_timeline(word: str, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Obtiene la serie temporal para UNA palabra (desde las métricas).
    """
    # CAMBIO: Se usa %(name)s para los placeholders
    sql = """
    SELECT date, SUM(count) as count
    FROM metrics_word_daily
    WHERE word = %(word)s AND date >= %(start)s AND date <= %(end)s
    GROUP BY date
    ORDER BY date ASC;
    """
    # CAMBIO: Se pasan params como un DICT
    params = {
        "word": word,
        "start": start_date.isoformat(),
        "end": end_date.isoformat()
    }
    # CAMBIO: Se elimina 'db_path' de la llamada
    df = read_sql(sql, params=params)
    
    # Renombramos 'date' a 'day' para compatibilidad con el gráfico
    df = df.rename(columns={"date": "day"})
    return df


@st.cache_data(show_spinner="Buscando bots...", ttl=60)
def get_bots_for_word(word: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    sql = """
    SELECT token, COUNT(*) as count
    FROM messages
    WHERE text LIKE %(word_like)s 
      AND date_utc >= %(start)s 
      AND date_utc < %(end)s
    GROUP BY token
    ORDER BY count DESC
    LIMIT 15;
    """
    # CAMBIO: Se pasan params como un DICT
    params = {
        "word_like": f"%{word}%",
        "start": start_iso,
        "end": end_iso
    }
    # CAMBIO: Se elimina 'db_path' de la llamada
    return read_sql(sql, params=params)