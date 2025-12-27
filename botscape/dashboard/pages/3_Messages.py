import sys
import os
import io
import re
import streamlit as st
import pandas as pd
from PIL import Image
from datetime import date, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
from botscape.shared.db.caching import list_tokens
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Messages", page_icon="💬", layout="wide")

st.markdown(
    """
    <style>
    .hero-messages{
        background: linear-gradient(135deg,#062a2f 0%,#0a3e48 55%,#0f5966 100%);
        border:1px solid #0e3a42; border-radius:14px; padding:16px 18px;
        color:#e9fbff;
        box-shadow:0 2px 12px rgba(6,42,47,.35) inset;
    }
    .hero-messages .muted{ color:#bfe7ee; font-size:.92rem; }
    </style>
    <div class="hero-messages">
      <h2 style="margin:0 0 6px 0;">💬 Messages</h2>
      <div class="muted">
        Investigación detallada: filtros, resaltado de entidades y adjuntos en contexto.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Helpers Locales (Visualización)
# -----------------------------
def dt_range(start_date: date, end_date: date):
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso   = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"
    return start_iso, end_iso

def is_image_path(p: str) -> bool:
    if not p: return False
    return os.path.splitext(p.lower())[1] in {".png", ".jpg", ".jpeg", ".gif", ".webp"}

def open_image_safe(path: str):
    try:
        with open(path, "rb") as f:
            return Image.open(io.BytesIO(f.read())).convert("RGB")
    except Exception:
        return None

def escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def highlight_entities(text: str, ents_df: pd.DataFrame) -> str:
    if not text: return ""
    if ents_df is None or ents_df.empty: return escape_html(text)
    values = sorted(set(ents_df["value"].astype(str).tolist()), key=len, reverse=True)
    html = escape_html(text)
    for v in values:
        v_esc = escape_html(v)
        try:
            pattern = re.escape(v_esc)
            html = re.sub(pattern, lambda m: f"<mark>{m.group(0)}</mark>", html, flags=re.IGNORECASE)
        except re.error: pass
    return html

# -----------------------------
# Filtros
# -----------------------------
tokens = list_tokens()
colf1, colf2, colf3 = st.columns([2, 1, 1])
with colf1:
    token = st.selectbox("Bot", options=tokens, index=0 if tokens else None, placeholder="Selecciona un bot")
with colf2:
    days = st.slider("Ventana (días)", 1, 60, 14)
with colf3:
    end_date = st.date_input("Hasta (UTC)", value=date.today())

if not token:
    st.info("No hay bots disponibles.")
    st.stop()

start_date = end_date - timedelta(days=days - 1)
start_iso, end_iso = dt_range(start_date, end_date)

c2a, c2b, c2c, c2d = st.columns([2, 1, 1, 1])
with c2a:
    q_text = st.text_input("Buscar texto (LIKE)", "", placeholder="ej: login.php o %token%")
with c2b:
    only_media = st.checkbox("Sólo con media", value=False)
with c2c:
    etype_filter = st.selectbox("Tipo de entidad", options=["(cualquiera)", "email", "url", "ip", "chat_id"])
with c2d:
    evalue = st.text_input("Valor entidad (LIKE)", "", placeholder="ej: %example.com%")

# -----------------------------
# Tabla Principal (Llamada a queries.py)
# -----------------------------
# Toda la lógica de construcción de SQL ahora está encapsulada
df_all = queries.get_filtered_messages(
    token=token,
    start_iso=start_iso,
    end_iso=end_iso,
    text_query=q_text,
    only_media=only_media,
    etype=etype_filter,
    evalue=evalue,
    limit=5000
)

st.caption(f"Conjunto filtrado: {len(df_all)} mensajes (máximo 5000).")

# -----------------------------
# Paginación y Selector
# -----------------------------
colp1, colp2, colp3 = st.columns([1,1,2])
with colp1:
    page_size = st.selectbox("Tamaño página", options=[25, 50, 100, 200], index=1)
with colp2:
    total_pages = max(1, (len(df_all) + page_size - 1) // page_size)
    if "force_page" in st.session_state:
        page_num = st.session_state.pop("force_page")
    else:
        page_num = 1
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=page_num, step=1)

start_idx = (page - 1) * page_size
end_idx = min(start_idx + page_size, len(df_all))
df_page = df_all.iloc[start_idx:end_idx].copy()

csel1, csel2 = st.columns([3, 1])
with csel1:
    st.dataframe(df_page, width='stretch', hide_index=True)
with csel2:
    if not df_page.empty:
        ids = df_page["id"].astype(int).tolist()
        default_id = ids[0]
        if "jump_to_id" in st.session_state:
            jump_id = st.session_state.pop("jump_to_id")
            if jump_id in ids: default_id = jump_id
        sel_id = st.selectbox("Mensaje (ID interno)", options=ids, index=ids.index(default_id))
    else:
        sel_id = None

# Export
csv = df_all.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Exportar conjunto (CSV)", csv, f"messages_{token[:10]}.csv", "text/csv", width='stretch')

st.markdown("---")

# -----------------------------
# Detalle del Mensaje
# -----------------------------
st.subheader("Detalle del mensaje")

if sel_id is None:
    st.info("Selecciona un mensaje para ver el detalle.")
    st.stop()

# Carga de detalles (vía queries.py)
df_full = queries.get_message_detail(int(sel_id))

if df_full.empty:
    st.warning("Mensaje no encontrado.")
    st.stop()

row = df_full.iloc[0]
df_ents = queries.get_message_entities(int(sel_id))
df_atts = queries.get_message_attachments(int(sel_id))

# Navegación Anterior/Siguiente
cur_idx_list = df_all.index[df_all["id"] == sel_id].tolist()
cur_idx = cur_idx_list[0] if cur_idx_list else None

nav1, _, nav3 = st.columns([1,2,1])
with nav1:
    if cur_idx is not None and cur_idx > 0:
        if st.button("⬅️ Anterior"):
            st.session_state["jump_to_id"] = int(df_all.iloc[cur_idx - 1]["id"])
            st.rerun()
with nav3:
    if cur_idx is not None and cur_idx + 1 < len(df_all):
        if st.button("Siguiente ➡️"):
            st.session_state["jump_to_id"] = int(df_all.iloc[cur_idx + 1]["id"])
            st.rerun()

# Metadatos
m1, m2, m3, m4 = st.columns(4)
m1.metric("ID interno", int(row["id"]))
m2.metric("Msg ID", str(row["message_id"]))
m3.metric("Chat ID", str(row["chat_id"]))
m4.metric("Sender ID", str(row["sender_id"]))
st.caption(f"Bot: `{row['token']}`  •  Fecha (UTC): {row['date_utc']}")

# Contenido
st.markdown("**Contenido**")
html = highlight_entities(row["text"] or "", df_ents)
st.markdown(f"<div style='white-space:pre-wrap;font-family:monospace;font-size:13.5px;background:#0b1116;color:#e2e8f0;padding:12px;border-radius:8px;'>{html}</div>", unsafe_allow_html=True)

# Entidades y Adjuntos
st.markdown("**Entidades detectadas**")
if not df_ents.empty: st.dataframe(df_ents, width='stretch', hide_index=True)
else: st.info("No se extrajeron entidades.")

st.markdown("**Adjuntos**")
if not df_atts.empty:
    img_paths = [p for p in df_atts["path"].tolist() if is_image_path(p) and p and os.path.exists(p)]
    other_atts = [r for _, r in df_atts.iterrows() if r["path"] and (not is_image_path(r["path"]) or not os.path.exists(r["path"]))]

    if img_paths:
        st.caption("Imágenes")
        cols = st.columns(6)
        for i, p in enumerate(img_paths[:24]):
            im = open_image_safe(p)
            if im:
                with cols[i % 6]: st.image(im, caption=os.path.basename(p), width='stretch')
    if other_atts:
        st.caption("Otros adjuntos")
        df_other = pd.DataFrame([{"archivo": os.path.basename(r["path"]), "mime": r["mime"], "size": r["size"], "ruta": r["path"]} for r in other_atts])
        st.dataframe(df_other, width='stretch', hide_index=True)
else:
    st.info("Sin adjuntos asociados.")

st.caption("Tip: usa los filtros para cazar IOCs y navega en serie.")