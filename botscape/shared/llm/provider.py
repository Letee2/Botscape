import os
import json
import logging
import requests
from typing import Dict, Any, Optional

# Configuración dinámica
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "llama3.1" 

class LocalLLMProvider:
    """
    Cliente agnóstico para interactuar con Ollama (Local o Remoto).
    Garantiza que los datos viajen solo a la IP designada.
    """
    
    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.1):
        self.base_url = OLLAMA_URL
        self.model = model
        self.temperature = temperature
        self.api_generate = f"{self.base_url}/api/generate"
        
        # Validación de conexión al iniciar (Warn only)
        if not self.is_available():
            logging.warning(f"⚠️  [LLM] No se detecta Ollama en {self.base_url}. El perfilado fallará si no se levanta.")

    def is_available(self) -> bool:
        """Ping simple para verificar si el nodo de inferencia está vivo."""
        try:
            res = requests.get(f"{self.base_url}/", timeout=2)
            return res.status_code == 200
        except Exception:
            return False

    def analyze_bot_context(self, context_text: str) -> Optional[Dict[str, Any]]:
        # Prompt de Sistema REFINADO
        system_prompt = (
        "You are a strict, evidence-based Threat Intelligence Analyst analyzing raw Telegram Bot logs."
        "\n\nCORE ANALYSIS DIRECTIVES:"
        "\n1. ANALYSIS LOGIC: Analyze context, content patterns, and file structures to determine intent. Presence of file extensions attached to messages can help in the assessment."
        "\n2. ATTRIBUTION RULES: Do not guess malware family names (e.g., do not tag 'RedLine') unless a specific config signature is explicitly present. Use descriptive behavioral tags instead."
        "\n3. FACTUALITY: If logs are insufficient, classify as 'Unknown'. Do not invent data."
        "\n\nCLASSIFICATION FRAMEWORK:"
        "\n- INFOSTEALER: Unauthorized extraction of browser data, session tokens, system fingerprints, or credentials."
        "\n- DRAINER/CRYPTO: Targeting digital assets, wallets, seed phrases, or smart contracts."
        "\n- C2/BACKDOOR: Remote command execution, shell access, persistence, or payloads."
        "\n- BENIGN/LEGIT: Coherent human conversations, safe media, or standard admin operations."
        "\n\nTAGGING INSTRUCTIONS:"
        "\n- Generate tags based STRICTLY on observed data."
        "\n- Quantity: Use as many or as few as necessary (1 or more). Do not add filler tags."
        "\n- Content: Focus on Target Identity (if found), Data Type, Locale, or specific Attack Vectors."
        "\n\nRESPONSE FORMAT (JSON ONLY):"
        "{"
        '  "risk_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",'
        '  "actor_intent": "Infostealer" | "Drainer" | "C2/Backdoor" | "Benign/Legit" | "Unknown",'
        '  "summary": "Technical summary in Spanish. Objective and concise.",'
        '    "detected_ttps": ["Credential Access", "Exfiltration", "User Execution", "Benign Activity", ...]'
        '  "tags": ["Tag1", ...]' 
        "}"
        )

        payload = {
            "model": self.model,
            "prompt": context_text,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_ctx": 4096
            }
        }

        try:
            logging.info(f"🧠 [LLM] Enviando query a {self.base_url}...")
            response = requests.post(self.api_generate, json=payload, timeout=180)
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get("response", "")
            
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                logging.error(f"❌ [LLM] Respuesta no es JSON válido: {response_text[:100]}")
                return None

        except Exception as e:
            logging.error(f"❌ [LLM] Error de inferencia: {e}")
            return None

    def analyze_community_cohesion(self, community_logs: str) -> Optional[Dict[str, Any]]:
        system_prompt = (
            "You are a Senior Threat Hunter analyzing a cluster of Telegram Bots suspected to be part of the same campaign."
            "\n\nYOUR TASK:"
            "\nIdentify the 'Common Denominator' linking these disjointed log samples. "
            "Ignore variable data (like random IPs or usernames). Focus on structural similarities, specific malware phrases, or shared languages."
            "\n\nINPUT FORMAT:"
            "\nYou will receive raw logs labeled by Bot ID. Example: [Bot 123]: 'Log text...'"
            "\n\nOUTPUT FORMAT (JSON ONLY):"
            "{"
            '  "cohesion_score": 0-100 (How similar are they?),'
            '  "shared_pattern": "Brief description of the similarity (e.g., \'All use RedLine Stealer logs\').",'
            '  "hypothesis": "Why are they clustered? (e.g., \'Same Malware Builder\', \'Same Phishing Kit\', \'Same Operator\').",'
            '  "keywords": ["keyword1", "keyword2"]'
            "}"
        )

        payload = {
            "model": self.model,
            "prompt": community_logs,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_ctx": 4096}
        }

        try:
            logging.info(f"🧠 [LLM] Analizando cohesión de comunidad...")
            response = requests.post(self.api_generate, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            return json.loads(result.get("response", ""))
        except Exception as e:
            logging.error(f"❌ [LLM] Error en análisis de comunidad: {e}")
            return None

    def generate(self, prompt: str, system: str = None) -> Optional[str]:
        """Envía un prompt genérico y devuelve texto plano."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": 4096
            }
        }
        if system:
            payload["system"] = system

        try:
            print(f"🔵 [DEBUG] Enviando prompt a {self.api_generate} (Modelo: {self.model})...")
            response = requests.post(self.api_generate, json=payload, timeout=120)
            
            # Verificamos si falló el HTTP (404, 500, etc)
            if response.status_code != 200:
                print(f"🔴 [ERROR] Ollama respondió con código {response.status_code}: {response.text}")
                return None
                
            json_response = response.json()
            actual_text = json_response.get("response", "")
            
            if not actual_text:
                print("🟠 [WARN] Ollama respondió 200 OK pero el campo 'response' estaba vacío.")
            else:
                print(f"🟢 [SUCCESS] Respuesta recibida ({len(actual_text)} caracteres).")
                
            return actual_text

        except requests.exceptions.ConnectTimeout:
            print("🔴 [ERROR] Timeout: Ollama tardó más de 120s en responder.")
            return None
        except requests.exceptions.ConnectionError:
            print(f"🔴 [ERROR] No se puede conectar a {self.base_url}. ¿Está Ollama corriendo?")
            return None
        except Exception as e:
            print(f"🔴 [ERROR CRÍTICO] Excepción en generate: {e}")
            return None

# --- WRAPPER FUERA DE LA CLASE ---
def query_llm(prompt: str) -> str:
    """Helper externo con debug."""
    try:
        provider = LocalLLMProvider()
        response = provider.generate(prompt)
        return response if response else ""
    except Exception as e:
        print(f"🔴 [ERROR] Fallo al instanciar provider: {e}")
        return ""