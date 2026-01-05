-- Migración: Tablas para almacenar conversaciones y programar encuestas FAQ
-- Fecha: 2025-12-31

-- =====================================================
-- Tabla 1: conversation_logs
-- Almacena metadata de sesiones conversacionales
-- =====================================================

CREATE TABLE IF NOT EXISTS conversation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificación del huésped
    wa_id TEXT NOT NULL,
    guest_phone TEXT,
    guest_name TEXT,

    -- Timestamps de la conversación
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_bot_message_at TIMESTAMP,
    ended_at TIMESTAMP,

    -- Métricas de la conversación
    message_count INTEGER DEFAULT 0,
    bot_message_count INTEGER DEFAULT 0,
    faq_count INTEGER DEFAULT 0,

    -- Relación con tickets (si se creó uno)
    ticket_created BOOLEAN DEFAULT FALSE,
    ticket_id INTEGER,

    -- Estado de encuesta FAQ
    survey_scheduled BOOLEAN DEFAULT FALSE,
    survey_job_id TEXT,  -- ID del job de APScheduler
    survey_sent BOOLEAN DEFAULT FALSE,
    survey_sent_at TIMESTAMP,
    survey_state TEXT DEFAULT 'none',  -- 'none', 'q1_sent', 'q2_sent', 'completed'

    -- Respuestas de la encuesta FAQ
    faq_csat_score INTEGER CHECK (faq_csat_score BETWEEN 1 AND 5),
    faq_csat_comment TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ticket_id) REFERENCES Tickets(id) ON DELETE SET NULL
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_conv_logs_wa_id ON conversation_logs(wa_id);
CREATE INDEX IF NOT EXISTS idx_conv_logs_started ON conversation_logs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_logs_last_bot_msg ON conversation_logs(last_bot_message_at);
CREATE INDEX IF NOT EXISTS idx_conv_logs_survey_pending
    ON conversation_logs(survey_scheduled, survey_sent)
    WHERE survey_scheduled = TRUE AND survey_sent = FALSE;

-- =====================================================
-- Tabla 2: conversation_messages
-- Almacena cada mensaje individual de la conversación
-- =====================================================

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_log_id INTEGER NOT NULL,

    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sender TEXT NOT NULL CHECK (sender IN ('guest', 'bot')),
    message_text TEXT,

    -- Análisis de intent (solo para mensajes del huésped)
    intent TEXT,
    intent_confidence REAL,

    -- FAQ específico (solo para respuestas del bot)
    is_faq_response BOOLEAN DEFAULT FALSE,
    faq_matched_id TEXT,

    FOREIGN KEY (conversation_log_id) REFERENCES conversation_logs(id) ON DELETE CASCADE
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_conv_messages_log ON conversation_messages(conversation_log_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_timestamp ON conversation_messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conv_messages_sender ON conversation_messages(sender);

-- =====================================================
-- Comentarios informativos
-- =====================================================

-- Esta migración permite:
-- 1. Almacenar todas las conversaciones FAQ en BD
-- 2. Trackear último mensaje del bot para timer de encuesta
-- 3. Programar encuestas con APScheduler (job_id almacenado)
-- 4. Evitar spam con cooldown (verificar survey_sent_at)
-- 5. Analizar calidad de respuestas FAQ posteriormente
