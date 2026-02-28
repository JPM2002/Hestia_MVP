


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."create_csat_survey_on_ticket_resolved"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    -- Solo actuar si el estado cambió a RESUELTO
    IF NEW.estado = 'RESUELTO' AND (OLD.estado IS NULL OR OLD.estado != 'RESUELTO') THEN
        
        -- Insertar encuesta programada para 5 minutos después
        INSERT INTO csat_surveys (
            ticket_id,
            guest_phone,
            survey_state,
            scheduled_at,
            created_at
        ) VALUES (
            NEW.id,
            NEW.huesped_id,  -- El teléfono del huésped está en tickets.huesped_id
            'scheduled',
            NOW() + INTERVAL '5 minutes',  -- 5 minutos de espera
            NOW()
        )
        ON CONFLICT (ticket_id) DO NOTHING;  -- Si ya existe, no hacer nada
        
    END IF;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."create_csat_survey_on_ticket_resolved"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_assigned_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    -- Si se está asignando por primera vez (de NULL a un valor)
    IF NEW.assigned_to IS NOT NULL AND (OLD.assigned_to IS NULL OR OLD.assigned_to != NEW.assigned_to) THEN
        NEW.assigned_at = NOW();
        NEW.assignment_notif_sent = FALSE;  -- Resetear flag para nueva asignación
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_assigned_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_conversation_logs_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_conversation_logs_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_started_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.estado = 'EN_CURSO' AND (OLD.estado IS NULL OR OLD.estado != 'EN_CURSO') THEN
        NEW.started_at = NOW();
        NEW.in_progress_notif_sent = FALSE;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_started_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."FAQhistory" (
    "id" bigint NOT NULL,
    "org_id" integer,
    "hotel_id" integer,
    "guest_phone" "text" NOT NULL,
    "question_text" "text" NOT NULL,
    "answer_text" "text" NOT NULL,
    "matched_key" "text",
    "asked_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "answered_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."FAQhistory" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."FAQhistory_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."FAQhistory_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."FAQhistory_id_seq" OWNED BY "public"."FAQhistory"."id";



CREATE TABLE IF NOT EXISTS "public"."assets" (
    "id" bigint NOT NULL,
    "hotel_id" bigint NOT NULL,
    "location_id" bigint,
    "name" "text" NOT NULL,
    "category" "text",
    "serial" "text",
    "status" "text",
    "qr_code" "text",
    "created_at" timestamp without time zone DEFAULT "now"(),
    "retired_at" timestamp without time zone
);


ALTER TABLE "public"."assets" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."assets_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."assets_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."assets_id_seq" OWNED BY "public"."assets"."id";



CREATE TABLE IF NOT EXISTS "public"."conversation_logs" (
    "id" integer NOT NULL,
    "wa_id" "text" NOT NULL,
    "guest_phone" "text",
    "guest_name" "text",
    "started_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_bot_message_at" timestamp with time zone,
    "last_guest_message_at" timestamp with time zone,
    "ended_at" timestamp with time zone,
    "message_count" integer DEFAULT 0,
    "bot_message_count" integer DEFAULT 0,
    "faq_count" integer DEFAULT 0,
    "ticket_created" boolean DEFAULT false,
    "ticket_id" integer,
    "survey_scheduled" boolean DEFAULT false,
    "survey_job_id" "text",
    "survey_sent" boolean DEFAULT false,
    "survey_sent_at" timestamp with time zone,
    "survey_state" "text" DEFAULT 'none'::"text",
    "faq_csat_score" integer,
    "faq_csat_comment" "text",
    "faq_csat_completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "total_input_tokens" integer DEFAULT 0,
    "total_output_tokens" integer DEFAULT 0,
    CONSTRAINT "conversation_logs_faq_csat_score_check" CHECK ((("faq_csat_score" >= 1) AND ("faq_csat_score" <= 5))),
    CONSTRAINT "conversation_logs_survey_state_check" CHECK (("survey_state" = ANY (ARRAY['none'::"text", 'q1_sent'::"text", 'q2_sent'::"text", 'completed'::"text"])))
);


ALTER TABLE "public"."conversation_logs" OWNER TO "postgres";


COMMENT ON TABLE "public"."conversation_logs" IS 'Almacena metadata de sesiones de conversación para análisis y encuestas FAQ';



COMMENT ON COLUMN "public"."conversation_logs"."ticket_created" IS 'Si es TRUE, no enviar encuesta FAQ (ya recibirá encuesta CSAT de ticket)';



COMMENT ON COLUMN "public"."conversation_logs"."survey_job_id" IS 'ID del job de APScheduler para cancelar/reprogramar';



COMMENT ON COLUMN "public"."conversation_logs"."survey_state" IS 'Estado actual de la encuesta: none, q1_sent, q2_sent, completed';



CREATE SEQUENCE IF NOT EXISTS "public"."conversation_logs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."conversation_logs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."conversation_logs_id_seq" OWNED BY "public"."conversation_logs"."id";



CREATE TABLE IF NOT EXISTS "public"."conversation_messages" (
    "id" integer NOT NULL,
    "conversation_log_id" integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sender" "text" NOT NULL,
    "message_text" "text",
    "intent" "text",
    "intent_confidence" real,
    "is_faq_response" boolean DEFAULT false,
    "faq_matched_id" "text",
    "input_tokens" integer DEFAULT 0,
    "output_tokens" integer DEFAULT 0,
    CONSTRAINT "conversation_messages_sender_check" CHECK (("sender" = ANY (ARRAY['guest'::"text", 'bot'::"text"])))
);


ALTER TABLE "public"."conversation_messages" OWNER TO "postgres";


COMMENT ON TABLE "public"."conversation_messages" IS 'Almacena cada mensaje individual de la conversación para análisis detallado';



CREATE SEQUENCE IF NOT EXISTS "public"."conversation_messages_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."conversation_messages_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."conversation_messages_id_seq" OWNED BY "public"."conversation_messages"."id";



CREATE TABLE IF NOT EXISTS "public"."csat_surveys" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "guest_phone" "text" NOT NULL,
    "survey_state" "text" DEFAULT 'scheduled'::"text" NOT NULL,
    "csat_score" integer,
    "csat_comment" "text",
    "tool_utility_score" integer,
    "scheduled_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "guest_status" "text" DEFAULT 'active'::"text",
    "guest_checkout_date" timestamp with time zone,
    "completed_at" timestamp without time zone,
    "org_id" integer,
    "hotel_id" integer,
    "survey_started_at" timestamp without time zone,
    "survey_last_prompt_at" timestamp without time zone,
    CONSTRAINT "csat_surveys_csat_score_check" CHECK ((("csat_score" IS NULL) OR (("csat_score" >= 1) AND ("csat_score" <= 5)))),
    CONSTRAINT "csat_surveys_guest_status_check" CHECK (("guest_status" = ANY (ARRAY['active'::"text", 'checked_out'::"text", 'unknown'::"text"]))),
    CONSTRAINT "csat_surveys_tool_utility_score_check" CHECK ((("tool_utility_score" IS NULL) OR (("tool_utility_score" >= 1) AND ("tool_utility_score" <= 5))))
);


