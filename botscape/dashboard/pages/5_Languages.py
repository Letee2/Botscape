import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

# --- IMPORTS DE ARQUITECTURA ---
from botscape.config import settings
import botscape.shared.db.queries as queries

# =========================
# MAPEO DE IDIOMAS 
# =========================
LANG_MAP = {
    'af': 'Afrikáans', 'ar': 'Árabe', 'bg': 'Búlgaro', 'bn': 'Bengalí', 'ca': 'Catalán', 
    'cs': 'Checo', 'da': 'Danés', 'de': 'Alemán', 'el': 'Griego', 'en': 'Inglés', 
    'es': 'Español', 'et': 'Estonio', 'fa': 'Persa (Farsi)', 'fi': 'Finés', 'fr': 'Francés', 
    'he': 'Hebreo', 'hi': 'Hindi', 'hr': 'Croata', 'hu': 'Húngaro', 'id': 'Indonesio', 
    'it': 'Italiano', 'ja': 'Japonés', 'ko': 'Coreano', 'lt': 'Lituano', 'lv': 'Letón', 
    'nl': 'Holandés', 'no': 'Noruego', 'pl': 'Polaco', 'pt': 'Portugués', 'ro': 'Rumano', 
    'ru': 'Ruso', 'sk': 'Eslovaco', 'sl': 'Esloveno', 'sv': 'Sueco', 'th': 'Tailandés', 
    'tr': 'Turco', 'uk': 'Ucraniano', 'vi': 'Vietnamita', 'zh-cn': 'Chino (Simplificado)'
}

# =========================
# Configuración Página
# =========================
st.set_page_config(page_title="Language Analysis", page_icon="🌐", layout="wide")

st.markdown(
    """
    <style>
    .hero-lang {
        background: linear-gradient(135deg, #2a0a2f 0%, #3e0f48 55%, #591666 100%);
        border:1px solid #3a0e42; border-radius:14px; padding:16px 18px;
        color:#fbe9ff;
        box-shadow:0 2px 12px rgba(42,10,47,.35) inset;
    }
    .hero-lang .muted{ color:#dcbfe7; font-size:.92rem; }
    </style>
    <div class="hero-lang">
      <h2 style="margin:0 0 6px 0;">🌐 Language & Token Analysis</h2>
      <div class="muted">
        Analiza los idiomas y los términos más frecuentes en los mensajes C2.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# Helpers y Filtros
# =========================
def dt_helpers(start_date: date, end_date: date):
    # Necesitamos YYYY-MM-DD para tablas agregadas, e ISO para drill-down
    start_iso = f"{start_date.isoformat()}T00:00:00Z"
    end_iso = f"{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z"
    # Para las tablas de métricas (date column) usamos string simple YYYY-MM-DD
    return start_date.isoformat(), end_date.isoformat(), start_iso, end_iso

st.write("")
c_f1, c_f2 = st.columns([1, 1])
with c_f1:
    days = st.slider("Ventana (días)", 1, 60, 14, key="lang_days")
with c_f2:
    end_date = st.date_input("Hasta (UTC)", value=date.today(), key="lang_end")

start_date = end_date - timedelta(days=days - 1)
agg_start, agg_end, raw_start_iso, raw_end_iso = dt_helpers(start_date, end_date)

# =========================
# Carga de Datos (Desde queries.py)
# =========================
# Usamos las fechas formato 'YYYY-MM-DD' para las tablas agregadas
df_lang_stats = queries.get_aggregated_languages(agg_start, agg_end)
df_words = queries.get_aggregated_words(agg_start, agg_end)

if df_lang_stats.empty or df_words.empty:
    st.info("No hay datos de idioma o palabras. Ejecuta `scripts/aggregate_metrics.py`.")
    st.stop()

# =========================
# Análisis de Lenguaje
# =========================
st.subheader("Análisis de Idioma (Global)")
st.caption(f"Resultados pre-calculados desde {agg_start} hasta {agg_end}")

c_l1, c_l2 = st.columns([1, 2])
with c_l1:
    total_msgs = int(df_lang_stats["count"].sum())
    st.metric("Mensajes con idioma fiable", f"{total_msgs:,}")
    st.metric("Idiomas únicos detectados", len(df_lang_stats))

with c_l2:
    df_lang_stats['language_full'] = df_lang_stats['language'].map(LANG_MAP).fillna(df_lang_stats['language'])
    fig_lang = px.pie(
        df_lang_stats.head(10), 
        names="language_full", 
        values="count",
        title="Distribución de Idiomas (Top 10)",
        hole=0.3
    )
    fig_lang.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_lang, width='stretch')

# =========================
# Análisis de Palabras (Tokens)
# =========================
st.subheader("Análisis de Términos (Global)")
st.markdown("Términos más frecuentes (excluyendo *stopwords*).")

col_w1, col_w2 = st.columns([1, 2])

with col_w1:
    st.markdown("**Términos más usados**")
    word_selection = st.selectbox(
        "Selecciona un término para ver detalles:",
        options=df_words["word"],
        index=0
    )
    st.dataframe(df_words, width='stretch', height=700, hide_index=True)

with col_w2:
    st.markdown(f"**Uso de \"{word_selection}\" en el tiempo**")
    
    # Calcular timeline (rápido, desde agregados)
    df_timeline = queries.get_word_timeline(word_selection, agg_start, agg_end)
    
    if not df_timeline.empty:
        fig_time = px.area(df_timeline, x="day", y="count", labels={"day": "Día", "count": "Menciones"})
        fig_time.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_time, width='stretch')
    else:
        st.info("No hay datos de tiempo para este término.")

    # Drill-down de Bots (Consulta lenta a tabla messages)
    st.markdown(f"**Bots que usan \"{word_selection}\" (Top 15)**")
    df_bots = queries.get_bots_for_word(word_selection, raw_start_iso, raw_end_iso)
    
    if not df_bots.empty:
        fig_bots = px.bar(df_bots, x="count", y="token", orientation="h", labels={"token": "Bot", "count": "Menciones"})
        fig_bots.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bots, width='stretch')
    else:
        st.info(f"Ningún bot mencionó '{word_selection}' en esta ventana.")