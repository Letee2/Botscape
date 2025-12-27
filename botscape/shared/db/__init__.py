# botscape/shared/db/__init__.py

# Exponemos desde los nuevos módulos
from .core import get_conn, execute, executemany, execute_sql
from .ingest import (
    upsert_bot, insert_message, insert_entities_batch, 
    insert_attachments_batch, MessageRecord, AttachmentRecord, EntityRecord
)

# caching.py (read_sql) NO se expone aquí para evitar cargar Streamlit en el listener.
# El Dashboard lo importará explícitamente desde .caching