ALTER TABLE "public"."csat_surveys" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."csat_surveys_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."csat_surveys_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."csat_surveys_id_seq" OWNED BY "public"."csat_surveys"."id";



CREATE TABLE IF NOT EXISTS "public"."hotels" (
    "id" bigint NOT NULL,
    "org_id" bigint NOT NULL,
    "name" "text" NOT NULL,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."hotels" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hotels_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hotels_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hotels_id_seq" OWNED BY "public"."hotels"."id";



CREATE TABLE IF NOT EXISTS "public"."kpi_daily" (
    "id" bigint NOT NULL,
    "org_id" bigint NOT NULL,
    "hotel_id" bigint,
    "day" "date" NOT NULL,
    "open_total" integer DEFAULT 0 NOT NULL,
    "resolved_total" integer DEFAULT 0 NOT NULL,
    "sla_rate" numeric,
    "ttr_avg_min" numeric,
    "by_area" "jsonb",
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."kpi_daily" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."kpi_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."kpi_daily_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."kpi_daily_id_seq" OWNED BY "public"."kpi_daily"."id";



CREATE TABLE IF NOT EXISTS "public"."location_types" (
    "code" "text" NOT NULL,
    "name" "text" NOT NULL
);


ALTER TABLE "public"."location_types" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."locations" (
    "id" bigint NOT NULL,
    "hotel_id" bigint NOT NULL,
    "type_code" "text" NOT NULL,
    "code" "text",
    "name" "text" NOT NULL,
    "parent_id" bigint
);


ALTER TABLE "public"."locations" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."locations_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."locations_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."locations_id_seq" OWNED BY "public"."locations"."id";



CREATE TABLE IF NOT EXISTS "public"."notifications" (
    "id" bigint NOT NULL,
    "ticket_id" bigint,
    "channel" "text" NOT NULL,
    "payload" "jsonb",
    "status" "text",
    "error" "text",
    "sent_at" timestamp without time zone,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."notifications" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."notifications_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."notifications_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."notifications_id_seq" OWNED BY "public"."notifications"."id";



CREATE TABLE IF NOT EXISTS "public"."orgs" (
    "id" bigint NOT NULL,
    "name" "text" NOT NULL,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."orgs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."orgs_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."orgs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."orgs_id_seq" OWNED BY "public"."orgs"."id";



CREATE TABLE IF NOT EXISTS "public"."orguserareas" (
    "org_id" bigint NOT NULL,
    "user_id" bigint NOT NULL,
    "area_code" "text" NOT NULL
);


ALTER TABLE "public"."orguserareas" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."orgusers" (
    "id" bigint NOT NULL,
    "org_id" bigint NOT NULL,
    "user_id" bigint NOT NULL,
    "role" "text" NOT NULL,
    "default_area" "text",
    "default_hotel_id" bigint
);


ALTER TABLE "public"."orgusers" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."orgusers_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."orgusers_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."orgusers_id_seq" OWNED BY "public"."orgusers"."id";



CREATE TABLE IF NOT EXISTS "public"."permissions" (
    "code" "text" NOT NULL,
    "name" "text" NOT NULL
);


ALTER TABLE "public"."permissions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."pmsguests" (
    "id" bigint NOT NULL,
    "huesped_id" "text" NOT NULL,
    "nombre" "text" NOT NULL,
    "habitacion" "text" NOT NULL,
    "status" "text" NOT NULL,
    "checkin" timestamp without time zone,
    "checkout" timestamp without time zone
);


ALTER TABLE "public"."pmsguests" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."pmsguests_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."pmsguests_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."pmsguests_id_seq" OWNED BY "public"."pmsguests"."id";



CREATE TABLE IF NOT EXISTS "public"."rolepermissions" (
    "role_code" "text" NOT NULL,
    "perm_code" "text" NOT NULL,
    "allow" boolean DEFAULT true NOT NULL
);


ALTER TABLE "public"."rolepermissions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."roles" (
    "code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "inherits_code" "text"
);


ALTER TABLE "public"."roles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."runtime_sessions" (
    "phone" "text" NOT NULL,
    "data" "jsonb" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."runtime_sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."runtime_wamids" (
    "id" "text" NOT NULL,
    "seen_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."runtime_wamids" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."slarules" (
    "area" "text" NOT NULL,
    "prioridad" "text" NOT NULL,
    "max_minutes" integer NOT NULL,
    "org_id" bigint NOT NULL,
    "hotel_id" bigint NOT NULL
);


ALTER TABLE "public"."slarules" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ticket_approvals" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "requested_by" bigint,
    "approver_id" bigint,
    "status" "text" DEFAULT 'PENDING'::"text" NOT NULL,
    "reason" "text",
    "decided_at" timestamp without time zone,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."ticket_approvals" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."ticket_approvals_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."ticket_approvals_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."ticket_approvals_id_seq" OWNED BY "public"."ticket_approvals"."id";



CREATE TABLE IF NOT EXISTS "public"."ticket_assets" (
    "ticket_id" bigint NOT NULL,
    "asset_id" bigint NOT NULL
);


ALTER TABLE "public"."ticket_assets" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ticket_attachments" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "kind" "text",
    "url" "text" NOT NULL,
    "mime" "text",
    "size_bytes" bigint,
    "created_by" bigint,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."ticket_attachments" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."ticket_attachments_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."ticket_attachments_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."ticket_attachments_id_seq" OWNED BY "public"."ticket_attachments"."id";



CREATE TABLE IF NOT EXISTS "public"."ticket_comments" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "author_id" bigint,
    "body" "text" NOT NULL,
    "is_internal" boolean DEFAULT false NOT NULL,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."ticket_comments" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."ticket_comments_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."ticket_comments_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."ticket_comments_id_seq" OWNED BY "public"."ticket_comments"."id";



CREATE TABLE IF NOT EXISTS "public"."ticket_tag_map" (
    "ticket_id" bigint NOT NULL,
    "tag" "text" NOT NULL
);


ALTER TABLE "public"."ticket_tag_map" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ticket_tags" (
    "tag" "text" NOT NULL
);


