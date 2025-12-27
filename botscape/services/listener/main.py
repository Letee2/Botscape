import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession


from botscape.config import settings
from botscape.shared.db.core import get_conn
from botscape.services.listener.state import state, SEND_QUEUE, INGEST_QUEUE
from botscape.services.listener.client_manager import start_single_bot, bot_refresher_loop
from botscape.services.listener.ingest.worker import ingest_worker
from botscape.shared.utils.network import validate_anonymity

from botscape.shared.utils.sender import ForwarderSender
from botscape.services.listener.handlers import CustomMarkdown

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ------------------------------------------------------------------------------
# WORKER PUENTE (Bridge)
# ------------------------------------------------------------------------------
async def bridge_to_sender(sender_instance: ForwarderSender):
    """
    Mueve mensajes de la cola global (SEND_QUEUE) al ForwarderSender
    """
    while not state.stop_event.is_set():
        try:
            # Esperamos un trabajo de la cola global (generado por handlers.py)
            job = await asyncio.wait_for(SEND_QUEUE.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
            
        try:
            # Delegamos el envío (maneja FloodWait y retries)
            await sender_instance.send(
                entity=job["target"],
                text=job["text"],
                file=job.get("file_path")
            )
            # Nota: ForwarderSender gestiona su propia cola interna y ritmo.
        except Exception as e:
            logging.error(f"Error en el puente de envío: {e}")
        finally:
            SEND_QUEUE.task_done()

# ------------------------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------------------------
async def main():
    # 1. OpSec Check (Kill Switch)
    print("\n" + "="*60)
    if not validate_anonymity():
        logging.critical("💀 Shutdown forzado por fallo de OpSec.")
        return
    print("="*60 + "\n")

    logging.info("🚀 Iniciando Botscape Listener (Modular v2)...")
    
    # 2. Configurar DB
    try:
        db_conn = get_conn()
        logging.info("✅ Base de datos conectada.")
    except Exception as e:
        logging.critical(f"❌ Fallo fatal DB: {e}")
        return

    # 3. Arrancar Worker de Ingesta (Base de Datos)
    ingest_task = asyncio.create_task(ingest_worker(db_conn, INGEST_QUEUE))
    state.tasks.append(ingest_task)

    # 4. Iniciar Forwarder (Cliente Maestro)
    fwd_session_path = settings.SESSIONS_DIR / "forwarder.session"
    fwd_session_str = ""
    if fwd_session_path.exists():
        fwd_session_str = fwd_session_path.read_text(encoding="utf-8")
        
    forwarder_client = TelegramClient(
        StringSession(fwd_session_str),
        settings.API_ID,
        settings.API_HASH
    )
    
    try:
        await forwarder_client.start(bot_token=settings.FORWARDER_TOKEN)
        forwarder_client.parse_mode = CustomMarkdown()
        if forwarder_client.session.save() != fwd_session_str:
            fwd_session_path.write_text(forwarder_client.session.save(), encoding="utf-8")
            
        target_entity = await forwarder_client.get_entity(settings.TARGET_CHANNEL)
        logging.info(f"📢 Forwarder conectado. Destino: {settings.TARGET_CHANNEL}")
        
        # --- AQUÍ ESTÁ LA MEJORA: Usamos la clase ForwarderSender ---
        # Instanciamos el sender robusto
        sender_robust = ForwarderSender(forwarder_client, rate_per_sec=1.5)
        await sender_robust.start() # Arranca su loop interno
        
        # Arrancamos el puente que alimenta al sender desde la cola global
        bridge_task = asyncio.create_task(bridge_to_sender(sender_robust))
        state.tasks.append(bridge_task)
        # ------------------------------------------------------------
        
    except Exception as e:
        logging.critical(f"❌ Fallo Forwarder: {e}")
        return

    # 5. Cargar Bots Iniciales desde BD
    logging.info("📋 Cargando bots activos...")
    with db_conn.cursor() as cur:
        cur.execute("SELECT token FROM bots WHERE is_active = true")
        tokens = [row['token'] for row in cur.fetchall()]

    if not tokens:
        logging.warning("⚠️  No hay bots activos. Esperando al Refresher.")

    # 6. Arrancar Clientes Monitores
    for token in tokens:
        client = await start_single_bot(token, forwarder_client, target_entity)
        if client:
            t = asyncio.create_task(client.run_until_disconnected())
            state.tasks.append(t)
        await asyncio.sleep(0.5) 

    # 7. Arrancar Refresher
    refresher_t = asyncio.create_task(bot_refresher_loop(forwarder_client, target_entity))
    state.tasks.append(refresher_t)

    # 8. Loop Principal
    logging.info("✅ Sistema operando. Ctrl+C para salir.")
    try:
        await asyncio.gather(*state.tasks)
    except asyncio.CancelledError: pass
    except KeyboardInterrupt:
        logging.info("🛑 Interrupción de usuario.")
    finally:
        # Parada ordenada
        if 'sender_robust' in locals():
            await sender_robust.stop()
        await state.shutdown()
        db_conn.close()
        logging.info("💀 Shutdown completo.")

if __name__ == "__main__":
    asyncio.run(main())