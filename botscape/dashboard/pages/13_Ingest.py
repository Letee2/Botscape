# botscape/dashboard/pages/14_Ingest.py
import streamlit as st
from botscape.services.ingest_tools import extract_and_inject_from_hash, inject_manual_token

st.set_page_config(page_title="Ingest Manager", page_icon="📥", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .ingest-box {
        background: #161b22; border: 1px solid #30363d;
        padding: 30px; border-radius: 12px; text-align: center;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("## 📥 Ingest Manager")
st.caption("Añade nuevos vectores de ataque al sistema de monitorización.")

with st.container(border=True):
    st.markdown("### 🎯 Inyección Rápida")
    
    input_val = st.text_input(
        "Pega aquí un **Token de Telegram** o un **Hash SHA256**", 
        placeholder="123456:ABC... o a4f5...",
        help="El sistema detectará automáticamente si es un Token o un Hash."
    )
    
    if st.button("Procesar Entrada", type="primary", use_container_width=True):
        if not input_val:
            st.warning("El campo está vacío.")
            st.stop()
            
        input_clean = input_val.strip()
        
        # Lógica de detección
        if ":" in input_clean and len(input_clean) > 20:
            # Parece un Token
            with st.spinner("Registrando Bot..."):
                res = inject_manual_token(input_clean)
                if res["status"] == "success":
                    st.success(res["msg"])
                else:
                    st.error(res["msg"])
                    
        elif len(input_clean) == 64:
            # Parece un Hash
            with st.spinner("Contactando VirusTotal y analizando muestra..."):
                res = extract_and_inject_from_hash(input_clean)
                
                if res["status"] == "success":
                    st.success(res["msg"])
                    if res["tokens_found"]:
                        st.markdown("---")
                        st.markdown("**Tokens extraídos:**")
                        for t in res["tokens_found"]:
                            st.code(t, language="text")
                elif res["status"] == "warning":
                    st.warning(res["msg"])
                else:
                    st.error(res["msg"])
        else:
            st.error("Formato no reconocido. Debe ser un Token válido o un SHA256.")

st.info("ℹ️ Los bots añadidos serán verificados y monitorizados por el Listener en el siguiente ciclo (max 10 min).")