import asyncio
import logging
from typing import Dict, List
from telethon import TelegramClient

# Colas globales (Thread-safe para asyncio)
SEND_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=2000)
INGEST_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=5000)

class ListenerState:
    """Gestor del estado en memoria del servicio Listener."""
    
    def __init__(self):
        # Mapa: token -> instancia de cliente
        self.active_clients: Dict[str, TelegramClient] = {}
        
        # Lista de tareas de asyncio (para poder cancelarlas al cerrar)
        self.tasks: List[asyncio.Task] = []
        
        # Evento para detener todos los workers
        self.stop_event = asyncio.Event()

    def add_client(self, token: str, client: TelegramClient):
        self.active_clients[token] = client
        logging.info(f"✅ Cliente registrado: {token[:10]}...")

    def remove_client(self, token: str):
        if token in self.active_clients:
            del self.active_clients[token]
            logging.info(f"❌ Cliente eliminado del pool: {token[:10]}...")

    async def shutdown(self):
        """Cierra ordenadamente todos los recursos."""
        logging.warning("🛑 Iniciando apagado del ListenerState...")
        self.stop_event.set()
        
        # Cancelar tareas de fondo
        for task in self.tasks:
            task.cancel()
        
        # Desconectar clientes de Telegram
        disconnect_coros = [c.disconnect() for c in self.active_clients.values()]
        if disconnect_coros:
            await asyncio.gather(*disconnect_coros, return_exceptions=True)
        
        logging.info("👋 Estado limpio. Apagado completado.")

# Singleton global para el estado
state = ListenerState()