ALTER TABLE "public"."ticket_tags" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ticket_types" (
    "code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "area" "text"
);


ALTER TABLE "public"."ticket_types" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ticket_voice_notes" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "audio_url" "text" NOT NULL,
    "transcript" "text",
    "lang" "text",
    "duration_sec" integer,
    "created_by" bigint,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."ticket_voice_notes" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."ticket_voice_notes_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."ticket_voice_notes_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."ticket_voice_notes_id_seq" OWNED BY "public"."ticket_voice_notes"."id";



CREATE TABLE IF NOT EXISTS "public"."tickethistory" (
    "id" bigint NOT NULL,
    "ticket_id" bigint NOT NULL,
    "actor_user_id" bigint,
    "action" "text" NOT NULL,
    "motivo" "text",
    "at" timestamp without time zone NOT NULL
);


ALTER TABLE "public"."tickethistory" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."tickethistory_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."tickethistory_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."tickethistory_id_seq" OWNED BY "public"."tickethistory"."id";



CREATE TABLE IF NOT EXISTS "public"."tickets" (
    "id" bigint NOT NULL,
    "org_id" bigint NOT NULL,
    "hotel_id" bigint NOT NULL,
    "area" "text" NOT NULL,
    "prioridad" "text" NOT NULL,
    "estado" "text" NOT NULL,
    "detalle" "text" NOT NULL,
    "canal_origen" "text" NOT NULL,
    "ubicacion" "text" NOT NULL,
    "huesped_id" "text",
    "created_at" timestamp without time zone NOT NULL,
    "due_at" timestamp without time zone,
    "assigned_to" bigint,
    "created_by" bigint,
    "confidence_score" numeric,
    "qr_required" boolean DEFAULT false NOT NULL,
    "accepted_at" timestamp without time zone,
    "started_at" timestamp without time zone,
    "finished_at" timestamp without time zone,
    "approved" boolean,
    "approved_by" bigint,
    "approved_at" timestamp without time zone,
    "deleted_at" timestamp without time zone,
    "deleted_by" bigint,
    "delete_reason" "text",
    "tipo" "text",
    "external_ref" "text",
    "location_id" bigint,
    "routing_source" character varying(20),
    "routing_reason" "text",
    "routing_confidence" real,
    "routing_version" character varying(10),
    "huesped_whatsapp" "text",
    "assigned_at" timestamp without time zone,
    "assignment_notif_sent" boolean DEFAULT false,
    "csat_survey_triggered" boolean DEFAULT false,
    "in_progress_notif_sent" boolean DEFAULT false
);


