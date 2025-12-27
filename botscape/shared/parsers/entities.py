from typing import List
import re
from botscape.shared.db.ingest import EntityRecord

# ==============================================================================
# 1. DEFINICIÓN DE PATRONES (REGEX) - ALTA PRECISIÓN
# ==============================================================================

# --- A. Infraestructura y Red ---
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b")
# URLs: Ignoramos las muy cortas o locales para reducir ruido
URL_RE   = re.compile(r"https?://(?:[\w-]+\.)+[\w-]+(?:/[^\s\"'<>]*)?")
IPV4_RE  = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b")
CHATID_RE = re.compile(r"(?:chat[_\-]?id|chatid)\D{0,5}(-?\d{5,15})", re.I)

# --- B. Cripto-Activos (Financial Threat) ---
# BTC: Legacy (1...), P2SH (3...), SegWit (bc1...)
BTC_RE     = re.compile(r"\b(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}\b")
ETH_RE     = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
TRON_RE    = re.compile(r"\bT[a-zA-HJ-NP-Z0-9]{33}\b")
SOLANA_RE  = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
LITECOIN_RE = re.compile(r"\b[LM3][a-km-zA-HJ-NP-Z1-9]{26,33}\b")

# --- C. Tokens de Servicios y Cloud (High Value Targets) ---
# AWS Access Key ID (AKIA, ASIA, etc.)
AWS_KEY_RE = re.compile(r"\b(AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")
# Discord Token (Estructura aproximada: ID.Time.Hmac)
DISCORD_RE = re.compile(r"\b[M-Z][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}\b")
# Telegram Bot Token (para detectar si el bot comparte credenciales de otros bots)
TELEGRAM_TOKEN_RE = re.compile(r"\b\d{8,10}:[a-zA-Z0-9_-]{35}\b")
# Google API Key (Empieza por AIza)
GOOGLE_API_RE = re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b")

# --- D. Artefactos de Stealers (Evidence Markers) ---
# La presencia de estos archivos confirma infección por InfoStealer
STEALER_FILES_RE = re.compile(
    r"(?i)\b(wallet\.dat|passwords\.txt|cookies\.txt|login.*\.json|Local State|key3\.db|key4\.db|autofill\.json)\b"
)

# ==============================================================================
# 2. PATRONES CONTEXTUALES (HEURÍSTICA ESTRUCTURAL)
# ==============================================================================

# --- E. Credenciales y Datos Personales ---
# Captura: "Password: ...", "Pass = ...", "Login: ..."
# Soporta inicio de línea (^) O separadores comunes (|)
CREDENTIAL_KV_RE = re.compile(
    r"(?im)(?:^|[|•-])\s*\b(password|pass|pwd|contraseña|clave|login|user|usuario|email)\b\s*[:=]\s*([^\s|]+)"
)

# Tarjetas de Crédito (Formatos: xxxx-xxxx... o xxxxxxxx...)
CC_KV_RE = re.compile(
    r"(?i)\b(cc|card|number|tarjeta|numero)\b\D{0,10}(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4})"
)

# Info de Host (Fingerprinting)
# Captura: "OS: Windows 11", "IP: 1.1.1.1", "CPU: Intel..."
HOST_KV_RE = re.compile(
    r"(?im)(?:^|[|•-])\s*\b(host|computer|pc|system|os|ip|cpu|ram|hwid)\b\s*[:=]\s*([^|\n\r]{2,100})"
)

# --- F. Extracción Genérica "Catch-All" (La clave de la robustez) ---
# Intenta capturar CUALQUIER patrón "Clave: Valor" que parezca técnico.
# Reglas estrictas para la Clave para evitar falsos positivos en texto natural.
# - La clave no puede tener espacios (o muy pocos).
# - Debe estar seguida de : o =.
# - Soporta delimitadores de una línea (| :: •).
GENERIC_KV_RE = re.compile(
    r"(?im)(?:^|[|•]|\s{2,})\s*([a-zA-Z0-9\.\-_]{2,25})\s*[:=]\s*(?!http)([^|\n\r]{1,200})"
)

# ==============================================================================
# 3. FUNCIONES DE VALIDACIÓN
# ==============================================================================

def is_luhn_valid(cc_number: str) -> bool:
    """Valida checksum de tarjetas de crédito para eliminar números aleatorios."""
    digits = [int(d) for d in re.sub(r'\D', '', cc_number)]
    if len(digits) < 13 or len(digits) > 19: return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled if doubled < 9 else doubled - 9
        else:
            checksum += d
    return (checksum % 10) == 0

def is_noise_key(key: str) -> bool:
    """Filtra claves genéricas que suelen ser ruido en lenguaje natural."""
    k = key.lower().strip()
    # Palabras comunes que pueden ir seguidas de dos puntos en una frase normal
    noise = {"note", "nota", "warning", "error", "example", "ejemplo", "http", "https", "mailto", "tel"}
    return k in noise

