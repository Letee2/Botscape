import logging
import ppdeep
from botscape.shared.db.core import get_conn

# Configuración
SSDEEP_THRESHOLD = 80 # Similitud mínima para considerar relación

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [SIMILARITY] %(message)s")

def run_clustering():
    logging.info("🔄 Iniciando motor de correlación de malware...")
    
    conn = get_conn()
    try:
        # 1. Cargar muestras con ssdeep/imphash
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sha256, ssdeep, imphash 
                FROM samples_intelligence 
                WHERE ssdeep IS NOT NULL OR imphash IS NOT NULL
            """)
            samples = cur.fetchall()
            
        logging.info(f"📋 Analizando {len(samples)} muestras...")
        new_links = 0
        
        # 2. Comparación "Todos contra Todos" (Optimizable en el futuro)
        # Para N < 10,000 esto es aceptable.
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                s1 = samples[i]
                s2 = samples[j]
                
                match_found = False
                method = ""
                score = 0
                
                # A. Check Imphash (Exacto)
                if s1['imphash'] and s2['imphash'] and s1['imphash'] == s2['imphash']:
                    match_found = True
                    method = "imphash_exact"
                    score = 100
                
                # B. Check SSDeep (Fuzzy) si no hubo match exacto previo
                if not match_found and s1['ssdeep'] and s2['ssdeep']:
                    try:
                        fuzzy_score = ppdeep.compare(s1['ssdeep'], s2['ssdeep'])
                        if fuzzy_score >= SSDEEP_THRESHOLD:
                            match_found = True
                            method = "ssdeep"
                            score = fuzzy_score
                    except Exception:
                        pass

                # 3. Guardar Enlace
                if match_found:
                    # Ordenar hashes para evitar duplicados (A-B vs B-A)
                    h1, h2 = sorted([s1['sha256'], s2['sha256']])
                    
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO malware_similarity_links (sha256_a, sha256_b, score, method, detected_at)
                            VALUES (%s, %s, %s, %s, NOW())
                            ON CONFLICT (sha256_a, sha256_b) DO UPDATE SET
                                score = EXCLUDED.score,
                                detected_at = NOW();
                        """, (h1, h2, score, method))
                        
                        # Detectar si fue un insert real (opcional)
                        new_links += 1

        conn.commit()
        logging.info(f"✅ Análisis finalizado. Se procesaron/actualizaron enlaces de similitud.")

    except Exception as e:
        logging.error(f"❌ Error crítico: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_clustering()