ALTER TABLE "public"."tickets" OWNER TO "postgres";


COMMENT ON COLUMN "public"."tickets"."started_at" IS 'Timestamp cuando el ticket pasó a estado EN_CURSO (auto-actualizado por trigger)';



COMMENT ON COLUMN "public"."tickets"."assigned_at" IS 'Timestamp cuando el ticket fue asignado a un técnico (auto-actualizado por trigger)';



COMMENT ON COLUMN "public"."tickets"."assignment_notif_sent" IS 'Flag: TRUE si se envió notificación de asignación al huésped vía WhatsApp';



COMMENT ON COLUMN "public"."tickets"."csat_survey_triggered" IS 'Flag: TRUE si se disparó encuesta CSAT cuando el ticket fue finalizado';



COMMENT ON COLUMN "public"."tickets"."in_progress_notif_sent" IS 'Flag: TRUE si se envió notificación de inicio de trabajo (EN_CURSO) vía WhatsApp';



CREATE SEQUENCE IF NOT EXISTS "public"."tickets_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."tickets_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."tickets_id_seq" OWNED BY "public"."tickets"."id";



CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" bigint NOT NULL,
    "username" "text",
    "email" "text",
    "password_hash" "text" NOT NULL,
    "role" "text" NOT NULL,
    "area" "text",
    "telefono" "text",
    "activo" boolean DEFAULT true NOT NULL,
    "is_superadmin" boolean DEFAULT false NOT NULL,
    "initialized" boolean DEFAULT false NOT NULL,
    "phone_verified" boolean DEFAULT false NOT NULL,
    "onboarding_step" character varying(32)
);


ALTER TABLE "public"."users" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."users_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."users_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."users_id_seq" OWNED BY "public"."users"."id";



