import sys
import logging
import time
import json

from botscape.config import settings
from botscape.shared.llm.provider import LocalLLMProvider
from botscape.services.profiler.context import build_bot_context
from botscape.shared.db.queries import profiling as queries
from botscape.shared.db.actions import save_bot_profile

# Configuración
BATCH_SIZE = 10
MODEL_NAME = "llama3.1"

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - [PROFILER] %(message)s"
)

def analyze_single_bot(token: str, llm_provider: LocalLLMProvider = None) -> dict:
    """
    Función atómica para analizar un bot. 
    Retorna el resultado (dict) si éxito, None si falla.
    """
    # Si no nos pasan un proveedor (ej: desde script batch), instanciamos uno
    if not llm_provider:
        llm_provider = LocalLLMProvider(model=MODEL_NAME)
        if not llm_provider.is_available():
            logging.error("❌ LLM no disponible.")
            return None

    logging.info(f"   -> Analizando {token[:15]}...")
    
    # 1. Construir Contexto
    context_text = build_bot_context(token)
    if not context_text:
        logging.warning(f"      ⚠️ Datos insuficientes para {token[:10]}.")
        return None
        
    # 2. Inferencia LLM
    analysis = llm_provider.analyze_bot_context(context_text)
    
    if not analysis:
        logging.warning("      ❌ Fallo en inferencia LLM.")
        return None
        
    # 3. Guardar Resultados
    if save_bot_profile(token, analysis, MODEL_NAME):
        logging.info(f"      ✅ Perfil guardado. Riesgo: {analysis.get('risk_level')}")
        return analysis
    else:
        logging.error("      ❌ Error guardando en BBDD.")
        return None

def main():
    logging.info("🕵️‍♂️ Iniciando Ciclo de Perfilado Automático...")
    
    llm = LocalLLMProvider(model=MODEL_NAME)
    if not llm.is_available():
        logging.error("❌ El servicio LLM (Ollama) no responde. Abortando.")
        sys.exit(1)
        
    candidates = queries.get_candidates_for_profiling(limit=BATCH_SIZE)
    
    if not candidates:
        logging.info("💤 No hay bots pendientes de análisis.")
        return

    logging.info(f"🎯 Se analizarán {len(candidates)} bots.")
    
    for token in candidates:
        try:
            analyze_single_bot(token, llm)
        except Exception as e:
            logging.error(f"Excepción en loop: {e}")

if __name__ == "__main__":
    main()