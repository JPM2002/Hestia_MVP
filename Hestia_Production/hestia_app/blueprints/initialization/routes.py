import os
import time
import random
import hashlib
import json
from typing import Optional, Dict, Any

import requests
from flask import render_template, request, redirect, url_for, flash, session

from . import bp
from hestia_app.services.db import fetchone, execute

# Reuse WhatsApp Cloud credentials
META_TOKEN = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
META_PHONE_ID = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "")

# Verification code TTL (seconds)
PHONE_CODE_TTL = 10 * 60  # 10 minutes


def _session_user() -> Optional[Dict[str, Any]]:
    return session.get("user")


def _current_user_row() -> Optional[Dict[str, Any]]:
    su = _session_user()
    if not su:
        return None

    return fetchone(
        """
        SELECT
          id,
          username,
          email,
          role,
          area,
          telefono,
          initialized,
          phone_verified,
          onboarding_step
        FROM Users
        WHERE id = ?
        """,
        (su["id"],),
    )


def _require_login_redirect():
    if not _session_user():
        return redirect(url_for("auth.login"))
    return None


def _send_whatsapp_text(to_phone: str, body: str) -> None:
    """
    Minimal WhatsApp sender for verification codes.
    If creds are missing, just print to console.
    """
    to_clean = to_phone.replace("whatsapp:", "").lstrip("+")
    print(f"[INIT OUT → {to_clean}] {body}", flush=True)

    if not (META_TOKEN and META_PHONE_ID):
        return

    try:
        url = f"https://graph.facebook.com/v19.0/{META_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {META_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "text",
            "text": {"body": body},
        }
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        if r.status_code >= 300:
            print(f"[WARN] WhatsApp send (init) failed {r.status_code}: {r.text}", flush=True)
    except Exception as e:
        print(f"[WARN] WhatsApp send (init) exception: {e}", flush=True)


def _store_phone_verification(user_id: int, phone: str, code: str) -> None:
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    session["phone_verification"] = {
        "user_id": user_id,
        "phone": phone,
        "code_hash": code_hash,
        "created_at": time.time(),
    }


def _get_phone_verification() -> Optional[Dict[str, Any]]:
    data = session.get("phone_verification")
    if not isinstance(data, dict):
        return None
    return data


def _clear_phone_verification() -> None:
    session.pop("phone_verification", None)


def _needs_initialization(user_row: Dict[str, Any]) -> bool:
    initialized = bool(user_row.get("initialized"))
    phone_verified = bool(user_row.get("phone_verified"))
    step = (user_row.get("onboarding_step") or "").lower()
    return (not initialized) or (not phone_verified) or (step != "done")


@bp.route("/", methods=["GET"])
def start():
    """
    Entry point: called from login if user needs onboarding.
    """
    not_logged = _require_login_redirect()
    if not_logged:
        return not_logged

    user_row = _current_user_row()
    if not user_row:
        return redirect(url_for("auth.login"))

    if not _needs_initialization(user_row):
        return redirect(url_for("dashboard.index"))

    return redirect(url_for("initialization.phone"))


@bp.route("/phone", methods=["GET", "POST"])
def phone():
    """
    Step 1: ask for WhatsApp number, send verification code.
    """
    not_logged = _require_login_redirect()
    if not_logged:
        return not_logged

    user_row = _current_user_row()
    if not user_row:
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            phone_value=user_row.get("telefono") or "",
        )

    raw_phone = (request.form.get("phone") or "").strip()
    if not raw_phone:
        flash("Por favor ingresa tu número de WhatsApp.", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            phone_value=raw_phone,
        )

    if not raw_phone.replace("+", "").isdigit():
        flash("El número debe contener solo dígitos (y opcionalmente un + al inicio).", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            phone_value=raw_phone,
        )

    # 6-digit code
    code = f"{random.randint(0, 999999):06d}"

    _store_phone_verification(user_id=user_row["id"], phone=raw_phone, code=code)

    normalized_phone = "+" + raw_phone.lstrip("+")
    execute(
        """
        UPDATE Users
        SET telefono = ?, initialized = ?, phone_verified = ?, onboarding_step = ?
        WHERE id = ?
        """,
        (normalized_phone, False, False, "phone_code_sent", user_row["id"]),
    )

    body = (
        "🔐 Verificación de número en Hestia\n\n"
        f"Tu código de verificación es: *{code}*\n\n"
        "Por favor ingrésalo en la página de verificación para completar tu registro."
    )
    _send_whatsapp_text(normalized_phone, body)

    flash("Te hemos enviado un código por WhatsApp. Ingrésalo para verificar tu número.", "success")
    return redirect(url_for("initialization.verify"))


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    """
    Step 2: user enters the code received on WhatsApp.
    """
    not_logged = _require_login_redirect()
    if not_logged:
        return not_logged

    user_row = _current_user_row()
    if not user_row:
        return redirect(url_for("auth.login"))

    pv = _get_phone_verification()
    if not pv or pv.get("user_id") != user_row["id"]:
        flash(
            "No encontramos un código pendiente de verificación. "
            "Por favor ingresa tu número nuevamente.",
            "error",
        )
        return redirect(url_for("initialization.phone"))

    created_at = float(pv.get("created_at", 0))
    if time.time() - created_at > PHONE_CODE_TTL:
        _clear_phone_verification()
        flash(
            "Tu código de verificación ha expirado. "
            "Vuelve a ingresar tu número para obtener uno nuevo.",
            "error",
        )
        return redirect(url_for("initialization.phone"))

    if request.method == "GET":
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="verify",
            phone_value=pv.get("phone"),
        )

    input_code = (request.form.get("code") or "").strip()
    if not input_code:
        flash("Por favor ingresa el código que recibiste por WhatsApp.", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="verify",
            phone_value=pv.get("phone"),
        )

    code_hash = hashlib.sha256(input_code.encode("utf-8")).hexdigest()
    if code_hash != pv.get("code_hash"):
        flash("El código ingresado no es correcto. Inténtalo nuevamente.", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="verify",
            phone_value=pv.get("phone"),
        )

    normalized_phone = "+" + str(pv.get("phone", "")).lstrip("+")
    execute(
        """
        UPDATE Users
        SET telefono = ?, initialized = ?, phone_verified = ?, onboarding_step = ?
        WHERE id = ?
        """,
        (normalized_phone, True, True, "done", user_row["id"]),
    )

    _clear_phone_verification()

    flash("Tu número de WhatsApp ha sido verificado. ¡Bienvenido a Hestia!", "success")
    return redirect(url_for("dashboard.index"))
