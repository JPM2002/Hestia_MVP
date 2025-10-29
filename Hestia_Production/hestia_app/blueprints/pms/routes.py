# ---------------------------- PMS (read) ----------------------------
@app.get('/pms/guest')
def pms_guest():
    """Validación simple: /pms/guest?room=1203"""
    room = request.args.get('room')
    if not room:
        return jsonify({"error":"missing room"}), 400
    row = fetchone(
        "SELECT huesped_id, nombre, habitacion, status FROM PMSGuests WHERE habitacion=? AND status='IN_HOUSE'",
        (room,)
    )
    if not row:
        return jsonify({"found": False})
    return jsonify({"found": True, "huesped_id": row["huesped_id"], "nombre": row["nombre"], "habitacion": row["habitacion"]})