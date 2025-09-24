import os
import re
import sqlite3 as sql
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from flask import Flask, jsonify, request, send_from_directory, render_template

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "hestia_V2.db")
DEFAULT_ORG_ID = int(os.getenv("DEFAULT_ORG_ID", "1"))       # <- set these to scope tickets
DEFAULT_HOTEL_ID = int(os.getenv("DEFAULT_HOTEL_ID", "1"))

STT_BACKEND = os.getenv("STT_BACKEND", "local")              # 'local' (faster-whisper). You can add 'openai' later.
STT_MODEL = os.getenv("STT_MODEL", "small")                  # tiny|base|small|medium|large-v3 etc.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "es")               # Spanish by default
COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8")         # int8/int8_float16/float16 depending on CPU/GPU

# -----------------------------------------------------------------------------
# Flask
# -----------------------------------------------------------------------------
app = Flask(__name__)

# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------
def db():
    conn = sql.connect(DB_PATH)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def fetchone(q: str, params=()):
    with db() as conn:
        cur = conn.execute(q, params)
        return cur.fetchone()

def execute(q: str, params=()):
    with db() as conn:
        conn.execute(q, params)
        conn.commit()

def sla_minutes(area: str, prioridad: str) -> Optional[int]:
    row = fetchone("SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?", (area, prioridad))
    return int(row["max_minutes"]) if row else None

def compute_due(created_at: datetime, area: str, prioridad: str) -> Optional[str]:
    mins = sla_minutes(area, prioridad)
    if not mins:
        return None
    return (created_at + timedelta(minutes=mins)).isoformat(timespec="seconds")

# -----------------------------------------------------------------------------
# STT (local faster-whisper)
# -----------------------------------------------------------------------------
_fw_model = None
_fw_ready_error = None

def _load_fw():
    """Lazy-load faster-whisper to speed app boot."""
    global _fw_model, _fw_ready_error
    if _fw_model is not None or _fw_ready_error:
        return
    try:
        # Import here so you can still run the app without the package installed
        from faster_whisper import WhisperModel
        _fw_model = WhisperModel(STT_MODEL, device="cpu", compute_type=COMPUTE_TYPE)
    except Exception as e:
        _fw_ready_error = f"faster-whisper not available: {e}"

