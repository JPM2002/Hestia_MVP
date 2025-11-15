import os
import time
import random
import hashlib
import json
from typing import Optional, Dict, Any, List

import requests
from flask import render_template, request, redirect, url_for, flash, session

from . import bp
from hestia_app.services.db import fetchone, execute
from hestia_app.services.whatsapp import send_whatsapp



# Verification code TTL (seconds)
PHONE_CODE_TTL = 10 * 60  # 10 minutes

# ---------------------------------------------------------
# Country list for strict phone format
#   - min_len / max_len refer to the local part (without + and country code)
# ---------------------------------------------------------
COUNTRY_OPTIONS: List[Dict[str, Any]] = [
    {
        "code": "CL",
        "name": "Chile",
        "flag": "🇨🇱",
        "dial": "+56",
        "min_len": 8,
        "max_len": 9,
    },
    {
        "code": "PE",
        "name": "Perú",
        "flag": "🇵🇪",
        "dial": "+51",
        "min_len": 9,
        "max_len": 9,
    },
    {
        "code": "DE",
        "name": "Alemania",
        "flag": "🇩🇪",
        "dial": "+49",
        "min_len": 10,
        "max_len": 12,
    },
    {
        "code": "US",
        "name": "Estados Unidos",
        "flag": "🇺🇸",
        "dial": "+1",
        "min_len": 10,
        "max_len": 10,
    },
    {
        "code": "MX",
        "name": "México",
        "flag": "🇲🇽",
        "dial": "+52",
        "min_len": 10,
        "max_len": 10,
    },
]

COUNTRY_MAP = {c["code"]: c for c in COUNTRY_OPTIONS}


def _split_phone_by_country(full_phone: str) -> tuple[Optional[str], str]:
    """
    Given a full E.164 phone (e.g. '+56912345678'), try to detect
    which country code it belongs to and return (country_code, local_part).
    If no match, returns (None, digits_without_plus).
    """
    if not full_phone:
        return None, ""
    p = str(full_phone).strip()
    if not p.startswith("+"):
        p = "+" + p.lstrip("+")
    for c in COUNTRY_OPTIONS:
        dial = c["dial"]
        if p.startswith(dial):
            return c["code"], p[len(dial):]
    # Fallback: no match, just strip '+'
    return None, p.lstrip("+")


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
    Step 1: ask for WhatsApp number (country + strict local format), send verification code.
    """
    not_logged = _require_login_redirect()
    if not_logged:
        return not_logged

    user_row = _current_user_row()
    if not user_row:
        return redirect(url_for("auth.login"))

    # --- Pre-fill from existing telefono if any ---
    default_country_code = "CL"  # fallback
    phone_local_value = ""
    selected_country_code = default_country_code

    if user_row.get("telefono"):
        c_code, local_part = _split_phone_by_country(user_row["telefono"])
        if c_code and c_code in COUNTRY_MAP:
            selected_country_code = c_code
        phone_local_value = local_part

    # For GET: show the form
    if request.method == "GET":
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            countries=COUNTRY_OPTIONS,
            selected_country_code=selected_country_code,
            phone_local_value=phone_local_value,
        )

    # --- POST: validate + send code ---
    country_code = (request.form.get("country_code") or "").upper()
    raw_local = (request.form.get("phone_local") or "").strip()
    local_digits = "".join(ch for ch in raw_local if ch.isdigit())

    if country_code not in COUNTRY_MAP:
        flash("Selecciona un país válido.", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            countries=COUNTRY_OPTIONS,
            selected_country_code=selected_country_code,
            phone_local_value=raw_local,
        )

    cinfo = COUNTRY_MAP[country_code]
    min_len = int(cinfo["min_len"])
    max_len = int(cinfo["max_len"])

    if not local_digits:
        flash("Por favor ingresa tu número local (solo dígitos).", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            countries=COUNTRY_OPTIONS,
            selected_country_code=country_code,
            phone_local_value=raw_local,
        )

    if not local_digits.isdigit():
        flash("El número local debe contener solo dígitos.", "error")
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            countries=COUNTRY_OPTIONS,
            selected_country_code=country_code,
            phone_local_value=raw_local,
        )

    if not (min_len <= len(local_digits) <= max_len):
        flash(
            f"Para {cinfo['name']} se esperan entre {min_len} y {max_len} dígitos "
            "en el número local.",
            "error",
        )
        return render_template(
            "phone_step.html",
            user=user_row,
            mode="phone",
            countries=COUNTRY_OPTIONS,
            selected_country_code=country_code,
            phone_local_value=raw_local,
        )

    # Normalize to E.164: +cc + local
    normalized_phone = cinfo["dial"] + local_digits

    # 6-digit code
    code = f"{random.randint(0, 999999):06d}"

    _store_phone_verification(user_id=user_row["id"], phone=normalized_phone, code=code)

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
    # tag='INIT' so you can distinguish these sends in the logs
    send_whatsapp(normalized_phone, body, tag="INIT")


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


@bp.route("/reset-phone", methods=["GET"])
def reset_phone():
    """
    Allow the user (from verify step) to go back and change the number
    if they wrote it wrong while a code is pending.
    """
    not_logged = _require_login_redirect()
    if not_logged:
        return not_logged

    user_row = _current_user_row()
    if not user_row:
        return redirect(url_for("auth.login"))

    _clear_phone_verification()
    execute(
        """
        UPDATE Users
        SET telefono = NULL, initialized = ?, phone_verified = ?, onboarding_step = ?
        WHERE id = ?
        """,
        (False, False, "phone", user_row["id"]),
    )

    flash("Vamos a volver a ingresar tu número de WhatsApp.", "info")
    return redirect(url_for("initialization.phone"))