CREATE TABLE IF NOT EXISTS "public"."webhooks" (
    "id" bigint NOT NULL,
    "org_id" bigint NOT NULL,
    "event" "text" NOT NULL,
    "url" "text" NOT NULL,
    "secret" "text",
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."webhooks" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."webhooks_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."webhooks_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."webhooks_id_seq" OWNED BY "public"."webhooks"."id";



ALTER TABLE ONLY "public"."FAQhistory" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."FAQhistory_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."assets" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."assets_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."conversation_logs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."conversation_logs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."conversation_messages" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."conversation_messages_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."csat_surveys" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."csat_surveys_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hotels" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hotels_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."kpi_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."kpi_daily_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."locations" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."locations_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."notifications" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."notifications_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."orgs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."orgs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."orgusers" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."orgusers_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."pmsguests" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."pmsguests_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."ticket_approvals" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."ticket_approvals_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."ticket_attachments" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."ticket_attachments_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."ticket_comments" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."ticket_comments_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."ticket_voice_notes" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."ticket_voice_notes_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."tickethistory" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."tickethistory_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."tickets" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."tickets_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."users" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."users_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."webhooks" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."webhooks_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."FAQhistory"
    ADD CONSTRAINT "FAQhistory_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."assets"
    ADD CONSTRAINT "assets_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."conversation_logs"
    ADD CONSTRAINT "conversation_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."csat_surveys"
    ADD CONSTRAINT "csat_surveys_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."csat_surveys"
    ADD CONSTRAINT "csat_surveys_ticket_id_key" UNIQUE ("ticket_id");



ALTER TABLE ONLY "public"."hotels"
    ADD CONSTRAINT "hotels_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."kpi_daily"
    ADD CONSTRAINT "kpi_daily_org_id_hotel_id_day_key" UNIQUE ("org_id", "hotel_id", "day");



ALTER TABLE ONLY "public"."kpi_daily"
    ADD CONSTRAINT "kpi_daily_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."location_types"
    ADD CONSTRAINT "location_types_pkey" PRIMARY KEY ("code");



ALTER TABLE ONLY "public"."locations"
    ADD CONSTRAINT "locations_hotel_id_type_code_code_key" UNIQUE ("hotel_id", "type_code", "code");



ALTER TABLE ONLY "public"."locations"
    ADD CONSTRAINT "locations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."orgs"
    ADD CONSTRAINT "orgs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."orguserareas"
    ADD CONSTRAINT "orguserareas_pkey" PRIMARY KEY ("org_id", "user_id", "area_code");



ALTER TABLE ONLY "public"."orgusers"
    ADD CONSTRAINT "orgusers_org_id_user_id_key" UNIQUE ("org_id", "user_id");



ALTER TABLE ONLY "public"."orgusers"
    ADD CONSTRAINT "orgusers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."permissions"
    ADD CONSTRAINT "permissions_pkey" PRIMARY KEY ("code");



ALTER TABLE ONLY "public"."pmsguests"
    ADD CONSTRAINT "pmsguests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rolepermissions"
    ADD CONSTRAINT "rolepermissions_pkey" PRIMARY KEY ("role_code", "perm_code");



ALTER TABLE ONLY "public"."roles"
    ADD CONSTRAINT "roles_pkey" PRIMARY KEY ("code");



ALTER TABLE ONLY "public"."runtime_sessions"
    ADD CONSTRAINT "runtime_sessions_pkey" PRIMARY KEY ("phone");



ALTER TABLE ONLY "public"."runtime_wamids"
    ADD CONSTRAINT "runtime_wamids_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."slarules"
    ADD CONSTRAINT "slarules_pkey" PRIMARY KEY ("area", "prioridad", "org_id", "hotel_id");



ALTER TABLE ONLY "public"."ticket_approvals"
    ADD CONSTRAINT "ticket_approvals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ticket_assets"
    ADD CONSTRAINT "ticket_assets_pkey" PRIMARY KEY ("ticket_id", "asset_id");



ALTER TABLE ONLY "public"."ticket_attachments"
    ADD CONSTRAINT "ticket_attachments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ticket_comments"
    ADD CONSTRAINT "ticket_comments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ticket_tag_map"
    ADD CONSTRAINT "ticket_tag_map_pkey" PRIMARY KEY ("ticket_id", "tag");



ALTER TABLE ONLY "public"."ticket_tags"
    ADD CONSTRAINT "ticket_tags_pkey" PRIMARY KEY ("tag");



ALTER TABLE ONLY "public"."ticket_types"
    ADD CONSTRAINT "ticket_types_pkey" PRIMARY KEY ("code");



ALTER TABLE ONLY "public"."ticket_voice_notes"
    ADD CONSTRAINT "ticket_voice_notes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tickethistory"
    ADD CONSTRAINT "tickethistory_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_username_key" UNIQUE ("username");



ALTER TABLE ONLY "public"."webhooks"
    ADD CONSTRAINT "webhooks_pkey" PRIMARY KEY ("id");



CREATE INDEX "FAQhistory_org_hotel_time_idx" ON "public"."FAQhistory" USING "btree" ("org_id", "hotel_id", "asked_at" DESC);



CREATE INDEX "idx_conv_logs_last_bot_msg" ON "public"."conversation_logs" USING "btree" ("last_bot_message_at");



CREATE INDEX "idx_conv_logs_started" ON "public"."conversation_logs" USING "btree" ("started_at" DESC);



CREATE INDEX "idx_conv_logs_survey_pending" ON "public"."conversation_logs" USING "btree" ("survey_scheduled", "survey_sent") WHERE (("survey_scheduled" = true) AND ("survey_sent" = false));



CREATE INDEX "idx_conv_logs_survey_state" ON "public"."conversation_logs" USING "btree" ("survey_state");



CREATE INDEX "idx_conv_logs_wa_id" ON "public"."conversation_logs" USING "btree" ("wa_id");



CREATE INDEX "idx_conv_messages_log" ON "public"."conversation_messages" USING "btree" ("conversation_log_id");



CREATE INDEX "idx_conv_messages_sender" ON "public"."conversation_messages" USING "btree" ("sender");



CREATE INDEX "idx_conv_messages_timestamp" ON "public"."conversation_messages" USING "btree" ("timestamp" DESC);



CREATE INDEX "idx_conversation_logs_faq_survey" ON "public"."conversation_logs" USING "btree" ("survey_sent", "created_at") WHERE (("survey_sent" = false) OR ("survey_sent" IS NULL));



CREATE INDEX "idx_sla_scope" ON "public"."slarules" USING "btree" ("org_id", "hotel_id", "area", "prioridad");



CREATE INDEX "idx_ticket_history_ticket" ON "public"."tickethistory" USING "btree" ("ticket_id");



CREATE INDEX "idx_tickets_assigned" ON "public"."tickets" USING "btree" ("assigned_to");



CREATE INDEX "idx_tickets_assigned_notif" ON "public"."tickets" USING "btree" ("assigned_at", "assignment_notif_sent") WHERE (("assigned_to" IS NOT NULL) AND (("assignment_notif_sent" IS NULL) OR ("assignment_notif_sent" = false)));



CREATE INDEX "idx_tickets_created" ON "public"."tickets" USING "btree" ("created_at");



CREATE INDEX "idx_tickets_critical" ON "public"."tickets" USING "btree" ("due_at") WHERE (("estado" = ANY (ARRAY['PENDIENTE'::"text", 'ASIGNADO'::"text", 'ACEPTADO'::"text", 'EN_CURSO'::"text", 'PAUSADO'::"text", 'DERIVADO'::"text"])) AND ("due_at" IS NOT NULL));



CREATE INDEX "idx_tickets_estado_area" ON "public"."tickets" USING "btree" ("estado", "area");



CREATE INDEX "idx_tickets_finished_csat" ON "public"."tickets" USING "btree" ("finished_at", "csat_survey_triggered") WHERE (("finished_at" IS NOT NULL) AND (("csat_survey_triggered" IS NULL) OR ("csat_survey_triggered" = false)));



CREATE INDEX "idx_tickets_guest_fields" ON "public"."tickets" USING "btree" ("ubicacion", "huesped_id");



CREATE INDEX "idx_tickets_hotel_created_desc" ON "public"."tickets" USING "btree" ("hotel_id", "created_at" DESC);



CREATE INDEX "idx_tickets_in_progress_notif" ON "public"."tickets" USING "btree" ("started_at", "in_progress_notif_sent") WHERE (("estado" = 'EN_CURSO'::"text") AND (("in_progress_notif_sent" IS NULL) OR ("in_progress_notif_sent" = false)));



CREATE INDEX "idx_tickets_scope" ON "public"."tickets" USING "btree" ("org_id", "hotel_id");



CREATE INDEX "idx_tickets_state" ON "public"."tickets" USING "btree" ("estado");



CREATE OR REPLACE TRIGGER "trg_conversation_logs_updated_at" BEFORE UPDATE ON "public"."conversation_logs" FOR EACH ROW EXECUTE FUNCTION "public"."update_conversation_logs_updated_at"();



CREATE OR REPLACE TRIGGER "trg_tickets_assigned_at" BEFORE UPDATE OF "assigned_to" ON "public"."tickets" FOR EACH ROW EXECUTE FUNCTION "public"."update_assigned_at"();



CREATE OR REPLACE TRIGGER "trg_tickets_started_at" BEFORE UPDATE OF "estado" ON "public"."tickets" FOR EACH ROW EXECUTE FUNCTION "public"."update_started_at"();



CREATE OR REPLACE TRIGGER "trigger_create_csat_on_ticket_resolved" AFTER UPDATE ON "public"."tickets" FOR EACH ROW WHEN (("new"."estado" = 'RESUELTO'::"text")) EXECUTE FUNCTION "public"."create_csat_survey_on_ticket_resolved"();



CREATE OR REPLACE TRIGGER "update_conversation_logs_updated_at" BEFORE UPDATE ON "public"."conversation_logs" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."assets"
    ADD CONSTRAINT "assets_hotel_id_fkey" FOREIGN KEY ("hotel_id") REFERENCES "public"."hotels"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."assets"
    ADD CONSTRAINT "assets_location_id_fkey" FOREIGN KEY ("location_id") REFERENCES "public"."locations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."conversation_logs"
    ADD CONSTRAINT "conversation_logs_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_conversation_log_id_fkey" FOREIGN KEY ("conversation_log_id") REFERENCES "public"."conversation_logs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."csat_surveys"
    ADD CONSTRAINT "csat_surveys_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hotels"
    ADD CONSTRAINT "hotels_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."kpi_daily"
    ADD CONSTRAINT "kpi_daily_hotel_id_fkey" FOREIGN KEY ("hotel_id") REFERENCES "public"."hotels"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."kpi_daily"
    ADD CONSTRAINT "kpi_daily_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."locations"
    ADD CONSTRAINT "locations_hotel_id_fkey" FOREIGN KEY ("hotel_id") REFERENCES "public"."hotels"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."locations"
    ADD CONSTRAINT "locations_parent_id_fkey" FOREIGN KEY ("parent_id") REFERENCES "public"."locations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."locations"
    ADD CONSTRAINT "locations_type_code_fkey" FOREIGN KEY ("type_code") REFERENCES "public"."location_types"("code");



ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orguserareas"
    ADD CONSTRAINT "orguserareas_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orguserareas"
    ADD CONSTRAINT "orguserareas_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orgusers"
    ADD CONSTRAINT "orgusers_default_hotel_id_fkey" FOREIGN KEY ("default_hotel_id") REFERENCES "public"."hotels"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."orgusers"
    ADD CONSTRAINT "orgusers_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orgusers"
    ADD CONSTRAINT "orgusers_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."rolepermissions"
    ADD CONSTRAINT "rolepermissions_perm_code_fkey" FOREIGN KEY ("perm_code") REFERENCES "public"."permissions"("code") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."rolepermissions"
    ADD CONSTRAINT "rolepermissions_role_code_fkey" FOREIGN KEY ("role_code") REFERENCES "public"."roles"("code") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."roles"
    ADD CONSTRAINT "roles_inherits_code_fkey" FOREIGN KEY ("inherits_code") REFERENCES "public"."roles"("code");



ALTER TABLE ONLY "public"."slarules"
    ADD CONSTRAINT "slarules_hotel_id_fkey" FOREIGN KEY ("hotel_id") REFERENCES "public"."hotels"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."slarules"
    ADD CONSTRAINT "slarules_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_approvals"
    ADD CONSTRAINT "ticket_approvals_approver_id_fkey" FOREIGN KEY ("approver_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."ticket_approvals"
    ADD CONSTRAINT "ticket_approvals_requested_by_fkey" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."ticket_approvals"
    ADD CONSTRAINT "ticket_approvals_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_assets"
    ADD CONSTRAINT "ticket_assets_asset_id_fkey" FOREIGN KEY ("asset_id") REFERENCES "public"."assets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_assets"
    ADD CONSTRAINT "ticket_assets_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_attachments"
    ADD CONSTRAINT "ticket_attachments_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."ticket_attachments"
    ADD CONSTRAINT "ticket_attachments_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_comments"
    ADD CONSTRAINT "ticket_comments_author_id_fkey" FOREIGN KEY ("author_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."ticket_comments"
    ADD CONSTRAINT "ticket_comments_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_tag_map"
    ADD CONSTRAINT "ticket_tag_map_tag_fkey" FOREIGN KEY ("tag") REFERENCES "public"."ticket_tags"("tag") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_tag_map"
    ADD CONSTRAINT "ticket_tag_map_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ticket_voice_notes"
    ADD CONSTRAINT "ticket_voice_notes_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."ticket_voice_notes"
    ADD CONSTRAINT "ticket_voice_notes_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tickethistory"
    ADD CONSTRAINT "tickethistory_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."tickethistory"
    ADD CONSTRAINT "tickethistory_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "public"."tickets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_approved_by_fkey" FOREIGN KEY ("approved_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_hotel_id_fkey" FOREIGN KEY ("hotel_id") REFERENCES "public"."hotels"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_location_id_fkey" FOREIGN KEY ("location_id") REFERENCES "public"."locations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."tickets"
    ADD CONSTRAINT "tickets_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."webhooks"
    ADD CONSTRAINT "webhooks_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE CASCADE;





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

























































































































































GRANT ALL ON FUNCTION "public"."create_csat_survey_on_ticket_resolved"() TO "anon";
GRANT ALL ON FUNCTION "public"."create_csat_survey_on_ticket_resolved"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."create_csat_survey_on_ticket_resolved"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_assigned_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_assigned_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_assigned_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_conversation_logs_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_conversation_logs_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_conversation_logs_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_started_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_started_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_started_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";


















GRANT ALL ON TABLE "public"."FAQhistory" TO "anon";
GRANT ALL ON TABLE "public"."FAQhistory" TO "authenticated";
GRANT ALL ON TABLE "public"."FAQhistory" TO "service_role";



GRANT ALL ON SEQUENCE "public"."FAQhistory_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."FAQhistory_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."FAQhistory_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."assets" TO "anon";
GRANT ALL ON TABLE "public"."assets" TO "authenticated";
GRANT ALL ON TABLE "public"."assets" TO "service_role";



GRANT ALL ON SEQUENCE "public"."assets_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."assets_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."assets_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."conversation_logs" TO "anon";
GRANT ALL ON TABLE "public"."conversation_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."conversation_logs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."conversation_logs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."conversation_logs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."conversation_logs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."conversation_messages" TO "anon";
GRANT ALL ON TABLE "public"."conversation_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."conversation_messages" TO "service_role";



GRANT ALL ON SEQUENCE "public"."conversation_messages_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."conversation_messages_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."conversation_messages_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."csat_surveys" TO "anon";
GRANT ALL ON TABLE "public"."csat_surveys" TO "authenticated";
GRANT ALL ON TABLE "public"."csat_surveys" TO "service_role";



GRANT ALL ON SEQUENCE "public"."csat_surveys_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."csat_surveys_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."csat_surveys_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hotels" TO "anon";
GRANT ALL ON TABLE "public"."hotels" TO "authenticated";
GRANT ALL ON TABLE "public"."hotels" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hotels_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hotels_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hotels_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."kpi_daily" TO "anon";
GRANT ALL ON TABLE "public"."kpi_daily" TO "authenticated";
GRANT ALL ON TABLE "public"."kpi_daily" TO "service_role";



GRANT ALL ON SEQUENCE "public"."kpi_daily_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."kpi_daily_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."kpi_daily_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."location_types" TO "anon";
GRANT ALL ON TABLE "public"."location_types" TO "authenticated";
GRANT ALL ON TABLE "public"."location_types" TO "service_role";



GRANT ALL ON TABLE "public"."locations" TO "anon";
GRANT ALL ON TABLE "public"."locations" TO "authenticated";
GRANT ALL ON TABLE "public"."locations" TO "service_role";



GRANT ALL ON SEQUENCE "public"."locations_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."locations_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."locations_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."notifications" TO "anon";
GRANT ALL ON TABLE "public"."notifications" TO "authenticated";
GRANT ALL ON TABLE "public"."notifications" TO "service_role";



GRANT ALL ON SEQUENCE "public"."notifications_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."notifications_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."notifications_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."orgs" TO "anon";
GRANT ALL ON TABLE "public"."orgs" TO "authenticated";
GRANT ALL ON TABLE "public"."orgs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."orgs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."orgs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."orgs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."orguserareas" TO "anon";
GRANT ALL ON TABLE "public"."orguserareas" TO "authenticated";
GRANT ALL ON TABLE "public"."orguserareas" TO "service_role";



GRANT ALL ON TABLE "public"."orgusers" TO "anon";
GRANT ALL ON TABLE "public"."orgusers" TO "authenticated";
GRANT ALL ON TABLE "public"."orgusers" TO "service_role";



GRANT ALL ON SEQUENCE "public"."orgusers_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."orgusers_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."orgusers_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."permissions" TO "anon";
GRANT ALL ON TABLE "public"."permissions" TO "authenticated";
GRANT ALL ON TABLE "public"."permissions" TO "service_role";



GRANT ALL ON TABLE "public"."pmsguests" TO "anon";
GRANT ALL ON TABLE "public"."pmsguests" TO "authenticated";
GRANT ALL ON TABLE "public"."pmsguests" TO "service_role";



GRANT ALL ON SEQUENCE "public"."pmsguests_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."pmsguests_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."pmsguests_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."rolepermissions" TO "anon";
GRANT ALL ON TABLE "public"."rolepermissions" TO "authenticated";
GRANT ALL ON TABLE "public"."rolepermissions" TO "service_role";



GRANT ALL ON TABLE "public"."roles" TO "anon";
GRANT ALL ON TABLE "public"."roles" TO "authenticated";
GRANT ALL ON TABLE "public"."roles" TO "service_role";



GRANT ALL ON TABLE "public"."runtime_sessions" TO "anon";
GRANT ALL ON TABLE "public"."runtime_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."runtime_sessions" TO "service_role";



GRANT ALL ON TABLE "public"."runtime_wamids" TO "anon";
GRANT ALL ON TABLE "public"."runtime_wamids" TO "authenticated";
GRANT ALL ON TABLE "public"."runtime_wamids" TO "service_role";



GRANT ALL ON TABLE "public"."slarules" TO "anon";
GRANT ALL ON TABLE "public"."slarules" TO "authenticated";
GRANT ALL ON TABLE "public"."slarules" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_approvals" TO "anon";
GRANT ALL ON TABLE "public"."ticket_approvals" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_approvals" TO "service_role";



GRANT ALL ON SEQUENCE "public"."ticket_approvals_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."ticket_approvals_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."ticket_approvals_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_assets" TO "anon";
GRANT ALL ON TABLE "public"."ticket_assets" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_assets" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_attachments" TO "anon";
GRANT ALL ON TABLE "public"."ticket_attachments" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_attachments" TO "service_role";



GRANT ALL ON SEQUENCE "public"."ticket_attachments_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."ticket_attachments_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."ticket_attachments_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_comments" TO "anon";
GRANT ALL ON TABLE "public"."ticket_comments" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_comments" TO "service_role";



GRANT ALL ON SEQUENCE "public"."ticket_comments_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."ticket_comments_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."ticket_comments_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_tag_map" TO "anon";
GRANT ALL ON TABLE "public"."ticket_tag_map" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_tag_map" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_tags" TO "anon";
GRANT ALL ON TABLE "public"."ticket_tags" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_tags" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_types" TO "anon";
GRANT ALL ON TABLE "public"."ticket_types" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_types" TO "service_role";



GRANT ALL ON TABLE "public"."ticket_voice_notes" TO "anon";
GRANT ALL ON TABLE "public"."ticket_voice_notes" TO "authenticated";
GRANT ALL ON TABLE "public"."ticket_voice_notes" TO "service_role";



GRANT ALL ON SEQUENCE "public"."ticket_voice_notes_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."ticket_voice_notes_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."ticket_voice_notes_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."tickethistory" TO "anon";
GRANT ALL ON TABLE "public"."tickethistory" TO "authenticated";
GRANT ALL ON TABLE "public"."tickethistory" TO "service_role";



GRANT ALL ON SEQUENCE "public"."tickethistory_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."tickethistory_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."tickethistory_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."tickets" TO "anon";
GRANT ALL ON TABLE "public"."tickets" TO "authenticated";
GRANT ALL ON TABLE "public"."tickets" TO "service_role";



GRANT ALL ON SEQUENCE "public"."tickets_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."tickets_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."tickets_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";



GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."webhooks" TO "anon";
GRANT ALL ON TABLE "public"."webhooks" TO "authenticated";
GRANT ALL ON TABLE "public"."webhooks" TO "service_role";



GRANT ALL ON SEQUENCE "public"."webhooks_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."webhooks_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."webhooks_id_seq" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































drop extension if exists "pg_net";