def stt_local_whisper(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribe with faster-whisper.
    Returns (text, error).
    """
    _load_fw()
    if _fw_ready_error:
        return None, _fw_ready_error
    try:
        # language hints & VAD to improve results with noisy recordings
        segments, info = _fw_model.transcribe(
            file_path,
            language=STT_LANGUAGE,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=200),
            beam_size=5
        )
        text_parts = []
        for seg in segments:
            if seg.text:
                text_parts.append(seg.text.strip())
        text = " ".join(text_parts).strip()
        return (text if text else None), (None if text else "No se detectó voz en el audio.")
    except Exception as e:
        return None, f"Error transcribiendo: {e}"

# -----------------------------------------------------------------------------
# Lightweight NLU (Spanish heuristics)
# -----------------------------------------------------------------------------
AREA_KEYWORDS = {
    "HOUSEKEEPING": [
        "toalla", "toallas", "sábana", "sabanas", "bata", "batas",
        "limpieza", "aseo", "papel", "basura", "servicio de limpieza"
    ],
    "MANTENCION": [
        "aire", "ac", "luz", "foco", "focos", "bombilla", "enchufe", "cortocircuito",
        "fuga", "agua", "filtración", "llave", "puerta", "cerradura", "pestillo",
        "ventilación", "ventilacion", "calefacción", "calefaccion", "ducha", "grif",
        "televisor", "tv", "nevera", "minibar"
    ],
    "ROOMSERVICE": [
        "room service", "roomservice", "comida", "bebida", "desayuno", "almuerzo",
        "cena", "pedido", "café", "cafe", "sándwich", "sandwich", "postre", "vino", "cerveza"
    ],
    "RECEPCION": [
        "taxi", "transporte", "consulta", "pregunta", "check-in", "check in", "checkin",
        "checkout", "check-out", "late checkout", "late check out", "reserva", "confirmación"
    ],
}

LOCATION_WORDS = [
    "lobby", "recepción", "recepcion", "piscina", "gimnasio",
    "spa", "restaurante", "bar", "pasillo", "ascensor", "elevador"
]

PRIORITY_URG = [
    "urgente", "inmediato", "inmediatamente", "ahora mismo", "inundación", "inundacion",
    "fuga", "sin luz", "peligro", "riesgo", "emergencia"
]
PRIORITY_ALTA = [
    "rápido", "rapido", "pronto", "lo antes posible", "muy pronto", "hoy"
]
PRIORITY_BAJA = [
    "cuando pueda", "no urgente", "mañana", "manana", "sin apuro", "más tarde", "mas tarde"
]

ROOM_REGEX = re.compile(r"\b(?:hab(?:\.|itacion|itación)?\s*)?(\d{3,4})\b", re.IGNORECASE)

def detect_area(text: str) -> Tuple[str, float]:
    t = text.lower()
    scores = {k: 0 for k in AREA_KEYWORDS.keys()}
    for area, kws in AREA_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                scores[area] += 1
    # default bucket if nothing matches: Mantención (most common)
    best_area = max(scores, key=lambda k: scores[k])
    conf = 0.5 + min(scores[best_area], 5) * 0.1 if scores[best_area] > 0 else 0.4
    if all(v == 0 for v in scores.values()):
        best_area = "MANTENCION"
    return best_area, min(conf, 0.95)

def detect_priority(text: str) -> Tuple[str, float]:
    t = text.lower()
    if any(kw in t for kw in PRIORITY_URG):
        return "URGENTE", 0.9
    if any(kw in t for kw in PRIORITY_ALTA):
        return "ALTA", 0.8
    if any(kw in t for kw in PRIORITY_BAJA):
        return "BAJA", 0.7
    return "MEDIA", 0.6

def detect_location(text: str) -> Optional[str]:
    t = text.lower()
    m = ROOM_REGEX.search(t)
    if m:
        return m.group(1)
    for w in LOCATION_WORDS:
        if w in t:
            # allow variants like "pasillo 2F"
            # try to capture word + trailing token
            patt = re.compile(rf"{w}\s*\w*", re.IGNORECASE)
            m2 = patt.search(text)
            return m2.group(0) if m2 else w
    return None

def extract_fields(text: str) -> Dict[str, Any]:
    area, a_conf = detect_area(text)
    prioridad, p_conf = detect_priority(text)
    ubicacion = detect_location(text)
    detalle = text.strip()
    conf = round((a_conf + p_conf + (0.8 if ubicacion else 0.6)) / 3.0, 2)
    return {
        "area": area,
        "prioridad": prioridad,
        "ubicacion": ubicacion or "",
        "detalle": detalle,
        "canal_origen": "recepcion",
        "confidence_score": conf
    }

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/voice")
def voice_page():
    return render_template("voice_ticket.html")

@app.post("/api/stt")
def api_stt():
    """
    Multipart form: audio=<file>
    Returns: { text: "..."} or { error: "..." }
    """
    if "audio" not in request.files:
        return jsonify({"error": "Falta el archivo 'audio'"}), 400
    f = request.files["audio"]
    if not f or f.filename == "":
        return jsonify({"error": "Archivo inválido"}), 400

    # Persist to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(f.filename)[1] or ".webm") as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        if STT_BACKEND == "local":
            text, err = stt_local_whisper(tmp_path)
        else:
            # Placeholder for other backends (e.g. OpenAI). Add here if you wish.
            text, err = None, "STT_BACKEND no soportado en este ejemplo. Use 'local'."

        if err:
            return jsonify({"error": err}), 500
        return jsonify({"text": text or ""})
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

@app.post("/api/extract")
def api_extract():
    """
    JSON: { text: "..." }
    Returns: { fields: { area, prioridad, ubicacion, detalle, canal_origen, confidence_score } }
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Texto vacío"}), 400
    fields = extract_fields(text)
    return jsonify({"fields": fields})

@app.post("/api/submit")
def api_submit():
    """
    JSON:
    {
      area, prioridad, ubicacion, detalle,
      canal_origen, qr_required (0/1), huesped_id, confidence_score
    }
    Writes into Tickets with DEFAULT_ORG_ID / DEFAULT_HOTEL_ID.
    """
    data = request.get_json(silent=True) or {}

    # Minimal validation
    area = data.get("area") or "MANTENCION"
    prioridad = data.get("prioridad") or "MEDIA"
    detalle = (data.get("detalle") or "").strip()
    ubicacion = (data.get("ubicacion") or "").strip() or "Lobby"
    canal = data.get("canal_origen") or "recepcion"
    qr_required = int(1 if data.get("qr_required") else 0)
    huesped_id = data.get("huesped_id")
    confidence_score = float(data.get("confidence_score") or 0.7)

    if not detalle:
        return jsonify({"error": "Detalle es requerido"}), 400

    # Scope check
    if not DEFAULT_ORG_ID or not DEFAULT_HOTEL_ID:
        return jsonify({"error": "DEFAULT_ORG_ID/DEFAULT_HOTEL_ID no configurados"}), 500

    created_at = datetime.now()
    due_at = compute_due(created_at, area, prioridad)

    try:
        with db() as conn:
            cur = conn.execute("""
                INSERT INTO Tickets(
                  org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion,
                  huesped_id, created_at, due_at, assigned_to, created_by, confidence_score,
                  qr_required, accepted_at, started_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                DEFAULT_ORG_ID, DEFAULT_HOTEL_ID, area, prioridad, "PENDIENTE", detalle, canal, ubicacion,
                huesped_id, created_at.isoformat(timespec="seconds"), due_at, None, None, confidence_score,
                qr_required, None, None, None
            ))
            ticket_id = cur.lastrowid

            conn.execute("""
                INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
                VALUES(?,?,?,?,?)
            """, (ticket_id, None, "CREADO", None, created_at.isoformat(timespec="seconds")))

        return jsonify({"ok": True, "ticket_id": ticket_id})
    except Exception as e:
        return jsonify({"error": f"DB error: {e}"}), 500

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"DB: {DB_PATH} | ORG={DEFAULT_ORG_ID} HOTEL={DEFAULT_HOTEL_ID}")
    print(f"STT: backend={STT_BACKEND} model={STT_MODEL} lang={STT_LANGUAGE} compute={COMPUTE_TYPE}")
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5001")), debug=True)
