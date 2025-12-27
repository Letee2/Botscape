import logging
import pandas as pd
from botscape.shared.db.caching import read_sql
from botscape.shared.llm.provider import LocalLLMProvider

def get_community_raw_samples(tokens_list: list, bots_per_community=5, msgs_per_bot=3) -> str:
    """
    Extrae una muestra quirúrgica de texto crudo de los miembros clave de la comunidad.
    """
    if not tokens_list:
        return ""

    # Convertir lista a formato seguro para SQL
    tokens_safe = list(tokens_list[:20]) 

    sql = """
    WITH ranked_msgs AS (
        SELECT 
            token, 
            text,
            -- Priorizamos mensajes largos (logs) y recientes
            ROW_NUMBER() OVER (PARTITION BY token ORDER BY length(text) DESC, date_utc DESC) as rn
        FROM messages
        WHERE token = ANY(%(tokens)s) 
          AND text IS NOT NULL 
          AND length(text) > 15
    )
    SELECT token, text 
    FROM ranked_msgs 
    WHERE rn <= %(limit)s
    LIMIT 30;
    """
    
    try:
        # Pasamos la lista directamente, psycopg la convierte a Array de Postgres
        df = read_sql(sql, params={"tokens": tokens_safe, "limit": msgs_per_bot})
    except Exception as e:
        logging.error(f"Error fetching raw samples: {e}")
        return ""

    if df.empty:
        return ""

    # Formatear para el LLM
    context_lines = []
    context_lines.append(f"ANALYSIS SET: {len(tokens_list)} Bots in Cluster.")
    
    grouped = df.groupby('token')['text'].apply(list)
    
    for i, (token, texts) in enumerate(grouped.items()):
        if i >= bots_per_community: break
        
        context_lines.append(f"\n[BOT_MEMBER_{i+1}]")
        for txt in texts:
            clean_txt = txt.replace("\n", " ").strip()[:300]
            context_lines.append(f"- {clean_txt}")

    return "\n".join(context_lines)

def analyze_community_with_llm(tokens_list: list):
    """
    Orquestador: Obtiene datos -> Llama al LLM -> Retorna JSON.
    """
    # 1. Obtener materia prima
    raw_context = get_community_raw_samples(tokens_list)
    
    if not raw_context or len(raw_context) < 50:
        return {"error": "Datos insuficientes (mensajes vacíos o muy cortos) en esta comunidad."}

    # 2. Instanciar LLM
    llm = LocalLLMProvider()
    if not llm.is_available():
        return {"error": "Servicio LLM (Ollama) no disponible/apagado."}

    # 3. Inferencia
    result = llm.analyze_community_cohesion(raw_context)
    
    if not result:
        return {"error": "El modelo no generó una respuesta válida."}
        
    return result