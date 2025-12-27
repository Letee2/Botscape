import sys
import os
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Entities", page_icon="🧩", layout="wide")

st.markdown(
    """
    <style>
    .hero-entities {
        background: linear-gradient(135deg, #12200b 0%, #1b2f0f 100%);
        border: 1px solid #23451a; padding: 16px 18px; border-radius: 14px; color: #e8fae6;
    }
    .muted { color: #b3d3b1; font-size: 0.92rem; }
    </style>
    <div class="hero-entities">
      <h2 style="margin:0 0 6px 0;">🧩 Entities</h2>
      <div class="muted">
        Patrones de datos recurrentes en el ecosistema.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Helpers Locales
# -----------------------------
def dt_range(start_date: date, end_date: date):
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso   = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"
    return start_iso, end_iso

def normalize_value(etype: str, value: str) -> str:
    """Agrupación suave de valores para visualización (Logic UI)."""
    if not isinstance(value, str): return value
    v = value.strip()
    if etype in ("url", "domain"):
        v = re.sub(r"^[a-z]+://", "", v, flags=re.I).split("/")[0]
        v = re.sub(r"^www\.", "", v, flags=re.I)
        return v.lower()
    if etype in ("email",): return v.lower().split("@")[-1]
    if etype in ("ip", "ipv4"):
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$", v)
        if m: return f"{m.group(1)}.{m.group(2)}.{m.group(3)}.0/24"
        return v
    if etype in ("file_path", "path"):
        parts = re.split(r"[\\/]", v)
        return f"{parts[0]}\\{parts[1]}\\…" if len(parts) > 2 else v
    if etype in ("credential", "password", "token"): return etype
    return v

# -----------------------------
# Filtros
# -----------------------------
c1, c2, c3, c4 = st.columns([1.6, 1, 1, 1])
with c1:
    days = st.slider("Ventana (días)", 1, 60, 14)
with c2:
    end_date = st.date_input("Hasta (UTC)", value=date.today())
with c3:
    topN = st.slider("Top grupos por tipo", 5, 50, 15)
with c4:
    min_msgs = st.slider("Min. mensajes por grupo", 1, 50, 3)

start_date = end_date - timedelta(days=days - 1)
start_iso, end_iso = dt_range(start_date, end_date)

# Cargar tipos disponibles para el selector
df_types = queries.get_entity_types_stats(start_iso, end_iso)
etype_opts = ["(todos)"] + df_types["etype"].tolist() if not df_types.empty else ["(todos)"]

colt1, colt2 = st.columns([1.2, 2])
with colt1:
    etype_sel = st.selectbox("Tipo de entidad", etype_opts)
with colt2:
    q_value = st.text_input("Filtro por valor (LIKE)", "", placeholder="ej: %example.com%")

# -----------------------------
# Carga y Procesamiento
# -----------------------------
# Obtenemos datos crudos para procesar en Python (Pandas)
df_raw = queries.get_raw_entities_sample(start_iso, end_iso, etype_sel, q_value, limit=100000)

if df_raw.empty:
    st.info("No hay entidades para el rango/filtros seleccionados.")
    st.stop()

# Aplicar normalización
df_raw["group_value"] = [normalize_value(et, val) for et, val in zip(df_raw["etype"], df_raw["value"])]

# -----------------------------
# Ranking (Pandas)
# -----------------------------
st.subheader("Grupos principales por tipo")

df_rank = (
    df_raw.groupby(["etype", "group_value"])
          .agg(msgs=("message_pk", "nunique"),
               bots=("token", "nunique"),
               first_seen=("date_utc", "min"),
               last_seen=("date_utc", "max"))
          .reset_index()
)
df_rank = df_rank[df_rank["msgs"] >= min_msgs].copy()
df_rank["rn"] = df_rank.groupby("etype")["msgs"].rank(method="first", ascending=False)
df_rank_top = df_rank[df_rank["rn"] <= topN].sort_values(["etype", "msgs"], ascending=[True, False])

c_r1, c_r2 = st.columns([1.4, 1])
with c_r1:
    if len(df_rank_top):
        fig_tree = px.treemap(
            df_rank_top,
            path=[px.Constant("entities"), "etype", "group_value"],
            values="msgs",
            color="bots",
            color_continuous_scale="Greens",
        )
        fig_tree.update_layout(height=460, margin=dict(l=0, r=0, t=30, b=10))
        st.plotly_chart(fig_tree, width='stretch')
    else:
        st.info("No hay grupos que cumplan los umbrales.")

with c_r2:
    if len(df_rank_top):
        st.dataframe(
            df_rank_top[["etype", "group_value", "msgs", "bots", "first_seen", "last_seen"]],
            width='stretch', height=460
        )

st.markdown("---")

# -----------------------------
# Co-ocurrencias
# -----------------------------
st.subheader("Co-ocurrencias entre grupos")

df_pairs = (
    df_raw[["message_pk", "etype", "group_value"]]
    .drop_duplicates()
    .merge(df_raw[["message_pk", "etype", "group_value"]].drop_duplicates(), on="message_pk")
)
df_pairs = df_pairs[df_pairs["group_value_x"] < df_pairs["group_value_y"]]
top_groups_set = set(df_rank_top["group_value"].astype(str) + "||" + df_rank_top["etype"].astype(str))
df_pairs["key_x"] = df_pairs["group_value_x"].astype(str) + "||" + df_pairs["etype_x"].astype(str)
df_pairs["key_y"] = df_pairs["group_value_y"].astype(str) + "||" + df_pairs["etype_y"].astype(str)
df_pairs = df_pairs[df_pairs["key_x"].isin(top_groups_set) & df_pairs["key_y"].isin(top_groups_set)]

# app/pages/4_Entities.py

if not df_pairs.empty:
    co = df_pairs.groupby(["key_x", "key_y"]).size().reset_index(name="cnt")
    keys = sorted(set(co["key_x"]).union(set(co["key_y"])))
    M = pd.DataFrame(0, index=keys, columns=keys, dtype=int)
    for _, r in co.iterrows():
        M.loc[r["key_x"], r["key_y"]] = r["cnt"]
        M.loc[r["key_y"], r["key_x"]] = r["cnt"]

    # FUNCIÓN CORREGIDA: Mantiene la clave original si hay colisión para garantizar unicidad
    def pretty_unique(k):
        gv, et = k.split("||", 1)
        display = f"{et}:{gv[:28]}"
        return display

    # Aplicamos el nombre amigable pero comprobamos duplicados
    new_labels = [pretty_unique(k) for k in M.index]
    
    # Si hay duplicados en las etiquetas amigables, usamos las claves técnicas 'key_x' 
    # para evitar que narwhals/plotly falle
    if len(new_labels) != len(set(new_labels)):
        # Si hay colisión, dejamos las etiquetas originales (etype:value) que son únicas
        M.index = [f"{k.split('||')[1]}:{k.split('||')[0]}" for k in M.index]
        M.columns = [f"{k.split('||')[1]}:{k.split('||')[0]}" for k in M.columns]
    else:
        M.index = new_labels
        M.columns = new_labels

    fig_hm = px.imshow(
        M, aspect="auto", color_continuous_scale="Greens",
        labels=dict(x="Grupo", y="Grupo", color="Co-ocurrencias")
    )
    fig_hm.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_hm, use_container_width=True)
else:
    st.info("Sin co-ocurrencias relevantes.")

st.markdown("---")

# -----------------------------
# Drill-down
# -----------------------------
st.subheader("Detalle de un grupo")

col_g1, col_g2 = st.columns([2, 1])
with col_g1:
    if len(df_rank_top):
        etype_pick = st.selectbox("Tipo", sorted(df_rank_top["etype"].unique().tolist()))
        df_gr_choices = df_rank_top[df_rank_top["etype"] == etype_pick].sort_values("msgs", ascending=False)
        group_pick = st.selectbox("Grupo", df_gr_choices["group_value"].tolist())
    else:
        st.info("No hay grupos para seleccionar.")
        st.stop()

with col_g2:
    show_msgs = st.slider("Máx. mensajes a listar", 10, 1000, 200)

if group_pick:
    # 1. Obtener todas las entidades de ese tipo para normalizar
    df_evals = queries.get_entities_by_type(start_iso, end_iso, etype_pick)
    
    # 2. Filtrar en Python cuáles coinciden con el grupo seleccionado
    df_evals["norm"] = [normalize_value(etype_pick, v) for v in df_evals["value"]]
    msg_ids = list(set(df_evals.loc[df_evals["norm"] == group_pick, "message_pk"]))
    
    # 3. Recuperar los mensajes completos
    if msg_ids:
        # Limitamos IDs para no romper SQL con una lista gigante
        df_group_msgs = queries.get_messages_by_ids(msg_ids[:show_msgs])
        
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            st.markdown("**Bots implicados**")
            df_bots = df_group_msgs.groupby("token").size().reset_index(name="msgs").sort_values("msgs", ascending=False)
            st.dataframe(df_bots, width='stretch', height=260)

        with col_b2:
            st.markdown("**Timeline del grupo**")
            df_tl = df_group_msgs.copy()
            df_tl["date_utc"] = pd.to_datetime(df_tl["date_utc"])
            df_tl["day"] = df_tl["date_utc"].dt.strftime('%Y-%m-%d')
            df_tl = df_tl.groupby("day").size().reset_index(name="msgs")
            if len(df_tl): st.line_chart(df_tl.set_index("day"))
            else: st.info("Sin timeline.")

        st.markdown("**Mensajes (muestra)**")
        st.dataframe(df_group_msgs[["message_pk", "date_utc", "token", "snippet", "has_media"]], width='stretch', height=320)

        # Export
        csv = df_group_msgs.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Exportar mensajes del grupo (CSV)", csv, f"group_{etype_pick}.csv", "text/csv", width='stretch')
    else:
        st.warning("No se encontraron mensajes para este grupo (posible desincronización).")

st.caption("Tip: usa la agrupación suave para juntar señales.")