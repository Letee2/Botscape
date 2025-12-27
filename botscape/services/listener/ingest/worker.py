# --- IMPORTS ACTUALIZADOS ---
import asyncio
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from botscape.shared.utils.templating import generate_structure_signature

# Importar desde el paquete compartido
from botscape.shared.db.ingest import (
    upsert_bot, insert_message, insert_entities_batch,
    insert_attachments_batch, MessageRecord, AttachmentRecord,
    upsert_social_identity, insert_social_edge
)
# Importar el parser desde shared
from botscape.shared.parsers.entities import extract_entities

def iso_utc(dt) -> str:
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
    except Exception:
        return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def sha1_text(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8", errors="ignore")).hexdigest()

async def ingest_worker(db_conn, queue: asyncio.Queue):
    """
    Worker asíncrono que procesa eventos de mensajes y los persiste en PostgreSQL.
    Implementa 'Hybrid Template Tagging': Agrupa mensajes por estructura, no por contenido exacto.
    """
    while True:
        item: Dict[str, Any] = await queue.get()
        try:
            # 1. Upsert del Bot (Información básica)
            upsert_bot(
                db_conn,
                token=item["token"],
                bot_id=item.get("bot_id"),
                username=item.get("bot_username"),
                display_name=item.get("bot_display")
            )

            # 2. Procesamiento del Mensaje y Generación de Plantilla
            original_text = item.get("text") or ""
            
            # --- CAMBIO CLAVE: Generar firma estructural ---
            # Generamos la firma (ej: "Login: <EMAIL> Pass: <NUM>")
            structure_text = generate_structure_signature(original_text)
            
            # Calculamos el hash de esa firma. Este será el ID de la plantilla.
            # Todos los mensajes con la misma estructura compartirán este hash.
            structural_hash = sha1_text(structure_text)
            # -----------------------------------------------

            mrec = MessageRecord(
                token=item["token"],
                message_id=item.get("message_id"),
                chat_id=str(item.get("chat_id")) if item.get("chat_id") is not None else None,
                chat_type=item.get("chat_type"),
                sender_id=str(item.get("sender_id")) if item.get("sender_id") is not None else None,
                date_utc=item["date_utc"],
                text=original_text,          # Guardamos el texto ORIGINAL para lectura humana y regex
                text_sha1=structural_hash,   # Guardamos el hash ESTRUCTURAL para agrupación automática
                has_media=bool(item.get("has_media", False)),
                media_path=item.get("media_path"),
                raw_json=json.dumps(item.get("raw"), ensure_ascii=False)[:1_000_000] if item.get("raw") else None,
            )
            
            # Insertamos el mensaje
            msg_pk = insert_message(db_conn, mrec)
            # --- [NUEVO] PROCESAR SOCIAL GRAPH ---
            social_data = item.get("social_graph", [])
            for node in social_data:
                try:
                    op_id = node.get("id")
                    op_type = node.get("type")
                    op_name = node.get("name") # Puede ser None
                    relation = node.get("relation")
                    
                    if op_id:
                        # 1. Guardar Identidad (Nodo)
                        upsert_social_identity(db_conn, op_id, None, op_name, op_type)
                        
                        # 2. Guardar Relación (Arista)
                        insert_social_edge(db_conn, item["token"], op_id, relation, msg_pk)
                        
                        logging.info(f"🕸️ [SOCIAL] Bot {item['token'][:8]} linked to {op_type} {op_id}")
                except Exception as ex_social:
                    logging.error(f"Error procesando nodo social: {ex_social}")

            # 3. Extracción de Entidades (Signal Extraction)
            # Usamos el parser mejorado (con validación Luhn, etc.) sobre el texto ORIGINAL
            ents = extract_entities(original_text)
            if ents:
                insert_entities_batch(db_conn, msg_pk, ents)

            # 4. Procesamiento de Adjuntos
            att_list = []
            for a in (item.get("attachments") or []):
                att_list.append(AttachmentRecord(
                    mime=a.get("mime"),
                    size=a.get("size"),
                    sha256=a.get("sha256"),
                    path=a.get("path")
                ))
            if att_list:
                insert_attachments_batch(db_conn, msg_pk, att_list)

            db_conn.commit()
            
        except Exception as e:
            logging.error(f"[INGEST] Error procesando item: {e}")
            try: 
                db_conn.rollback()
            except Exception: 
                pass
        finally:
            queue.task_done()