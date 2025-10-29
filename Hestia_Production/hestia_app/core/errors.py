# errors.py
from __future__ import annotations
from flask import request, redirect, url_for, jsonify, flash

try:
    from psycopg2 import OperationalError as PG_OperationalError
except Exception:
    PG_OperationalError = Exception  # safe alias if psycopg2 not installed

def _wants_json():
    if request.is_json:
        return True
    accept = (request.headers.get('Accept') or '').lower()
    if 'application/json' in accept:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    if request.headers.get('HX-Request') == 'true':
        return True
    return False

def _redirect_back(default_endpoint='dashboard'):
    target = request.args.get('next') or request.referrer
    if target:
        try:
            from urllib.parse import urlparse
            base = urlparse(request.host_url)
            dest = urlparse(target)
            if dest.netloc in ("", base.netloc):
                return redirect(target)
        except Exception:
            pass
    return redirect(url_for(default_endpoint))

def _ok_or_redirect(msg, **payload):
    if _wants_json():
        p = {"ok": True, "message": msg}
        p.update(payload)
        return jsonify(p)
    flash(msg, 'success')
    return _redirect_back()

def _err_or_redirect(msg, code=400):
    if _wants_json():
        return jsonify({"ok": False, "message": msg}), code
    flash(msg, 'error')
    return _redirect_back()

def register_db_error_handlers(app):
    @app.errorhandler(PG_OperationalError)
    def _db_down(e):
        app.logger.error(f"DB error: {e}")
        flash("Base de datos no disponible. Intenta de nuevo en unos segundos.", "error")
        return redirect(url_for("login"))
