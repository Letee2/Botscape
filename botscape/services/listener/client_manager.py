import os
import logging
import asyncio
from typing import Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors.rpcerrorlist import AccessTokenExpiredError, SessionRevokedError

from botscape.config import settings
from botscape.shared.db.core import get_conn
from botscape.services.listener.handlers import create_message_handler
from botscape.services.listener.state import state # Singleton de estado

def _get_session_path(token: str) -> str:
    bot_id = token.split(":")[0]
    bot_dir = settings.SESSIONS_DIR / bot_id
    bot_dir.mkdir(exist_ok=True)
    return str(bot_dir / "string.session")

def _load_string_session(token: str) -> StringSession:
    path = _get_session_path(token)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return StringSession(f.read().strip())
        except: pass
    return StringSession()

def _save_string_session(token: str, session_str: str):
    path = _get_session_path(token)
    with open(path, "w", encoding="utf-8") as f:
        f.write(session_str)

async def start_single_bot(token: str, forwarder_client, target_entity) -> Optional[TelegramClient]:
    """
    Crea, configura e inicia un cliente para un token.
    Maneja errores de autenticación actualizando la BBDD.
    """
    session = _load_string_session(token)
    
    client = TelegramClient(
        session,
        settings.API_ID,
        settings.API_HASH,
        flood_sleep_threshold=15,
        connection_retries=5,
        retry_delay=2
    )
    
    try:
        await client.start(bot_token=token)
        
        # Persistir sesión si cambió
        new_session = client.session.save()
        _save_string_session(token, new_session)
        
        # Configurar handlers
        handler = create_message_handler(forwarder_client, target_entity, token)
        client.add_event_handler(handler, events.NewMessage(incoming=True))
        client.add_event_handler(handler, events.NewMessage(outgoing=True))
        
        # Registrar en estado global
        state.add_client(token, client)
        return client

    except (AccessTokenExpiredError, SessionRevokedError):
        logging.warning(f"🚫 Token inválido: {token[:15]}... Marcando como inactivo.")
        _mark_bot_inactive(token)
        return None
        
    except Exception as e:
        logging.error(f"❌ Error iniciando bot {token[:15]}...: {e}")
        return None

def _mark_bot_inactive(token: str):
    """Actualiza la BBDD para no reintentar este bot."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE bots SET is_active = false, last_checked_utc = NOW() WHERE token = %s", (token,))
            conn.commit()
    except Exception as e:
        logging.error(f"Error DB marcando inactivo: {e}")

async def bot_refresher_loop(forwarder_client, target_entity):
    """
    Loop infinito que busca bots nuevos en la BBDD y los arranca.
    """
    while not state.stop_event.is_set():
        try:
            await asyncio.sleep(600) # 10 minutos
            logging.info("🔄 Refresher: Buscando bots nuevos...")
            
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT token FROM bots WHERE is_active = true")
                    db_tokens = {row['token'] for row in cur.fetchall()}
            
            active_tokens = set(state.active_clients.keys())
            new_tokens = db_tokens - active_tokens
            
            if new_tokens:
                logging.info(f"✨ Encontrados {len(new_tokens)} bots nuevos.")
                for token in new_tokens:
                    if state.stop_event.is_set(): break
                    
                    client = await start_single_bot(token, forwarder_client, target_entity)
                    if client:
                        # Añadir tarea de ejecución al loop
                        task = asyncio.create_task(client.run_until_disconnected())
                        state.tasks.append(task)
                    
                    await asyncio.sleep(1) # Rate limit de arranque
                    
        except Exception as e:
            logging.error(f"Error en Refresher: {e}")
            await asyncio.sleep(60)