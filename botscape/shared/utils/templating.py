import re

# core/templating.py

REPLACEMENTS = [
    # --- NUEVO: Normalización de Credenciales ---
    # Captura "Pass: xxxx" o "Login: yyyy" y oculta el valor.
    # Esto es vital para agrupar logs que solo difieren en la contraseña.
    (re.compile(r'(?i)\b(password|pass|pwd|contraseña|clave|login|user|username|email)\s*[:=]\s*\S+'), r'\1: <SECRET>'),

    # 1. Hashes y Tokens
    (re.compile(r'\b[a-fA-F0-9]{32,64}\b'), '<HASH>'),
    # ... (resto de la lista original igual: BOT_TOKEN, IP, URL, DATE, etc.)
    (re.compile(r'\d{8,10}:[a-zA-Z0-9_-]{35}'), '<BOT_TOKEN>'),
    (re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b'), '<IP>'),
    (re.compile(r'https?://[^\s]+'), '<URL>'),
    (re.compile(r'\b[\w\.-]+@[\w\.-]+\.\w+\b'), '<EMAIL>'),
    (re.compile(r'\d{4}-\d{2}-\d{2}'), '<DATE>'),
    (re.compile(r'\d{2}/\d{2}/\d{4}'), '<DATE>'),
    (re.compile(r'\d{2}:\d{2}:\d{2}'), '<TIME>'),
    (re.compile(r'[A-Za-z]:\\[^\n\t]+'), '<WIN_PATH>'), 
    (re.compile(r'(?:/[^/\n\s]+)+'), '<LINUX_PATH>'),
    (re.compile(r'\b\d+\b'), '<NUM>'),
    (re.compile(r'={3,}'), '==='),
    (re.compile(r'-{3,}'), '---'),
    (re.compile(r'_{3,}'), '___'),
]

def generate_structure_signature(text: str) -> str:
    if not text:
        return ""
    
    processed_text = text[:8192] 
    
    for pattern, replacement in REPLACEMENTS:
        processed_text = pattern.sub(replacement, processed_text)
    
    processed_text = "\n".join([line.strip() for line in processed_text.splitlines() if line.strip()])
    
    return processed_text