-- Migración: Tabla para encuestas CSAT de tickets resueltos
-- Fecha: 2025-01-05
-- Propósito: Almacenar encuestas CSAT enviadas a huéspedes después de resolver tickets

-- =====================================================
-- Tabla: csat_surveys
-- Almacena encuestas de satisfacción (CSAT) de tickets
-- =====================================================

CREATE TABLE IF NOT EXISTS csat_surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Relación con ticket y huésped
    ticket_id INTEGER NOT NULL,
    guest_phone TEXT NOT NULL,
    org_id INTEGER NOT NULL,
    hotel_id INTEGER NOT NULL,

    -- Estado de la encuesta
    survey_state TEXT NOT NULL DEFAULT 'pending' CHECK (
        survey_state IN (
            'pending',      -- Programada pero no enviada
            'q1_sent',      -- Pregunta 1 (CSAT) enviada
            'q2_sent',      -- Pregunta 2 (comentario) enviada
            'q3_sent',      -- Pregunta 3 (utilidad WhatsApp) enviada
            'completed',    -- Encuesta completada
            'expired',      -- Expiró sin completar
            'cancelled'     -- Cancelada
        )
    ),

    -- Estado del huésped
    guest_status TEXT DEFAULT 'active' CHECK (
        guest_status IN ('active', 'inactive', 'blocked')
    ),

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scheduled_at TIMESTAMP,          -- Cuándo se programó enviar
    survey_started_at TIMESTAMP,     -- Cuándo se envió Q1
    survey_completed_at TIMESTAMP,   -- Cuándo se completó
    expires_at TIMESTAMP,            -- Cuándo expira la encuesta

    -- Respuestas de la encuesta
    q1_csat_score INTEGER CHECK (q1_csat_score BETWEEN 1 AND 5),  -- Satisfacción con el servicio
    q1_answered_at TIMESTAMP,

    q2_comment TEXT,                 -- Comentario (qué mejorar / qué gustó)
    q2_answered_at TIMESTAMP,

    q3_whatsapp_usefulness INTEGER CHECK (q3_whatsapp_usefulness BETWEEN 1 AND 5),  -- Utilidad de WhatsApp
    q3_answered_at TIMESTAMP,

    -- Metadata
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE
);

-- Índices para performance y consultas comunes
CREATE INDEX IF NOT EXISTS idx_csat_ticket ON csat_surveys(ticket_id);
CREATE INDEX IF NOT EXISTS idx_csat_guest_phone ON csat_surveys(guest_phone);
CREATE INDEX IF NOT EXISTS idx_csat_state ON csat_surveys(survey_state);
CREATE INDEX IF NOT EXISTS idx_csat_created ON csat_surveys(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_csat_org_hotel ON csat_surveys(org_id, hotel_id);

-- Índice para encontrar encuestas pendientes de envío
CREATE INDEX IF NOT EXISTS idx_csat_pending
    ON csat_surveys(survey_state, scheduled_at)
    WHERE survey_state = 'pending';

-- Índice para reportes de satisfacción (solo encuestas completadas)
CREATE INDEX IF NOT EXISTS idx_csat_completed
    ON csat_surveys(org_id, hotel_id, q1_csat_score)
    WHERE survey_state = 'completed' AND q1_csat_score IS NOT NULL;

-- =====================================================
-- Comentarios informativos
-- =====================================================

-- Esta migración permite:
-- 1. Almacenar encuestas CSAT después de resolver tickets
-- 2. Trackear el estado de cada encuesta (pendiente, enviada, completada)
-- 3. Almacenar las 3 respuestas: CSAT score, comentario, utilidad WhatsApp
-- 4. Prevenir duplicados (un ticket solo debe tener una encuesta CSAT)
-- 5. Generar reportes de satisfacción por org/hotel
-- 6. Implementar expiración de encuestas no completadas
