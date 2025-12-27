import sys
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

# --- IMPORTS REFACTORIZADOS ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# -----------------------------
# Configuración Página
# -----------------------------
st.set_page_config(page_title="Overview", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .hero-overview{
        background: linear-gradient(135deg,#0b1220 0%,#1a2450 55%,#2b3f8c 100%);
        border:1px solid #1f2a44; border-radius:14px; padding:16px 18px;
        color:#e6eefb;
        box-shadow:0 2px 12px rgba(12,18,32,.35) inset;
    }
    .hero-overview .muted{ color:#b8c3dc; font-size:.92rem; }
    </style>
    <div class="hero-overview">
      <h2 style="margin:0 0 6px 0;">📊 Overview</h2>
      <div class="muted">
        Vista general del comportamiento de los bots.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Helpers Locales (UI Only)
# -----------------------------
def dt_range(start_date: date, end_date: date):
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso   = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"
    return start_iso, end_iso

# -----------------------------
# Filtros
# -----------------------------
col_f1, col_f2, col_f3 = st.columns([1.2, 1, 1])
with col_f1:
    days = st.slider("Ventana (días)", 1, 60, 14, help="Ventana temporal para todas las métricas")
with col_f2:
    end_date = st.date_input("Hasta (UTC)", value=date.today())
with col_f3:
    max_bots = st.slider("Máx bots en gráficos comparativos", 3, 20, 8)

start_date = end_date - timedelta(days=days - 1)
cur_start_iso, cur_end_iso = dt_range(start_date, end_date)

# Periodo anterior para deltas
prev_end_date = start_date - timedelta(days=1)
prev_start_date = prev_end_date - timedelta(days=days - 1)
prev_start_iso, prev_end_iso = dt_range(prev_start_date, prev_end_date)

# -----------------------------
# 1. KPIs + Deltas
# -----------------------------
# Reutilizamos las queries globales ya definidas en Home.py
df_kpi_cur = queries.get_global_kpis(cur_start_iso, cur_end_iso)
df_kpi_prev = queries.get_global_kpis(prev_start_iso, prev_end_iso)
df_ent_cur = queries.get_global_entity_count(cur_start_iso, cur_end_iso)
df_ent_prev = queries.get_global_entity_count(prev_start_iso, prev_end_iso)

def safe_val(df, col): return int(df.iloc[0][col] or 0) if not df.empty else 0

bots_cur = safe_val(df_kpi_cur, "bots")
bots_prev = safe_val(df_kpi_prev, "bots")
msgs_cur = safe_val(df_kpi_cur, "msgs")
msgs_prev = safe_val(df_kpi_prev, "msgs")
media_cur = safe_val(df_kpi_cur, "media")
media_prev = safe_val(df_kpi_prev, "media")
ents_cur = safe_val(df_ent_cur, "ents")
ents_prev = safe_val(df_ent_prev, "ents")

pct_media_cur = (media_cur / msgs_cur * 100) if msgs_cur else 0.0
pct_media_prev = (media_prev / msgs_prev * 100) if msgs_prev else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Bots activos", bots_cur, delta=bots_cur - bots_prev)
k2.metric("Mensajes", msgs_cur, delta=msgs_cur - msgs_prev)
k3.metric("Entidades extraídas", ents_cur, delta=ents_cur - ents_prev)
k4.metric("% mensajes con media", f"{pct_media_cur:.1f}%", delta=f"{(pct_media_cur - pct_media_prev):.1f}%")

st.caption(f"Periodo actual: {start_date.isoformat()} → {end_date.isoformat()}  |  Periodo anterior: {prev_start_date.isoformat()} → {prev_end_date.isoformat()}")

# -----------------------------
# 2. Botscape (Bubble Chart)
# -----------------------------
st.subheader("Botscape — volumen y riqueza de información")

# Llamada a la nueva query específica
df_botscape = queries.get_botscape_scatter_data(cur_start_iso, cur_end_iso, limit=100)

if len(df_botscape):
    df_botscape["ents_per_msg"] = np.where(df_botscape["msgs"] > 0, df_botscape["ents"] / df_botscape["msgs"], 0.0)
    df_plot = df_botscape.head(max_bots)

    fig = px.scatter(
        df_plot,
        x="msgs",
        y="ents_per_msg",
        size="msgs",
        color="ents_per_msg",
        hover_name="token",
        size_max=70,
        labels={"msgs": "Mensajes", "ents_per_msg": "Entidades por mensaje"},
        title="Cada burbuja es un bot — tamaño: #mensajes, color: entidades/mensaje"
    )
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width='stretch')
else:
    st.info("No hay datos para el rango seleccionado.")

# -----------------------------
# 3. Heatmap día/hora
# -----------------------------
st.subheader("Patrón temporal — Heatmap día x hora (UTC)")

df_heat = queries.get_hourly_heatmap_data(cur_start_iso, cur_end_iso)

if len(df_heat):
    # Aseguramos que 'hour' sea entero para un pivoting correcto
    df_heat['hour'] = df_heat['hour'].astype(int)
    pivot = df_heat.pivot(index="day", columns="hour", values="msgs").fillna(0).astype(int)
    # Rellenar horas faltantes (0-23)
    pivot = pivot.reindex(columns=range(24), fill_value=0)
    
    fig_hm = px.imshow(
        pivot,
        labels=dict(x="Hora (UTC)", y="Día", color="Mensajes"),
        aspect="auto",
        title="Actividad por día y hora"
    )
    fig_hm.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig_hm, width='stretch')
else:
    st.info("No hay actividad en el rango dado.")

# -----------------------------
# 4. Timeline apilada (Top bots)
# -----------------------------
st.subheader("Evolución por bot (Top)")

df_tl = queries.get_stacked_timeline_data(cur_start_iso, cur_end_iso, limit=max_bots)

if len(df_tl):
    df_wide = df_tl.pivot(index="day", columns="token", values="msgs").fillna(0)
    fig_stacked = go.Figure()
    for col in df_wide.columns:
        fig_stacked.add_trace(go.Bar(name=col, x=df_wide.index, y=df_wide[col]))
    fig_stacked.update_layout(barmode="stack", height=430, title="Mensajes por día (top bots apilados)", margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig_stacked, width='stretch')
else:
    st.info("No hay suficientes datos para la comparación.")

# -----------------------------
# 5. Treemap de entidades
# -----------------------------
st.subheader("Mapa de entidades (Treemap)")
topN_treemap = st.slider("Top valores por tipo", 5, 50, 15, help="Número de valores por tipo a incluir en el treemap")

# Reutilizamos la query de entidades top que ya existe
df_ent_treemap = queries.get_top_entities_values(cur_start_iso, cur_end_iso, limit=topN_treemap)

if len(df_ent_treemap):
    fig_tree = px.treemap(
        df_ent_treemap,
        path=[px.Constant("entities"), "etype", "value"],
        values="cnt",
        color="cnt",
        color_continuous_scale="Blues",
    )
    fig_tree.update_layout(height=460, margin=dict(l=0, r=0, t=30, b=10))
    st.plotly_chart(fig_tree, width='stretch')
else:
    st.info("Sin entidades en el periodo seleccionado.")

# Footer
st.caption("Consejo: usa 7–14 días para patrones, y limita bots a 6–10 para comparativas visuales más legibles.")