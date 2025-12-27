import os
import sys
import requests
import logging
import time

# Cargar configuración de entorno si es necesario (o confiar en las vars inyectadas por Docker)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = "llama3.1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

def pull_model():
    logging.info(f"📡 Conectando con nodo de inferencia: {OLLAMA_HOST}")
    
    # 1. Verificar conectividad
    try:
        requests.get(OLLAMA_HOST, timeout=5)
        logging.info("✅ Nodo Ollama online.")
    except requests.ConnectionError:
        logging.error(f"❌ No se puede conectar a {OLLAMA_HOST}.")
        logging.error("   -> Si es remoto, verifica VPN/Firewall y que Ollama escuche en 0.0.0.0")
        sys.exit(1)

    # 2. Verificar si el modelo ya existe
    try:
        res = requests.get(f"{OLLAMA_HOST}/api/tags")
        models = [m['name'] for m in res.json()['models']]
        if any(MODEL_NAME in m for m in models):
            logging.info(f"✅ Modelo '{MODEL_NAME}' ya está cargado en el nodo.")
            return
    except Exception as e:
        logging.warning(f"⚠️ No se pudieron listar modelos: {e}")

    # 3. Descargar (Pull)
    logging.info(f"⬇️  Iniciando descarga de '{MODEL_NAME}' en el nodo remoto/local...")
    logging.info("   (Esto puede tardar dependiendo del ancho de banda del nodo Ollama)")
    
    try:
        # stream=True para evitar timeout de lectura, aunque no imprimimos el stream
        res = requests.post(f"{OLLAMA_HOST}/api/pull", json={"name": MODEL_NAME}, stream=True)
        
        # Consumir el stream para esperar a que termine
        for _ in res.iter_lines():
            pass 
            
        if res.status_code == 200:
            logging.info(f"✅ Modelo '{MODEL_NAME}' descargado y listo para inferencia.")
        else:
            logging.error(f"❌ Error en pull: {res.status_code} - {res.text}")
            
    except Exception as e:
        logging.error(f"❌ Error crítico descargando modelo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    pull_model()