# utils/sessions.py
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

def _session_paths(bot_token: str, base_dir: str):
    bot_id = bot_token.split(":")[0]
    sdir = os.path.join(base_dir, bot_id)
    os.makedirs(sdir, exist_ok=True)
    spath = os.path.join(sdir, "string.session")
    return sdir, spath

def load_or_create_string_session(bot_token: str, base_dir: str) -> tuple[StringSession, str]:
    _, spath = _session_paths(bot_token, base_dir)
    if os.path.exists(spath):
        with open(spath, "r", encoding="utf-8") as f:
            s = f.read().strip()
        return StringSession(s), spath
    else:
        return StringSession(), spath

async def start_monitored_client_with_string(api_id: int, api_hash: str, bot_token: str, base_dir: str) -> TelegramClient:
    sess, spath = load_or_create_string_session(bot_token, base_dir)
    client = TelegramClient(
        sess, api_id, api_hash,
        flood_sleep_threshold=15,
        connection_retries=10,
        retry_delay=2,
        request_retries=5
    )
    await client.start(bot_token=bot_token)
    # Guardar el string si es nuevo o está vacío
    s = client.session.save()
    if (not os.path.exists(spath)) or os.path.getsize(spath) == 0:
        with open(spath, "w", encoding="utf-8") as f:
            f.write(s)
    return client
