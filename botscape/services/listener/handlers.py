import os
import json
import logging
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import Optional

from telethon import events, types
from telethon.extensions import markdown
from botscape.config import settings
from botscape.services.listener.state import SEND_QUEUE, INGEST_QUEUE

# Configuración hardcodeada que deberíamos mover a config.py algún día
BLACKLIST_WORDS = []
MIN_MESSAGE_LENGTH = 0

# --- Helpers de Texto ---
def norm_text(s: Optional[str]) -> str:
    return (s or "").replace("\r\n", "\n").strip()

def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def iso_utc(dt) -> str:
    try:
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# --- Helpers de Markdown Custom ---
class CustomMarkdown:
    @staticmethod
    def parse(text):
        text, entities = markdown.parse(text)
        for i, e in enumerate(entities):
            if isinstance(e, types.MessageEntityTextUrl):
                if e.url == "quote": entities[i] = types.MessageEntityBlockquote(e.offset, e.length)
                elif e.url.startswith("emoji/"):
                    try: entities[i] = types.MessageEntityCustomEmoji(e.offset, e.length, int(e.url.split("/")[1]))
                    except: pass
        return text, entities

    @staticmethod
    def unparse(text, entities):
        # Lógica inversa simplificada para el forwarder
        return markdown.unparse(text, entities)

async def _download_media(client, message, message_id):
    """Gestiona la descarga segura de adjuntos."""
    if not message.media: return None
    
    try:
        media_id = getattr(message.media, "document", None)
        suffix = f"_{media_id.id}" if media_id and hasattr(media_id, "id") else ""
        base_name = f"msg_{message_id}{suffix}"
        file_path = os.path.join(settings.MEDIA_DIR, base_name)
        
        return await client.download_media(message.media, file_path)
    except Exception as e:
        logging.warning(f"⚠️ Fallo descargando media msg_id={message_id}: {e}")
        return None

def create_message_handler(forwarder_client, target_entity, token_label):
    """
    Fábrica de handlers. Retorna una función asíncrona que procesa cada evento NewMessage.
    """
    # Caché local de identidad del bot (para no pedir get_me() en cada mensaje)
    me_cache = {"fetched": False, "id": None, "username": None, "display": None}

    async def handler(event):
        # 1. Filtros preliminares
        raw_text = getattr(event.message, "message", "") or ""
        text = norm_text(raw_text)
        
        if BLACKLIST_WORDS and any(w.lower() in text.lower() for w in BLACKLIST_WORDS): return
        if MIN_MESSAGE_LENGTH > 0 and len(text) <= MIN_MESSAGE_LENGTH: return

        # 2. Obtener metadatos
        msg = event.message
        dt_iso = iso_utc(getattr(msg, "date", datetime.now(timezone.utc)))
        msg_id = getattr(msg, "id", None)
        chat_id = getattr(event, "chat_id", None)
        is_out = getattr(msg, "out", False)
        social_graph_payload = []

        # CLASIFICACIÓN DE CHAT
        chat_type = "unknown"
        if event.is_private:
            chat_type = "private"  # ACTOR (1-a-1)
        elif event.is_channel:     # Incluye Broadcast Channels y Megagroups
            chat_type = "channel"  # INFRAESTRUCTURA
        elif event.is_group:
            chat_type = "group"    # INFRAESTRUCTURA (Small Group)
        # ---------------------------------------------
        # Lazy load de identidad
        if not me_cache["fetched"]:
            try:
                me = await event.client.get_me()
                me_cache.update({
                    "fetched": True, "id": getattr(me, "id", None),
                    "username": getattr(me, "username", None),
                    "display": f"{getattr(me, 'first_name', '')} {getattr(me, 'last_name', '')}".strip()
                })
            except: pass

        sender_id = me_cache["id"] if is_out else getattr(await event.get_sender(), "id", None)
        my_bot_id = me_cache.get("id")
        # Analizamos si es un Forward
        if msg.fwd_from:
            fwd = msg.fwd_from
            
            # Intentamos extraer datos tanto de usuario como de canal
            s_id = getattr(fwd, "from_id", None) or getattr(fwd, "channel_id", None)
            s_name = getattr(fwd, "from_name", None) # Nombre si está oculto
            
            # Normalización de Telethon Peer objects
            final_id = None
            id_type = "UNKNOWN"
            
            if s_id:
                if isinstance(s_id, int):
                    final_id = s_id
                    id_type = "CHANNEL" if getattr(fwd, "channel_post", None) else "USER"
                elif hasattr(s_id, 'user_id'):
                    final_id = s_id.user_id
                    id_type = "USER"
                elif hasattr(s_id, 'channel_id'):
                    final_id = s_id.channel_id
                    id_type = "CHANNEL"

            # Si tenemos un ID sólido, lo preparamos para ingesta
            if final_id and final_id != my_bot_id:
                # Intentamos obtener nombre del canal/usuario si Telethon lo resolvió
                # (Esto es "best effort", a veces solo tenemos el ID)
                social_graph_payload.append({
                    "id": int(final_id),
                    "name": s_name, # A veces viene aquí
                    "type": id_type,
                    "relation": "FORWARD_FROM"
                })

        # 3. Descargar Media
        local_path = await _download_media(event.client, msg, msg_id)
        
        # Metadatos de adjunto para DB
        att_meta = []
        if local_path:
            mime = getattr(msg.media, "document", None) and getattr(msg.media.document, "mime_type", None)
            size = getattr(msg.media, "document", None) and getattr(msg.media.document, "size", None)
            att_meta.append({"mime": mime, "size": size, "sha256": None, "path": local_path})

        # 4. Reenvío al Canal (Forwarder)
        if target_entity and forwarder_client.is_connected():
            header = f"🤖 Bot: `{token_label}`\n📅 {dt_iso}\n💬 ID: `{msg_id}`"
            if sender_id: header += f"\n🆔 User: `{sender_id}`"
            body = f"\n```\n{text}\n```" if text else ""
            
            try:
                # Encolar para envío
                await SEND_QUEUE.put({
                    "text": header + body,
                    "file_path": local_path,
                    "target": target_entity,
                    "message": msg, # Referencia para re-descarga si falla
                    "download_hint": local_path
                })
            except asyncio.QueueFull:
                logging.warning("⚠️ Cola de envío llena. Descartando mensaje para el canal.")

        # 5. Ingesta en Base de Datos
        ingest_payload = {
            "token": token_label,
            "bot_id": me_cache["id"],
            "bot_username": me_cache["username"],
            "bot_display": me_cache["display"],
            "social_graph": social_graph_payload,
            "message_id": msg_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_id": sender_id,
            "date_utc": dt_iso,
            "text": text,
            "text_sha1": sha1_text(text),
            "has_media": bool(local_path),
            "media_path": None, # No guardamos path en messages, solo en attachments
            "attachments": att_meta if att_meta else None,
            "raw": {"peer": str(getattr(event, "peer_id", "")), "via_bot_id": getattr(msg, "via_bot_id", None)}
        }

        try:
            INGEST_QUEUE.put_nowait(ingest_payload)
        except asyncio.QueueFull:
            logging.error("🚨 Cola de ingesta llena. Se perderá el dato.")

    return handler