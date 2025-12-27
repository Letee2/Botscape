import pandas as pd
import sys
import logging
import re
import difflib  
from botscape.shared.db.core import get_conn

# --- CONFIGURACIÓN DE LOGGING ---
logger = logging.getLogger("DeepDive")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - [DEEPDIVE] - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class ActorDeepDive:
    def __init__(self, actor_id):
        self.actor_id = str(actor_id)
        self.conn = get_conn()
        self.report = {}
        logger.info(f"🏁 INICIANDO AUDITORÍA PARA: {self.actor_id}")

    def close(self):
        if self.conn: 
            self.conn.close()
            logger.info("🔌 Conexión cerrada.")

    def run_full_audit(self):
        try:
            # 0. FLOTA
            self.fleet_tokens = self._get_fleet_tokens_debug()
            
            # 1. ESTRUCTURA
            self.report['profile'] = self._get_basic_profile()
            self.report['infrastructure'] = self._audit_infrastructure()
            
            # 2. HUELLA
            self.report['subscriptions'] = self._get_passive_subscriptions()
            self.report['bot_footprint'] = self._get_bot_footprint()
            
            # 3. ACTIVOS
            self.report['assets'] = self._extract_financial_and_social_assets()
            
            # 4. MOVIMIENTO (Lento pero seguro)
            self.report['content_movement'] = self._trace_content_movement_strict()
            
            # 5. DIRECTO
            self.report['direct_activity'] = self._get_actor_direct_activity()
            
            return self.report
        except Exception as e:
            logger.error(f"❌ ERROR CRÍTICO: {e}", exc_info=True)
            return {}
        finally:
            self.close()

    # --- MOTOR SQL ---
    def _fetch_debug(self, label, sql, params=None):
        params = params or {}
        logger.info(f"⏳ [STEP: {label}] Querying...")
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    cols = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                else:
                    return pd.DataFrame()

                if not rows:
                    logger.warning(f"   ⚠️ {label}: 0 resultados.")
                    return pd.DataFrame()

                logger.info(f"   ✅ {label}: {len(rows)} filas.")
                clean_data = [dict(zip(cols, row)) if not isinstance(row, dict) else row for row in rows]
                return pd.DataFrame(clean_data)
        except Exception as e:
            self.conn.rollback() 
            logger.error(f"   ❌ {label} - SQL ERROR: {e}")
            return pd.DataFrame()

    # --- LÓGICA DE TRAZABILIDAD ESTRICTA ---
    def _trace_content_movement_strict(self):
       
        if not self.fleet_tokens: return pd.DataFrame()

        # A. INBOUND (Traemos sender_id limpio)
        sql_in = """
            SELECT 
                m.text, m.date_utc, m.sender_id, m.token, 
                m.chat_type,
                b.display_name as bot_name
            FROM messages m
            JOIN bots b ON m.token = b.token
            WHERE m.token = ANY(%(tokens)s) 
              AND m.sender_id != %(aid)s
              AND (LENGTH(m.text) > 20 OR m.text ILIKE '%%.zip' OR m.text ILIKE '%%.rar')
            ORDER BY m.date_utc DESC LIMIT 400
        """
        df_in = self._fetch_debug("TRACE_IN_STRICT", sql_in, {'tokens': self.fleet_tokens, 'aid': self.actor_id})

        # B. OUTBOUND (Traemos chat_id limpio)
        sql_out = """
            SELECT 
                m.text, m.date_utc, m.chat_id, m.chat_title, m.token, 
                b.display_name as bot_name
            FROM messages m
            JOIN bots b ON m.token = b.token
            WHERE m.token = ANY(%(tokens)s)
              AND m.chat_type IN ('channel', 'group', 'supergroup')
              AND (LENGTH(m.text) > 20 OR m.text ILIKE '%%.zip' OR m.text ILIKE '%%.rar')
            ORDER BY m.date_utc DESC LIMIT 400
        """
        df_out = self._fetch_debug("TRACE_OUT_STRICT", sql_out, {'tokens': self.fleet_tokens})

        if df_in.empty or df_out.empty: return pd.DataFrame()

        matches = []
        logger.info("   🔄 Comparación Estricta (Threshold >= 92%)...")
        
        in_records = df_in.to_dict('records')
        out_records = df_out.to_dict('records')

        for out_msg in out_records:
            out_txt = str(out_msg.get('text', ''))
            
            for in_msg in in_records:
                in_txt = str(in_msg.get('text', ''))
                
                match_found = False
                priority_score = 0 # Para ordenar: 2=Archivo, 1=Inclusión, 0=Similitud
                ratio = 0.0

                # 1. Match de Archivos (Prioridad Máxima)
                in_files = re.findall(r'[\w\-]{5,}\.(?:zip|rar|7z|sql)', in_txt.lower())
                if in_files:
                    for f in in_files:
                        if f in out_txt.lower():
                            match_found = True
                            match_quality = "🔥 EXACTO (Archivo)"
                            priority_score = 3
                            ratio = 1.0
                            break
                
                # 2. Match de Texto
                if not match_found:
                    # Inclusión exacta (Prioridad Alta)
                    if len(in_txt) > 30 and in_txt in out_txt:
                        match_found = True
                        match_quality = "✅ CONTENIDO (Inclusión)"
                        priority_score = 2
                        ratio = 1.0
                    else:
                        # Similitud (Solo >= 92%)
                        matcher = difflib.SequenceMatcher(None, in_txt, out_txt)
                        ratio = matcher.ratio()
                        if ratio >= 0.92: 
                            match_found = True
                            match_quality = f"⚠️ ALTA SIMILITUD ({int(ratio*100)}%)"
                            priority_score = 1

                if match_found:
                    # Latencia
                    t_in = in_msg['date_utc']
                    t_out = out_msg['date_utc']
                    delta = (t_out - t_in).total_seconds()
                    direction = "⏩ NORMAL (In -> Out)" if delta >= 0 else "⏪ INVERSO (Out -> In)"
                    
                    # Limpieza de Nombres de Bot (Quitar ' None' si existe)
                    bot_in_clean = str(in_msg['bot_name']).replace(" None", "").strip()
                    bot_out_clean = str(out_msg['bot_name']).replace(" None", "").strip()

                    matches.append({
                        "match_type": match_quality,
                        "priority": priority_score, # Columna oculta para ordenar
                        "ratio": ratio,             # Columna oculta para ordenar
                        
                        "similarity": f"{int(ratio*100)}%",
                        "direction": direction,
                        "latency_str": f"{abs(int(delta))}s",
                        
                        # USAMOS SOLAMENTE IDs
                        "src_node": f"ID: {in_msg['sender_id']}",
                        "dst_node": f"ID: {out_msg['chat_id']}",
                        "dst_name_hint": out_msg['chat_title'], # Solo para tooltip o referencia
                        
                        "bot_in": bot_in_clean,
                        "bot_out": bot_out_clean,
                        
                        "content_snippet": out_txt,
                        "input_full_text": in_txt
                    })
                    break 

        # ORDENAMIENTO: Primero Prioridad (Archivos/Inclusión), Luego Ratio (Similitud más alta)
        if matches:
            df = pd.DataFrame(matches)
            df.sort_values(by=['priority', 'ratio'], ascending=[False, False], inplace=True)
            logger.info(f"   ✅ Trazas Confirmadas: {len(df)}")
            return df
            
        return pd.DataFrame()

    
    def _get_fleet_tokens_debug(self):
        sql = "SELECT DISTINCT token FROM messages WHERE sender_id = %(aid)s OR chat_id = %(aid)s"
        df = self._fetch_debug("IDENTIFY_FLEET", sql, {'aid': self.actor_id})
        if df.empty: return []
        return df['token'].tolist() if 'token' in df.columns else df.iloc[:, 0].tolist()

    def _get_basic_profile(self):
        if not self.fleet_tokens: return pd.DataFrame()
        return self._fetch_debug("PROFILE", "SELECT DISTINCT token, display_name, username FROM bots WHERE token = ANY(%(tokens)s)", {'tokens': self.fleet_tokens})

    def _audit_infrastructure(self):
        if not self.fleet_tokens: return {"c2": pd.DataFrame(), "ips": pd.DataFrame()}
        c2 = self._fetch_debug("INFRA_C2", "SELECT token, display_name, c2_webhook_url FROM bots WHERE token = ANY(%(tokens)s) AND c2_webhook_url IS NOT NULL", {'tokens': self.fleet_tokens})
        return {"c2": c2, "ips": pd.DataFrame()} 

    def _get_passive_subscriptions(self):
        sql = "SELECT forward_from_name, COUNT(*) as freq FROM messages WHERE sender_id = %(aid)s AND forward_from_name IS NOT NULL GROUP BY forward_from_name ORDER BY freq DESC LIMIT 20"
        return self._fetch_debug("SUBSCRIPTIONS", sql, {'aid': self.actor_id})

    def _get_bot_footprint(self):
        if not self.fleet_tokens: return pd.DataFrame()
        sql = "SELECT b.display_name, m.chat_title, COUNT(*) as vol FROM messages m JOIN bots b ON m.token = b.token WHERE m.token = ANY(%(tokens)s) AND m.chat_type IN ('channel', 'group') GROUP BY b.display_name, m.chat_title ORDER BY vol DESC LIMIT 50"
        return self._fetch_debug("BOT_FOOTPRINT", sql, {'tokens': self.fleet_tokens})

    def _extract_financial_and_social_assets(self):
        if not self.fleet_tokens: return pd.DataFrame()
        sql = """
            SELECT text, date_utc, chat_title, 'bot_fleet' as source 
            FROM messages WHERE token = ANY(%(tokens)s) AND LENGTH(text) > 5 LIMIT 1000
        """
        df = self._fetch_debug("ASSET_HUNT", sql, {'tokens': self.fleet_tokens})
        if df.empty: return pd.DataFrame()

        assets = []
        patterns = {
            "BTC": r"(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}",
            "USDT_TRC20": r"T[A-Za-z0-9]{33}",
            "TELEGRAM_ALIAS": r"@[a-zA-Z0-9_]{5,}"
        }
        for _, row in df.iterrows():
            txt = str(row.get('text', ''))
            for p_name, p_val in patterns.items():
                for m in re.findall(p_val, txt):
                    if p_name == "TELEGRAM_ALIAS" and m.lower() in ['@here', '@admin']: continue
                    assets.append({"tipo": p_name, "valor": m, "contexto": txt[:40]})
        
        return pd.DataFrame(assets).drop_duplicates(subset=['tipo', 'valor']) if assets else pd.DataFrame()

    def _get_actor_direct_activity(self):
        return self._fetch_debug("DIRECT_ACT", "SELECT date_utc, chat_title, text FROM messages WHERE sender_id = %(aid)s AND chat_type IN ('group', 'channel') LIMIT 20", {'aid': self.actor_id})

if __name__ == "__main__":
    ActorDeepDive(sys.argv[1] if len(sys.argv) > 1 else "123123123").run_full_audit()