import pandas as pd
from botscape.shared.db.core import get_conn

def get_actor_forensic_data(actor_id: int, limit: int = 50):
    """
    
    1. HARVEST: Qué envían a la flota.
    2. COMMANDS: Qué ordena el actor.
    3. CONTEXT: Qué le responden los bots al actor (Vital para atribución de malware).
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # A. Identificar la Flota (Bots que el actor toca)
            cur.execute("""
                SELECT DISTINCT m.token 
                FROM messages m
                WHERE (m.sender_id = %(aid)s OR m.chat_id = %(aid)s) 
                  AND m.chat_type = 'private'
            """, {'aid': actor_id})
            fleet = [x['token'] for x in cur.fetchall()]
            
            if not fleet:
                return None

            # ==========================================
            # 1. THE HARVEST (Lo que llega de fuera)
            # ==========================================
            # Tráfico dirigido a los bots del actor, pero NO provienen del actor.
            # Aquí buscamos ZIPs, Logs, Credenciales.
            sql_harvest = """
                SELECT 
                    CASE 
                        WHEN m.text ~* '\.zip$' THEN 'ARCHIVE (ZIP)'
                        WHEN m.text ~* '\.rar$' THEN 'ARCHIVE (RAR)'
                        WHEN m.text ~* '\.log$' THEN 'LOG FILE'
                        WHEN m.has_media = 1 THEN 'MEDIA (Unspecified)'
                        ELSE 'TEXT' 
                    END as content_type,
                    m.text as payload,
                    count(*) as frequency
                FROM messages m
                WHERE 
                    m.token = ANY(%(tokens)s) 
                    AND m.sender_id != %(aid)s  -- NO es el actor
                    AND m.chat_id != %(aid)s    -- NO es el chat privado del actor
                    AND m.chat_type = 'private'
                GROUP BY content_type, m.text
                ORDER BY frequency DESC
                LIMIT %(limit)s
            """
            cur.execute(sql_harvest, {'aid': actor_id, 'tokens': fleet, 'limit': limit})
            df_harvest = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])

            # ==========================================
            # 2. ACTOR COMMANDS (Lo que el actor ordena)
            # ==========================================
            sql_commands = """
                SELECT 
                    m.text as command,
                    count(*) as frequency
                FROM messages m
                WHERE 
                    m.sender_id = %(aid)s -- El actor habla
                    AND m.chat_type = 'private'
                    AND m.text IS NOT NULL
                GROUP BY m.text
                ORDER BY frequency DESC
                LIMIT %(limit)s
            """
            cur.execute(sql_commands, {'aid': actor_id, 'limit': limit})
            df_commands = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])

            # ==========================================
            # 3. BOT RESPONSES (Lo que los bots le dicen al actor)
            # ==========================================
            
            sql_responses = """
                SELECT 
                    b.display_name as bot_name,
                    m.text as bot_reply,
                    count(*) as frequency
                FROM messages m
                LEFT JOIN bots b ON m.token = b.token
                WHERE 
                    m.chat_id = %(aid)s     -- En el chat del actor
                    AND m.sender_id != %(aid)s -- Pero NO lo escribió el actor (lo escribió el bot)
                    AND m.chat_type = 'private'
                    AND m.text IS NOT NULL
                GROUP BY b.display_name, m.text
                ORDER BY frequency DESC
                LIMIT %(limit)s
            """
            cur.execute(sql_responses, {'aid': actor_id, 'limit': limit})
            df_responses = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])

        return {
            "fleet_count": len(fleet),
            "harvest": df_harvest,   # Origen -> Bot
            "commands": df_commands, # Actor -> Bot
            "responses": df_responses # Bot -> Actor
        }

    except Exception as e:
        print(f"❌ Error en forense: {e}")
        return None
    finally:
        conn.close()

def generate_llm_forensic_prompt(actor_id, data):
    """
    Genera el prompt con la distinción tripartita para el LLM.
    """
    df_harvest = data['harvest']
    df_commands = data['commands']
    df_responses = data['responses']
    
    # 1. Muestras de Cosecha (Harvest)
    harvest_txt = []
    if not df_harvest.empty:
        for _, row in df_harvest.head(15).iterrows():
            txt = str(row['payload'])[:100].replace('\n', ' ')
            harvest_txt.append(f"- [EXTERNAL_SOURCE] sent [{row['content_type']}]: \"{txt}\"")
    else:
        harvest_txt.append("- (No external traffic detected)")

    # 2. Muestras de Comandos (Commands)
    commands_txt = []
    if not df_commands.empty:
        for _, row in df_commands.head(15).iterrows():
            txt = str(row['command'])[:100].replace('\n', ' ')
            commands_txt.append(f"- [ACTOR] sent: \"{txt}\"")
    else:
        commands_txt.append("- (Actor is silent/passive)")

    # 3. Muestras de Respuesta (Context)
    responses_txt = []
    if not df_responses.empty:
        for _, row in df_responses.head(15).iterrows():
            bot = row['bot_name'] or "UnknownBot"
            txt = str(row['bot_reply'])[:150].replace('\n', ' ') # Más longitud aquí, suele estar la "marca"
            responses_txt.append(f"- [BOT '{bot}'] replied to Actor: \"{txt}\"")
    else:
        responses_txt.append("- (Bots did not reply with text)")

    prompt = f"""
    You are a Forensic Intelligence Analyst examining Telegram traffic for Actor {actor_id}.
    
    ### THE EVIDENCE TRIANGLE:
    
    **1. THE HARVEST (What is sent to the infrastructure):**
    *Look for ZIPs, Logs, or Credentials coming from outside.*
    {chr(10).join(harvest_txt)}

    **2. THE ACTOR'S VOICE (What the actor commands):**
    *Look for Admin commands (/ban, /add) or configurations.*
    {chr(10).join(commands_txt)}

    **3. THE INFRASTRUCTURE'S VOICE (What the bots say back to the Actor):**
    *CRITICAL: Look here for Malware Names (e.g., "Welcome to RedLine Panel"). The bots often identify themselves.*
    {chr(10).join(responses_txt)}

    ### MISSION:
    Reconstruct the operation based on these three perspectives.
    
    **OUTPUT FORMAT (JSON):**
    {{
        "operational_profile": "A strictly factual summary in Spanish (approx 60 words). Explain the flow: What comes in (Harvest), what the actor does (Commands), and what the software is (Responses).",
        "role_hypothesis": "Role based on evidence (e.g., 'MaaS Vendor' only if selling, 'Botnet Admin' if commanding, 'Traffer' if just pushing logs).",
        "evidence_quotes": [
            "Quote 1: Extract the specific text where the BOT identifies itself (e.g., 'Welcome to X').",
            "Quote 2: Extract text proving the actor's intent."
        ],
        "detected_software": "Name of malware/bot found in SECTION 3 (e.g. 'RedLine', 'Lumma', 'OTP Bot'). If none, return 'None'.",
        "confidence_score": "High/Medium/Low"
    }}
    """
    return prompt