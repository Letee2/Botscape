-- ============================================================================
-- PROYECTO BOTSCAPE - ESQUEMA DE BASE DE DATOS (POSTGRESQL)
-- Versión: 2.0 (Threat Hunting & C2 Intel)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. DOMINIO PRINCIPAL: BOTS Y PERFILES
-- ----------------------------------------------------------------------------

-- Tabla Maestra de Bots
CREATE TABLE IF NOT EXISTS bots (
    token TEXT PRIMARY KEY,
    bot_id BIGINT UNIQUE,
    username TEXT,
    display_name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true, 
    c2_webhook_url TEXT,              
    first_seen_utc TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    last_checked_utc TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bots_active ON bots(is_active);
CREATE INDEX IF NOT EXISTS idx_bots_last_seen ON bots(last_seen);

-- Perfiles de Inteligencia de Bots (Enriquecimiento LLM)
CREATE TABLE IF NOT EXISTS bot_profiles (
    token TEXT PRIMARY KEY REFERENCES bots(token) ON DELETE CASCADE,
    risk_level TEXT,     -- 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'
    actor_intent TEXT,   -- 'Stealer', 'Support', 'Crypto Drainer', 'DDoS', etc.
    summary TEXT,        -- Resumen narrativo
    detected_ttps JSONB, -- Etiquetas TTP (MITRE ATT&CK)
    model_version TEXT,  
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_profiles_risk ON bot_profiles(risk_level);
CREATE INDEX IF NOT EXISTS idx_profiles_intent ON bot_profiles(actor_intent);

-- Etiquetas (Tags) para clasificación automática
CREATE TABLE IF NOT EXISTS bot_tags (
    id SERIAL PRIMARY KEY,
    tag TEXT UNIQUE NOT NULL,
    description TEXT
);

-- Relación N:M Bots <-> Tags
CREATE TABLE IF NOT EXISTS bot_tag_map (
    bot_token TEXT NOT NULL REFERENCES bots(token) ON DELETE CASCADE,
    tag_id INT NOT NULL REFERENCES bot_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (bot_token, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_tag_map_token ON bot_tag_map(bot_token);
CREATE INDEX IF NOT EXISTS idx_tag_map_tag ON bot_tag_map(tag_id);

-- ----------------------------------------------------------------------------
-- 2. DOMINIO DE MENSAJERÍA E INGESTA (C2 TRAFFIC)
-- ----------------------------------------------------------------------------

-- Tabla Central de Mensajes
CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    token           TEXT NOT NULL,
    message_id      BIGINT,
    chat_id         TEXT,
    chat_type       TEXT,
    sender_id       TEXT,
    date_utc        TIMESTAMPTZ NOT NULL,
    text            TEXT,
    sender_first_name TEXT,              -- Nombre del remitente (fácil lectura)
    chat_title TEXT,                     -- Nombre del grupo/canal
    forward_from_name TEXT,              -- Origen de reenvíos (nombres)
    forward_from_id TEXT,                -- IDs de origen para trazabilidad
    text_sha1       TEXT,
    has_media       INTEGER DEFAULT 0,
    media_path      TEXT,
    raw_json        TEXT,
    ingest_ts       TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (token) REFERENCES bots(token) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_token_time ON messages(token, date_utc);
CREATE INDEX IF NOT EXISTS idx_messages_textsha1 ON messages(text_sha1);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_hasmedia ON messages(has_media);
CREATE INDEX IF NOT EXISTS idx_messages_chat_type ON messages(chat_type);
-- Constraint de Idempotencia para Mensajes
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ux_messages_identity') THEN
        ALTER TABLE messages ADD CONSTRAINT ux_messages_identity UNIQUE (token, message_id, date_utc);
    END IF;
END $$;

-- Entidades extraídas (RegEx / Heurística)
CREATE TABLE IF NOT EXISTS entities (
    id              SERIAL PRIMARY KEY,
    message_pk      INTEGER NOT NULL,
    etype           TEXT NOT NULL, -- 'ip', 'email', 'crypto_wallet', etc.
    value           TEXT NOT NULL,
    context_snippet TEXT,
    confidence      REAL DEFAULT 1.0,
    ingest_ts       TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (message_pk) REFERENCES messages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entities_type_value ON entities(etype, value);
CREATE INDEX IF NOT EXISTS idx_entities_msg ON entities(message_pk);

-- Constraint de Idempotencia para Entidades
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ux_entities_key') THEN
        ALTER TABLE entities ADD CONSTRAINT ux_entities_key UNIQUE (message_pk, etype, value);
    END IF;
END $$;

-- Adjuntos y Ficheros Exfiltrados
CREATE TABLE IF NOT EXISTS attachments (
    id              SERIAL PRIMARY KEY,
    message_pk      INTEGER NOT NULL,
    mime            TEXT,
    size            BIGINT,
    sha256          TEXT,
    path            TEXT,
    ingest_ts       TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (message_pk) REFERENCES messages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_attachments_sha256 ON attachments(sha256);
CREATE INDEX IF NOT EXISTS idx_attachments_mime ON attachments(mime);

-- ----------------------------------------------------------------------------
-- 3. THREAT INTELLIGENCE & INFRAESTRUCTURA
-- ----------------------------------------------------------------------------

-- Origen del Bot (Hash del malware dropper/config)
CREATE TABLE IF NOT EXISTS hash_origin (
    id              SERIAL PRIMARY KEY,
    token           TEXT NOT NULL,
    sample_sha256   TEXT NOT NULL,
    first_seen      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token, sample_sha256),
    FOREIGN KEY (token) REFERENCES bots(token) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_hash_origin_token ON hash_origin(token);
CREATE INDEX IF NOT EXISTS idx_hash_origin_sha ON hash_origin(sample_sha256);

-- Inteligencia de Infraestructura (IPs, ASNs de Operadores)
CREATE TABLE IF NOT EXISTS infrastructure_intelligence (
    id SERIAL PRIMARY KEY,
    indicator TEXT UNIQUE NOT NULL, -- IP o Host
    type TEXT,       -- 'HOST', 'DOMAIN'
    ip_address TEXT,
    asn TEXT,
    country_code TEXT,
    city TEXT,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ
);

-- Perfiles de Operadores (Actores Humanos)
CREATE TABLE IF NOT EXISTS operator_profiles (
    sender_id TEXT PRIMARY KEY,
    role TEXT,       -- 'COMMANDER', 'COLLECTOR'
    confidence DOUBLE PRECISION,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    msg_count INTEGER DEFAULT 0,
    command_count INTEGER DEFAULT 0,
    data_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ,
    bots_controlled INTEGER DEFAULT 0
);

-- Vinculación Operador -> Infraestructura
CREATE TABLE IF NOT EXISTS operator_infrastructure (
    sender_id TEXT NOT NULL, -- No FK estricta para permitir sender_id parciales, pero recomendable
    infra_id INTEGER NOT NULL REFERENCES infrastructure_intelligence(id) ON DELETE CASCADE,
    bot_token TEXT NOT NULL,
    UNIQUE(sender_id, infra_id, bot_token)
);

-- Inteligencia de Malware (Ficheros Droppers/Payloads)
CREATE TABLE IF NOT EXISTS samples_intelligence (
    sha256 TEXT PRIMARY KEY,
    file_type TEXT,
    origin_url TEXT,
    origin_source TEXT,
    associated_token TEXT,
    ingest_at TIMESTAMPTZ,
    imphash TEXT,
    ssdeep TEXT
);

-- Grafo de Similitud de Malware (Fuzzy Hashing)
CREATE TABLE IF NOT EXISTS malware_similarity_links (
    sha256_a TEXT NOT NULL,
    sha256_b TEXT NOT NULL,
    score INTEGER,
    method TEXT,
    detected_at TIMESTAMPTZ,
    PRIMARY KEY (sha256_a, sha256_b)
);

-- ----------------------------------------------------------------------------
-- 4. GRAFO SOCIAL Y TRÁFICO
-- ----------------------------------------------------------------------------

-- Nodos del Grafo Social (Identidades Telegram)
CREATE TABLE IF NOT EXISTS social_identities (
    telegram_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    type TEXT, -- 'user', 'channel', 'bot'
    first_seen TIMESTAMPTZ,
    risk_score INTEGER
);

-- Aristas del Grafo Social
CREATE TABLE IF NOT EXISTS social_graph_edges (
    bot_token TEXT NOT NULL,
    identity_id BIGINT NOT NULL,
    relation_type TEXT, -- 'FORWARD_FROM', 'COMMAND_BY', 'MEMBER_OF'
    message_pk INTEGER NOT NULL,
    detected_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_social_edges_bot ON social_graph_edges(bot_token);
CREATE INDEX IF NOT EXISTS idx_social_edges_identity ON social_graph_edges(identity_id);

-- Flujo de Tráfico (Para visualizaciones Sankey temporales)
CREATE TABLE IF NOT EXISTS intel_traffic_flow (
    actor_id TEXT NOT NULL,
    direction TEXT NOT NULL, -- 'INBOUND', 'OUTBOUND', 'LATERAL'
    remote_entity TEXT NOT NULL,
    remote_type TEXT,        -- 'USER', 'GROUP', 'BOT'
    via_bot_token TEXT NOT NULL,
    via_bot_name TEXT,
    volume INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_traffic_actor ON intel_traffic_flow(actor_id);

-- ----------------------------------------------------------------------------
-- 5. MONITORIZACIÓN DEFENSIVA (BREACH MONITOR)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitored_assets (
    id SERIAL PRIMARY KEY,
    asset_type TEXT NOT NULL,
    asset_value TEXT NOT NULL,
    description TEXT,
    added_utc TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT ux_monitored_asset UNIQUE (asset_type, asset_value)
);
CREATE INDEX IF NOT EXISTS idx_asset_value ON monitored_assets(asset_value);
CREATE INDEX IF NOT EXISTS idx_asset_type ON monitored_assets(asset_type);

-- ----------------------------------------------------------------------------
-- 6. MÉTRICAS AGREGADAS (ANALYTICS)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS metrics_bot_daily (
    date            DATE NOT NULL,
    token           TEXT NOT NULL,
    messages_count  INTEGER NOT NULL,
    entities_count  INTEGER NOT NULL,
    has_media_count INTEGER NOT NULL,
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    PRIMARY KEY (date, token),
    FOREIGN KEY (token) REFERENCES bots(token) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metrics_text_templates (
    text_sha1       TEXT PRIMARY KEY,
    example_text    TEXT,
    count           INTEGER NOT NULL,
    last_seen       TIMESTAMPTZ,
    tokens_sample   TEXT
);

CREATE TABLE IF NOT EXISTS metrics_language_daily (
    date            DATE NOT NULL,
    language        TEXT NOT NULL,
    count           INTEGER NOT NULL,
    PRIMARY KEY (date, language)
);
CREATE INDEX IF NOT EXISTS idx_lang_daily_lang ON metrics_language_daily(language);

CREATE TABLE IF NOT EXISTS metrics_word_daily (
    date            DATE NOT NULL,
    word            TEXT NOT NULL,
    count           INTEGER NOT NULL,
    PRIMARY KEY (date, word)
);
CREATE INDEX IF NOT EXISTS idx_word_daily_word ON metrics_word_daily(word);


CREATE TABLE IF NOT EXISTS message_intent (
    message_pk      INTEGER NOT NULL,
    label           TEXT NOT NULL,
    score           REAL NOT NULL,
    model           TEXT,
    ingest_ts       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (message_pk, label),
    FOREIGN KEY (message_pk) REFERENCES messages(id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 7. SALUD DEL SISTEMA
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_health (
    metric_name TEXT PRIMARY KEY,
    value_numeric REAL,
    value_text TEXT,
    last_updated TIMESTAMPTZ
);

-- Valores iniciales (Seed)
INSERT INTO system_health(metric_name) VALUES ('disk_total_gb') ON CONFLICT DO NOTHING;
INSERT INTO system_health(metric_name) VALUES ('disk_used_gb') ON CONFLICT DO NOTHING;
INSERT INTO system_health(metric_name) VALUES ('disk_free_gb') ON CONFLICT DO NOTHING;
INSERT INTO system_health(metric_name) VALUES ('disk_percent_used') ON CONFLICT DO NOTHING;
INSERT INTO system_health(metric_name) VALUES ('media_folder_gb') ON CONFLICT DO NOTHING;