def clean_value(val: str) -> str:
    """Limpia espacios y caracteres de control."""
    return val.strip()

# ==============================================================================
# 4. MOTOR PRINCIPAL
# ==============================================================================

def extract_entities(text: str) -> List[EntityRecord]:
    if not text: return []

    entities: List[EntityRecord] = []
    # Usamos una lista de rangos (start, end) para evitar solapamientos
    # Si una entidad específica (ej: AWS Key) ya reclamó un trozo de texto, 
    # el parser genérico no debe volver a extraerlo.
    claimed_spans = []

    def is_claimed(start, end):
        for c_start, c_end in claimed_spans:
            # Si hay solapamiento significativo
            if max(start, c_start) < min(end, c_end):
                return True
        return False

    def get_snippet(match_obj) -> str:
        s_idx, e_idx = match_obj.span()
        # Contexto: 40 chars atrás, 40 adelante
        ctx_start = max(0, s_idx - 40)
        ctx_end = min(len(text), e_idx + 40)
        return text[ctx_start:ctx_end].replace("\n", " ").strip()

    def add_entity(etype: str, val: str, match_obj, confidence: float = 1.0):
        val_clean = clean_value(val)
        if not val_clean or len(val_clean) > 300: return # Safety check
        
        start, end = match_obj.span()
        if is_claimed(start, end): return
        
        claimed_spans.append((start, end))
        entities.append(EntityRecord(
            etype=etype,
            value=val_clean,
            context_snippet=get_snippet(match_obj),
            confidence=confidence
        ))

    # --- FASE 1: Entidades de Alta Confianza (Formato único) ---
    # Ejecutamos esto primero porque su formato es inequívoco.
    
    for m in AWS_KEY_RE.finditer(text): add_entity("aws_key", m.group(0), m, 1.0)
    for m in DISCORD_RE.finditer(text): add_entity("discord_token", m.group(0), m, 1.0)
    for m in TELEGRAM_TOKEN_RE.finditer(text): add_entity("bot_token", m.group(0), m, 1.0)
    for m in GOOGLE_API_RE.finditer(text): add_entity("google_api_key", m.group(0), m, 1.0)

    for m in BTC_RE.finditer(text): add_entity("crypto_wallet", f"BTC: {m.group(0)}", m, 0.98)
    for m in ETH_RE.finditer(text): add_entity("crypto_wallet", f"ETH: {m.group(0)}", m, 0.98)
    for m in TRON_RE.finditer(text): add_entity("crypto_wallet", f"TRX: {m.group(0)}", m, 0.98)
    for m in SOLANA_RE.finditer(text): add_entity("crypto_wallet", f"SOL: {m.group(0)}", m, 0.95)

    for m in EMAIL_RE.finditer(text): add_entity("email", m.group(0).lower(), m, 0.95)
    for m in IPV4_RE.finditer(text):  add_entity("ip", m.group(0), m, 0.90)
    for m in URL_RE.finditer(text):   add_entity("url", m.group(0), m, 0.85)
    
    for m in STEALER_FILES_RE.finditer(text): add_entity("stealer_evidence", m.group(0), m, 1.0)

    # --- FASE 2: Entidades Contextuales (Semánticas) ---
    
    for m in CREDENTIAL_KV_RE.finditer(text):
        key, val = m.groups()
        if len(val) < 2: continue
        # Normalizamos el tipo
        tipo = "password"
        if any(u in key.lower() for u in ["user", "login", "email"]):
            tipo = "username"
        add_entity(tipo, val, m, 0.85)

    for m in HOST_KV_RE.finditer(text):
        add_entity("victim_metadata", f"{m.group(1)}: {m.group(2)}", m, 0.75)

    for m in CC_KV_RE.finditer(text):
        clean_cc = re.sub(r'\D', '', m.group(2))
        if is_luhn_valid(clean_cc):
            add_entity("credit_card", clean_cc, m, 1.0)

    # --- FASE 3: Generic Catch-All (Red de seguridad) ---
    # Capturamos todo lo que tenga estructura "Key: Value" y no haya sido procesado.
    # Esto alimenta al LLM con datos que no sabíamos que existían.
    
    for m in GENERIC_KV_RE.finditer(text):
        key = m.group(1).strip()
        val = m.group(2).strip()
        
        if is_noise_key(key): continue
        if len(key) < 2 or len(val) < 2: continue
        
        # Si el valor parece una URL o Email que ya capturamos en Fase 1, lo ignoramos
        if "http" in val or "@" in val: continue 
        
        # Guardamos como par completo para que el LLM entienda el contexto
        # Ej: etype="generic_kv", value="BuildID: 554"
        add_entity("generic_kv", f"{key}: {val}", m, 0.5)

    return entities