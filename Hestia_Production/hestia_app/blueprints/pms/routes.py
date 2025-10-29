from flask import request, jsonify
from . import bp
from ...services.db import fetchone  # hestia_app/blueprints/pms -> hestia_app/services

# ---------------------------- PMS (read) ----------------------------
@bp.get("/pms/guest")
def pms_guest():
    """Validación simple: /pms/guest?room=1203"""
    room = request.args.get("room")
    if not room:
        return jsonify({"error": "missing room"}), 400

    row = fetchone(
        "SELECT huesped_id, nombre, habitacion, status "
        "FROM PMSGuests "
        "WHERE habitacion=? AND status='IN_HOUSE'",
        (room,),
    )
    if not row:
        return jsonify({"found": False})

    return jsonify({
        "found": True,
        "huesped_id": row["huesped_id"],
        "nombre": row["nombre"],
        "habitacion": row["habitacion"],
    })
