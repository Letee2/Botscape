import logging
from botscape.shared.db.queries import profiling

def build_bot_context(token: str) -> str:
    """
    Agrega toda la inteligencia disponible sobre un bot y genera 
    el Prompt de Contexto para el LLM.
    """
    # 1. Obtener Datos 
    fingerprint = profiling.get_bot_fingerprint(token)
    templates = profiling.get_top_templates(token)
    entities = profiling.get_entity_summary(token)
    generic_kvs = profiling.get_generic_kv_samples(token)
    
    # AHORA raw_samples trae 'extensions'
    raw_samples = profiling.get_diverse_raw_samples(token)

    if not fingerprint or fingerprint['total_msgs'] == 0:
        return None

    # 2. Construir el Informe
    report = []
    report.append(f"ANALYSIS TARGET: Bot Token {token[:10]}...")
    
    # Sección A: Actividad (Igual)
    report.append("\n[ACTIVITY METRICS]")
    report.append(f"- Total Messages Captured: {fingerprint['total_msgs']}")
    report.append(f"- Active Period: {fingerprint['first_seen']} to {fingerprint['last_seen']}")
    report.append(f"- Unique Chats/Victims: {fingerprint['unique_chats']}")
    report.append(f"- Media/Files Sent: {fingerprint['media_count']}")

    # --- MEJORA OPTIMIZADA: Muestras con Extensiones ---
    if raw_samples:
        report.append("\n[ACTUAL MESSAGE SAMPLES (EVIDENCE)]")
        report.append("Here are exact copies of messages sent by this bot (with attachment extensions):")
        for i, item in enumerate(raw_samples):
            msg_content = item['text'].replace("\n", " ").strip()
            exts_content = item['extensions']
            
            line = f"Sample {i+1}: "
            if msg_content:
                line += f"Text=\"{msg_content[:500]}\" "
            
            if exts_content:
                # Etiqueta compacta: [EXT: .jpg, .txt]
                line += f"[EXT: {exts_content}]"
            
            if not msg_content and not exts_content:
                line += "(Empty Message)"
                
            report.append(line)

    # Sección B: Patrones Estructurales
    if templates:
        report.append("\n[DOMINANT MESSAGE PATTERNS]")
        report.append("The bot repeats these structural templates (normalized):")
        for t in templates:
            # Truncamos templates muy largos para no saturar la ventana de contexto
            report.append(f"- {t[:300]}")

    # Sección C: Datos Extraídos (Objetivos del atacante)
    if entities:
        report.append("\n[EXTRACTED DATA TYPES]")
        report.append("The bot is actively harvesting these entities:")
        for k, v in entities.items():
            report.append(f"- {k}: {v} occurrences")

    # Sección D: Anomalías Genéricas (Pistas para atribución)
    if generic_kvs:
        report.append("\n[UNKNOWN KEY-VALUE PATTERNS]")
        report.append("These technical fields appear in logs but are unclassified:")
        # Unimos las muestras, el LLM es bueno detectando patrones en listas sucias
        report.append(", ".join(generic_kvs[:20]))

    # Footer
    report.append("\n[INSTRUCTION]")
    report.append("Based on the evidence above, classify this bot's purpose and malware family.")
    
    return "\n".join(report)