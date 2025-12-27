# utils/sender.py
import asyncio
import logging
import time
from typing import Optional
from telethon import errors

class OutMsg:
    def __init__(self, entity, text: str, file: Optional[str] = None):
        self.entity = entity
        self.text = text
        self.file = file

class ForwarderSender:
    """
    Sender único con cola y rate limit suave para evitar FloodWait y reintentos caóticos.
    """
    def __init__(self, client, rate_per_sec: float = 1.5, max_retries: int = 6):
        self.client = client
        self.queue = asyncio.Queue()
        self.min_interval = 1.0 / max(rate_per_sec, 0.1)
        self.max_retries = max_retries
        self._last_sent_ts = 0.0
        self._task = None
        self._stop = asyncio.Event()

    async def start(self):
        self._task = asyncio.create_task(self._worker())

    async def stop(self):
        self._stop.set()
        # drena si quieres: await self.queue.join()
        if self._task:
            await self._task

    async def send(self, entity, text: str, file: Optional[str] = None):
        await self.queue.put(OutMsg(entity, text, file))

    async def _worker(self):
        while not self._stop.is_set():
            try:
                msg: OutMsg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Rate limit “suave”
            now = time.monotonic()
            elapsed = now - self._last_sent_ts
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)

            # Intentos con manejo de FloodWait
            attempt = 0
            while attempt < self.max_retries:
                try:
                    if msg.file:
                        await self.client.send_message(msg.entity, msg.text, file=msg.file)
                    else:
                        await self.client.send_message(msg.entity, msg.text)
                    self._last_sent_ts = time.monotonic()
                    break
                except errors.FloodWaitError as fw:
                    wait_s = int(getattr(fw, "seconds", 5))
                    logging.info(f"[SENDER] FloodWait {wait_s}s; durmiendo…")
                    await asyncio.sleep(wait_s + 1)
                except Exception as e:
                    attempt += 1
                    logging.warning(f"[SENDER] Fallo envío (intento {attempt}): {e}")
                    await asyncio.sleep(min(2 * attempt, 10))
            else:
                logging.error("[SENDER] Descartando mensaje tras múltiples intentos.")

            self.queue.task_done()
